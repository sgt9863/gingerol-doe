"""
app.py — HPLC デザインスペース最適化の Streamlit Web アプリ（薄い入口）

起動: streamlit run app.py

実験〜可視化の正規フロー（タブで順に進む）:
  ① 計画(CCD)      … Day1 の中心複合計画を生成し、データ入力用 Excel 雛形をDL
  ② Day1 フィット   … 記入済み Day1 データを読み込み、保持3・幅3モデルをフィット
  ③ D最適 augment  … メカニズムモデル基準で Day2 の追加点を生成、Excel 雛形をDL
  ④ 最終解析        … Day1+Day2 全データでフィット → デザインスペース → 推奨条件 → DL
  （デモ … 合成データで①〜④を一気に体験）

注: 中核ロジック（01〜04）は numpy 系のみ。plotly/streamlit はこの入口と 05 専用。
"""

import io
import os
import importlib.util

import numpy as np
import pandas as pd
import streamlit as st
import yaml


# ──────────────────────────────
# scripts/ の数字始まりモジュールを読み込む
# ──────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "scripts")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@st.cache_resource
def load_modules():
    model = _load(os.path.join(SCRIPTS, "01_model.py"), "model01")
    design = _load(os.path.join(SCRIPTS, "02_design.py"), "design02")
    fit = _load(os.path.join(SCRIPTS, "03_fit.py"), "fit03")
    opt = _load(os.path.join(SCRIPTS, "04_optimize.py"), "opt04")
    ds = _load(os.path.join(SCRIPTS, "05_designspace.py"), "ds05")
    return model, design, fit, opt, ds


def load_config():
    """config.yaml があれば読む。無ければ config.example.yaml。"""
    for fn in ("config.yaml", "config.example.yaml"):
        p = os.path.join(HERE, fn)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return yaml.safe_load(f), fn
    return None, None


def to_excel_bytes(df, sheet_name="runs"):
    """DataFrame を xlsx のバイト列にする（ダウンロードボタン用）。"""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=sheet_name)
    return buf.getvalue()


def read_runs(uploaded, required_cols):
    """アップロードされた xlsx/csv を読み、必要列を検証して返す（不足なら None と不足列）。"""
    df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
    missing = [c for c in required_cols if c not in df.columns]
    return (None, missing) if missing else (df, [])


# ──────────────────────────────
# 画面共通：設定（サイドバー）
# ──────────────────────────────
st.set_page_config(page_title="HPLC デザインスペース最適化", layout="wide")
st.title("HPLC デザインスペース最適化（10-gingerol）")
st.caption("CCD計画 → 実験 → D最適追加 → フィット → デザインスペース可視化までを一気通貫で行う")

model, design, fit, opt, ds = load_modules()
cfg, cfg_name = load_config()
if cfg is None:
    st.error("config.yaml / config.example.yaml が見つかりません。")
    st.stop()

st.sidebar.header("設定")
st.sidebar.caption(f"読込: {cfg_name}")

fc = cfg["factors"]
st.sidebar.subheader("因子範囲")
sc = st.sidebar.columns(3)
T_lo = sc[0].number_input("T 下限", value=float(fc["T"]["low"]))
T_hi = sc[2].number_input("T 上限", value=float(fc["T"]["high"]))
P_lo = sc[0].number_input("φ 下限", value=float(fc["phi"]["low"]), format="%.3f")
P_hi = sc[2].number_input("φ 上限", value=float(fc["phi"]["high"]), format="%.3f")
F_lo = sc[0].number_input("F 下限", value=float(fc["F"]["low"]), format="%.2f")
F_hi = sc[2].number_input("F 上限", value=float(fc["F"]["high"]), format="%.2f")

factors = {
    "T":   {"low": T_lo, "center": (T_lo + T_hi) / 2, "high": T_hi},
    "phi": {"low": P_lo, "center": (P_lo + P_hi) / 2, "high": P_hi},
    "F":   {"low": F_lo, "center": (F_lo + F_hi) / 2, "high": F_hi},
}

# ── ピーク構成（目的ピーク＋夾雑ピークの数を可変に）──
st.sidebar.subheader("ピーク構成")
n_ip = int(st.sidebar.number_input("夾雑ピークの数（目的ピークの前後）", 1, 8, 1, step=1,
                                   help="目的ピーク TP に対し、邪魔なピークを何本入れるか。既定1。"))
TARGET = "TP"
INTERFERING = [f"IP{i}" for i in range(1, n_ip + 1)]
ALL_PEAKS = [TARGET] + INTERFERING
RESPONSE_COLS = [f"tR_{p}" for p in ALL_PEAKS] + [f"Wh_{p}" for p in ALL_PEAKS]
REQUIRED_COLS = ["T", "phi", "F", "day"] + RESPONSE_COLS
st.sidebar.caption(f"ピーク: {TARGET}（目的）＋ {', '.join(INTERFERING)}")

ac = cfg["acceptance_criteria"]
st.sidebar.subheader("合格条件")
criteria = {
    "Rs_min": st.sidebar.number_input("Rs_min ≥", value=float(ac["Rs_min"]), format="%.1f"),
    "tR_TP_max": st.sidebar.number_input("t_R(TP) ≤ [分]", value=float(ac["tR_TP_max"]), format="%.1f"),
    # 最遅ピークの上限はデータ取り段階の洗浄前制約であり、デザインスペースの合否には含めない
    "tR_last_max": None,
}

# ── カラム寸法 → V_m を幾何推算 ──
# V_m = 空隙率 × π × (内径/2)² × 長さ。mm³ を 1000 で割って mL。
colu = cfg["column"]
st.sidebar.subheader("カラム（V_m を寸法から計算）")
WATERS_ID = [1.0, 2.1, 3.0]            # Waters ACQUITY BEH でよくある内径 [mm]
WATERS_LEN = [30, 50, 75, 100, 150]    # よくある長さ [mm]
id_default = float(colu.get("id_mm", 2.1))
len_default = int(colu.get("length_mm", 100))
id_mm = st.sidebar.selectbox("内径 [mm]", WATERS_ID,
                             index=WATERS_ID.index(id_default) if id_default in WATERS_ID else 1)
L_mm = float(st.sidebar.selectbox("長さ [mm]", WATERS_LEN,
                                  index=WATERS_LEN.index(len_default) if len_default in WATERS_LEN else 3))
porosity = st.sidebar.number_input("空隙率", value=float(colu.get("porosity", 0.66)), format="%.2f")
Vm_geo = porosity * np.pi * (id_mm / 2.0) ** 2 * L_mm / 1000.0
st.sidebar.caption(f"幾何推算 V_m = {Vm_geo:.3f} mL（{id_mm}×{int(L_mm)} mm, 空隙率{porosity}）")
if st.sidebar.checkbox("V_m を手入力で上書き（ウラシル実測値など）"):
    Vm = st.sidebar.number_input("V_m [mL]", value=round(Vm_geo, 3), format="%.3f")
else:
    Vm = Vm_geo
st.sidebar.subheader("実験計画")
n_center = st.sidebar.slider("CCD 中心点の数", 3, 8, 6)
n_augment = st.sidebar.slider("D最適 追加点の数", 0, 16, 8)
n_bridge = st.sidebar.slider("Day2 橋渡し中心点", 0, 5, 3)
grid_n = st.sidebar.slider("デザインスペース格子の細かさ（計算解像度・大=滑らか/やや重い）",
                           11, 71, 51, step=2)
extrapolate = st.sidebar.slider("外挿（予測範囲を因子範囲の外へ拡張）", 0.0, 0.5, 0.0, step=0.05,
                                help="0 で因子範囲内のみ。>0 で雲・グラフを範囲外まで広げる（検証外の予測）。"
                                     "推奨条件は安全のため検証済みの元範囲内からのみ選ぶ。")


def run_fit_and_designspace(df, header_prefix=""):
    """共通処理: フィット → 診断表示 → 最適化 → 推奨条件 → 3D → DL。"""
    peaks_hat, diag = fit.fit_all(df, Vm, L_mm, peak_names=ALL_PEAKS)

    st.subheader(f"{header_prefix}モデルフィット")
    rows = []
    for nm in ALL_PEAKS:
        d = diag[nm]
        rows.append({
            "ピーク": nm + ("（目的）" if nm == TARGET else ""),
            "n": d.get("n", ""),
            "R²(保持)": round(d["R2_retention"], 4),
            "R²(幅)": round(d["R2_width"], 4),
            "RMSE(t_R)[秒]": round(d["RMSE_tR_min"] * 60, 2),
            "RMSE(W_h)[秒]": round(d["RMSE_Wh_min"] * 60, 2),
        })
    st.table(pd.DataFrame(rows))
    st.caption("R²=当てはまり、RMSE=予測の平均的なズレ（小さいほど良い）。n=使った点数（欠損は除外）。"
               "保持の個別係数は実験範囲が狭く多重共線のため深読みせず、予測精度で評価する。")

    st.subheader(f"{header_prefix}デザインスペースと推奨条件")
    grid, rec = opt.optimize(model, peaks_hat, factors, Vm, L_mm, criteria, n=grid_n,
                             extrapolate=extrapolate, target=TARGET, interfering=INTERFERING)
    n_pass, n_total = int(grid["pass_mask"].sum()), grid["pass_mask"].size
    c1, c2 = st.columns(2)
    c1.metric("合格領域の広さ", f"{n_pass} / {n_total} 点", f"{100*n_pass/n_total:.1f}%")
    if rec is None:
        c2.error("合格領域なし。因子範囲か合格条件を見直してください。")
        return
    s = model.separation(peaks_hat, rec["T"], rec["phi"], rec["F"], Vm, L_mm,
                         target=TARGET, interfering=INTERFERING)
    last = float(max(s[nm]["tR"] for nm in ALL_PEAKS))
    c2.success(
        f"**推奨条件（最大余裕点）**\n\n"
        f"- T = {rec['T']:.1f} ℃\n- φ = {rec['phi']:.3f}（ACN 分率）\n"
        f"- F = {rec['F']:.2f} mL/min\n\n"
        f"→ Rs_min={float(s['Rs_min']):.2f} / t_R(TP)={float(s[TARGET]['tR']):.2f}分 / 最遅={last:.2f}分"
    )

    st.subheader(f"{header_prefix}3D デザインスペース")
    cc1, cc2, cc3 = st.columns(3)
    cloud_style = "volume" if cc1.radio(
        "雲の表現", ["無段階のボリューム", "散布点"],
        key=header_prefix + "cloud") == "無段階のボリューム" else "scatter"
    side_map = {"自動": "auto", "手前": "low", "奥": "high"}
    side_lr = side_map[cc2.radio("T壁・φ壁（手前/奥）", ["自動", "手前", "奥"],
                                 key=header_prefix + "wall_lr")]
    floor_map = {"自動": "auto", "床": "low", "天井": "high"}
    side_fc = floor_map[cc3.radio("F壁（床/天井）", ["自動", "床", "天井"],
                                  key=header_prefix + "wall_fc")]
    wall_side = {"T": side_lr, "phi": side_lr, "F": side_fc}
    rc1, rc2 = st.columns(2)
    surface_count = rc1.slider("雲の密度（層の数・大=濃く滑らか）", 5, 40, 30, step=1,
                               key=header_prefix + "scount")
    rot_speed = rc2.select_slider("自動回転の速さ", options=["遅い", "標準", "速い"],
                                  value="標準", key=header_prefix + "rot")
    rot_dur = {"遅い": 140, "標準": 80, "速い": 40}[rot_speed]
    fig = ds.plot_designspace_3d(grid, rec, model_mod=model, peaks=peaks_hat,
                                 factors=factors, Vm=Vm, L_mm=L_mm,
                                 cloud_style=cloud_style, wall_side=wall_side,
                                 surface_count=surface_count, rotate_duration_ms=rot_dur)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("雲＝合格領域（Viridis: 紫=ギリギリ→黄=余裕大）、壁の線＝デザインスペース内のRs等高線5本"
               "（太黒線が Rs=2.0 の合格境界）、黒ドット＝推奨条件。左下の「▶ 自動回転」で回転。")

    rec_df = pd.DataFrame([{
        "T_degC": rec["T"], "phi_ACN": rec["phi"], "F_mL_min": rec["F"],
        "margin_normalized": rec["margin"], "Rs_min": float(s["Rs_min"]),
        "tR_TP_min": float(s[TARGET]["tR"]), "tR_last_min": last,
    }])
    dc1, dc2 = st.columns(2)
    dc1.download_button("推奨条件 CSV をDL", rec_df.to_csv(index=False).encode("utf-8-sig"),
                        file_name="recommended_condition.csv", mime="text/csv",
                        key=header_prefix + "reccsv")
    dc2.download_button("3D グラフ HTML をDL",
                        fig.to_html(include_plotlyjs="cdn", full_html=True).encode("utf-8"),
                        file_name="designspace_3d.html", mime="text/html",
                        key=header_prefix + "html")

    # 回転 GIF（kaleido＋Chrome が必要・生成に時間がかかる）
    with st.expander("回転アニメーションを GIF で書き出す"):
        gif_frames = st.slider("フレーム数（多いほど滑らか・遅い）", 12, 48, 24, step=4,
                               key=header_prefix + "gifn")
        if st.button("GIF を生成", key=header_prefix + "gifbtn"):
            with st.spinner("GIF 生成中…（フレーム数×数秒）"):
                try:
                    gif = ds.rotation_gif_bytes(fig, n_frames=gif_frames,
                                                duration_ms=rot_dur)
                    st.image(gif, caption="回転プレビュー")
                    st.download_button("回転 GIF をDL", gif,
                                       file_name="designspace_rotation.gif",
                                       mime="image/gif", key=header_prefix + "gifdl")
                except Exception as e:
                    st.error(f"GIF 生成に失敗しました（kaleido/Chrome が必要）: {e}")


# ──────────────────────────────
# タブ構成
# ──────────────────────────────
tab1, tab2, tab3, tab4, tab_demo = st.tabs(
    ["① 計画(CCD)", "② Day1 フィット", "③ D最適 augment", "④ 最終解析", "デモ"])

# ── ① CCD 計画 ──
with tab1:
    st.header("① Day1 の実験計画（CCD）")
    st.write(f"中心複合計画（頂点8＋軸上6＋中心点）を生成します。Excel 雛形をDLし、"
             f"各条件で測った {len(ALL_PEAKS)} ピーク（{', '.join(ALL_PEAKS)}）の t_R・W_h を空欄に記入してください。")
    ccd = design.ccd_design(factors, n_center=n_center, alpha=1.0, day=0).copy()
    ccd.insert(0, "run", np.arange(1, len(ccd) + 1))
    for col in RESPONSE_COLS:
        ccd[col] = np.nan
    st.dataframe(ccd[["run", "day", "type", "T", "phi", "F"]], use_container_width=True)
    st.caption(f"Day1 = {len(ccd)} 本（中心点 {n_center}）。1注入で全ピーク測れます。")
    st.download_button("Day1 入力用 Excel 雛形をDL", to_excel_bytes(ccd),
                       file_name="runs_day1_template.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── ② Day1 フィット ──
with tab2:
    st.header("② Day1 データのフィット")
    st.write("①の雛形に実測値を入れたファイルを読み込みます（xlsx/csv）。"
             "保持3本・幅3本のモデルをフィットし、当てはまりを確認します。")
    up1 = st.file_uploader("記入済み Day1 データ", type=["xlsx", "csv"], key="up1")
    if up1 is not None:
        df1, missing = read_runs(up1, REQUIRED_COLS)
        if missing:
            st.error(f"必要な列が足りません: {missing}")
        else:
            st.dataframe(df1.head(12), use_container_width=True)
            run_fit_and_designspace(df1, header_prefix="Day1 ")
            st.info("Day1 だけでも暫定のデザインスペースは出ます。精度を上げるなら③へ進んでください。")

# ── ③ D最適 augment ──
with tab3:
    st.header("③ D最適 augment（Day2 の追加実験）")
    st.write("Day1 の CCD に D最適で情報量の高い点を追加します。"
             "別日に実施するため、冒頭に橋渡し中心点（日間差の測定用）を入れます。")
    basis = st.radio(
        "D最適の目的（基準）",
        ["(A) 係数精度（モデル基準・データ不要）",
         "(B) Rs境界の精度（局所D最適・Day1データ要）"],
        help="(A) はモデル係数全体を精密化（線形なので係数値に非依存・頑健）。"
             "(B) は Rs=2 の境界近傍に点を集めてデザインスペース境界を直接精密化（Day1の係数推定を使う）。")
    use_rs = basis.startswith("(B)")

    peaks_for_aug = None
    if use_rs:
        st.caption("(B) は非線形な Rs の係数感度（ヤコビアン）を使うため、Day1 のフィット結果が必要です。"
                   "記入済み Day1 データを読み込んでください。")
        up3 = st.file_uploader("記入済み Day1 データ（(B)用）", type=["xlsx", "csv"], key="up3")
        if up3 is not None:
            df3, miss3 = read_runs(up3, REQUIRED_COLS)
            if miss3:
                st.error(f"必要な列が足りません: {miss3}")
            else:
                peaks_for_aug, _ = fit.fit_all(df3, Vm, L_mm, peak_names=ALL_PEAKS)
                st.success("Day1 をフィットしました。Rs境界標的で追加点を生成します。")
    else:
        st.caption("補足：保持モデルは係数について線形なので、(A)の追加点はフィット係数の値に依存しません"
                   "（モデルの形が決まれば最適点が決まる）。データ不要で計画できます。")

    ccd_for_aug = design.ccd_design(factors, n_center=n_center, alpha=1.0, day=0)
    parts = []
    if n_bridge > 0:
        parts.append(design.bridge_center(factors, n_bridge=n_bridge, day=1))
    if n_augment > 0:
        if use_rs and peaks_for_aug is None:
            st.info("(B) は Day1 データの読み込み後に追加点を表示します。")
        elif use_rs:
            parts.append(design.augment_design(
                factors, ccd_for_aug, n_augment, alpha=1.0, day=1, method="rs_local",
                Vm=Vm, L_mm=L_mm, model_mod=model, peaks=peaks_for_aug,
                Rs_target=criteria["Rs_min"]))
        else:
            parts.append(design.augment_design(factors, ccd_for_aug, n_augment, alpha=1.0,
                                                day=1, method="model", Vm=Vm, L_mm=L_mm))
    if parts:
        day2 = pd.concat(parts, ignore_index=True)
        day2.insert(0, "run", np.arange(len(ccd_for_aug) + 1, len(ccd_for_aug) + 1 + len(day2)))
        for col in RESPONSE_COLS:
            day2[col] = np.nan
        st.dataframe(day2[["run", "day", "type", "T", "phi", "F"]], use_container_width=True)
        st.caption(f"Day2 = {len(day2)} 本（D最適 {n_augment} ＋ 橋渡し中心点 {n_bridge}）。")
        st.download_button("Day2 入力用 Excel 雛形をDL", to_excel_bytes(day2),
                           file_name="runs_day2_template.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.warning("追加点・橋渡し中心点がどちらも 0 です。サイドバーで数を増やしてください。")

# ── ④ 最終解析 ──
with tab4:
    st.header("④ 最終解析（Day1 + Day2）")
    st.write("Day1・Day2 を結合した全データを読み込み、最終フィット → デザインスペース → 推奨条件まで出します。"
             "1ファイルにまとめても、2ファイル別々でも構いません。")
    ups = st.file_uploader("記入済み全データ（複数可）", type=["xlsx", "csv"],
                           accept_multiple_files=True, key="upall")
    if ups:
        dfs, bad = [], []
        for u in ups:
            d, miss = read_runs(u, REQUIRED_COLS)
            (dfs.append(d) if d is not None else bad.append((u.name, miss)))
        if bad:
            for name, miss in bad:
                st.error(f"{name}: 必要列が不足 {miss}")
        if dfs:
            df_all = pd.concat(dfs, ignore_index=True)
            st.dataframe(df_all.head(15), use_container_width=True)
            counts = df_all["day"].value_counts().sort_index()
            st.caption(f"全 {len(df_all)} 行（day 別: "
                       + ", ".join(f"day{int(k)}={v}" for k, v in counts.items()) + "）")
            run_fit_and_designspace(df_all, header_prefix="最終 ")

# ── デモ ──
with tab_demo:
    st.header("デモ（合成データ）")
    st.write("CCD＋D最適の計画に、既知パラメータ（交互作用・日間差入り）で合成した t_R・W_h を当てた一気通貫デモ。")
    # ボタンは押した瞬間だけ True なので、状態を session_state に保持する。
    # こうしないと雲の表現などのウィジェットを変えるたびに結果が消えてしまう。
    if st.button("デモを実行"):
        st.session_state["demo_ran"] = True
    if st.session_state.get("demo_ran"):
        plan = design.build_runs_template(factors, n_center=n_center, alpha=1.0,
                                          n_bridge=n_bridge, n_augment=n_augment,
                                          method="model", Vm=Vm, L_mm=L_mm)
        # 選んだピーク数に合わせて合成パラメータを作る（TP の周りに IP を散らす）
        vd = {"A": 0.003, "B": 0.3, "C": 2.0e-5}
        true_peaks = {"TP": {"a": -0.49, "b": 1500.0, "c": -3.0, "d": 0.0,
                             "e": 80.0, "delta": 0.03, **vd}}
        offs = np.linspace(-0.9, 0.6, len(INTERFERING)) if len(INTERFERING) > 1 else [-0.9]
        for ip, off in zip(INTERFERING, offs):
            true_peaks[ip] = {"a": -0.49 + float(off), "b": 1500.0, "c": -3.0, "d": 0.0,
                              "e": 80.0, "delta": 0.03, **vd}
        df_demo = fit.simulate_measurements(model, true_peaks, plan, Vm, L_mm, seed=1,
                                            peak_names=ALL_PEAKS)
        st.dataframe(df_demo.head(12), use_container_width=True)
        run_fit_and_designspace(df_demo, header_prefix="デモ ")

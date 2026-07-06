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


def _scripts_signature():
    """scripts/*.py の内容ハッシュ。中身が変わると load_modules のキャッシュキーも変わり、
    再デプロイ後に古いモジュールが居座る（AttributeError 等）のを防ぐ。"""
    import hashlib
    h = hashlib.md5()
    for fn in sorted(os.listdir(SCRIPTS)):
        if fn.endswith(".py"):
            with open(os.path.join(SCRIPTS, fn), "rb") as f:
                h.update(f.read())
    return h.hexdigest()


@st.cache_resource
def load_modules(scripts_sig):
    # scripts_sig はキャッシュキー専用（中身は使わない）。スクリプトが変わると再ロードされる。
    # 注意: 引数名をアンダースコア始まりにすると Streamlit がハッシュ対象から除外し、
    # キャッシュが無効化されなくなる（古いモジュールが居座る）。必ず非アンダースコア名にする。
    model = _load(os.path.join(SCRIPTS, "01_model.py"), "model01")
    design = _load(os.path.join(SCRIPTS, "02_design.py"), "design02")
    fit = _load(os.path.join(SCRIPTS, "03_fit.py"), "fit03")
    opt = _load(os.path.join(SCRIPTS, "04_optimize.py"), "opt04")
    ds = _load(os.path.join(SCRIPTS, "05_designspace.py"), "ds05")
    quad = _load(os.path.join(SCRIPTS, "06_quadratic.py"), "quad06")
    return model, design, fit, opt, ds, quad


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
    df = (pd.read_csv(uploaded, keep_default_na=True, na_values=["", " "])
          if uploaded.name.endswith(".csv")
          else pd.read_excel(uploaded, keep_default_na=True, na_values=["", " "]))
    missing = [c for c in required_cols if c not in df.columns]
    return (None, missing) if missing else (df, [])


# ──────────────────────────────
# 画面共通：設定（サイドバー）
# ──────────────────────────────
st.set_page_config(page_title="HPLC デザインスペース最適化", layout="wide")
st.title("HPLC デザインスペース最適化")

model, design, fit, opt, ds, quad = load_modules(_scripts_signature())
cfg, cfg_name = load_config()
if cfg is None:
    st.error("config.yaml / config.example.yaml が見つかりません。")
    st.stop()

# ── 設定はページ上部の「⚙ 共通設定」expander に集約する ──
# タブより前に render_settings() を呼び、全設定をグローバルに確定してから
# 各タブ（①計画・②解析・③D最適・デモ）がそれを参照する。
fc = cfg["factors"]
ac = cfg["acceptance_criteria"]
colu = cfg["column"]
TARGET = "TP"
WATERS_ID = [1.0, 2.1, 3.0]            # Waters ACQUITY BEH でよくある内径 [mm]
WATERS_LEN = [30, 50, 75, 100, 150]    # よくある長さ [mm]
# 実験計画タイプ → (kind, alpha)。BBD は α 不使用。
DESIGN_OPTIONS = {
    "Box-Behnken (BBD) — 角も軸点もなし／全点が範囲内": ("bbd", 1.0),
    "面心 CCD (α=1.0) — 頂点＋軸点が範囲の面上": ("ccd", 1.0),
    "回転可能 CCD (α≈1.682) — 予測精度が均一・軸点は範囲外": ("ccd", (2 ** 3) ** 0.25),
}
grid_n = 51                            # デザインスペース格子の解像度（固定）


def basic_factor_inputs():
    """因子範囲・ピーク構成の入力（①計画タブの冒頭で呼ぶ）。グローバルに値を設定する。"""
    global factors, INTERFERING, ALL_PEAKS, RESPONSE_COLS, REQUIRED_COLS
    st.markdown("**因子範囲（T・φ・F の下限／上限）**")
    sc = st.columns(3)
    T_lo = sc[0].number_input("T 下限 [℃]", value=float(fc["T"]["low"]))
    T_hi = sc[0].number_input("T 上限 [℃]", value=float(fc["T"]["high"]))
    P_lo = sc[1].number_input("φ 下限", value=float(fc["phi"]["low"]), format="%.3f")
    P_hi = sc[1].number_input("φ 上限", value=float(fc["phi"]["high"]), format="%.3f")
    F_lo = sc[2].number_input("F 下限 [mL/min]", value=float(fc["F"]["low"]), format="%.2f")
    F_hi = sc[2].number_input("F 上限 [mL/min]", value=float(fc["F"]["high"]), format="%.2f")
    factors = {
        "T":   {"low": T_lo, "center": (T_lo + T_hi) / 2, "high": T_hi},
        "phi": {"low": P_lo, "center": (P_lo + P_hi) / 2, "high": P_hi},
        "F":   {"low": F_lo, "center": (F_lo + F_hi) / 2, "high": F_hi},
    }
    n_ip = int(st.number_input("夾雑ピークの数（目的ピークの前後）", 1, 8, 1, step=1,
                               help="目的ピーク TP に対し、邪魔なピークを何本入れるか。既定1。"))
    INTERFERING = [f"IP{i}" for i in range(1, n_ip + 1)]
    ALL_PEAKS = [TARGET] + INTERFERING
    RESPONSE_COLS = [f"tR_{p}" for p in ALL_PEAKS] + [f"Wh_{p}" for p in ALL_PEAKS]
    REQUIRED_COLS = ["T", "phi", "F", "day"] + RESPONSE_COLS
    st.caption(f"ピーク: {TARGET}（目的）＋ {', '.join(INTERFERING)}")


def ccd_design_inputs():
    """実験計画タイプ（BBD / 面心CCD / 回転CCD）と中心点数の入力（①計画タブで呼ぶ）。"""
    global n_center, alpha_ccd, design_kind
    c = st.columns(2)
    n_center = c[0].slider("中心点の数", 3, 8, 6)
    label = c[1].radio("実験計画のタイプ", list(DESIGN_OPTIONS.keys()), index=1)
    design_kind, alpha_ccd = DESIGN_OPTIONS[label]
    if design_kind == "bbd":
        c[1].caption("Box-Behnken: 各因子ペアの辺中点 12 点 ＋ 中心点")
    else:
        c[1].caption(f"CCD: 頂点8 ＋ 軸上点6 ＋ 中心点（α = {alpha_ccd:.4f}）")


def column_and_criteria_inputs():
    """カラム寸法→V_m と合格条件の入力（②フィット&結果タブの冒頭で呼ぶ）。"""
    global Vm, L_mm, criteria
    st.markdown("**カラム（寸法から V_m を計算）**")
    cc = st.columns(3)
    id_default = float(colu.get("id_mm", 2.1))
    len_default = int(colu.get("length_mm", 100))
    id_mm = cc[0].selectbox("内径 [mm]", WATERS_ID,
                            index=WATERS_ID.index(id_default) if id_default in WATERS_ID else 1)
    L_mm = float(cc[1].selectbox("長さ [mm]", WATERS_LEN,
                                 index=WATERS_LEN.index(len_default) if len_default in WATERS_LEN else 3))
    porosity = cc[2].number_input("空隙率", value=float(colu.get("porosity", 0.66)), format="%.2f")
    Vm_geo = porosity * np.pi * (id_mm / 2.0) ** 2 * L_mm / 1000.0
    st.caption(f"幾何推算 V_m = {Vm_geo:.3f} mL（{id_mm}×{int(L_mm)} mm, 空隙率{porosity}）")
    if st.checkbox("V_m を手入力で上書き（ウラシル実測値など）"):
        Vm = st.number_input("V_m [mL]", value=round(Vm_geo, 3), format="%.3f")
    else:
        Vm = Vm_geo
    st.markdown("**合格条件**")
    ac_cols = st.columns(2)
    criteria = {
        "Rs_min": ac_cols[0].number_input("Rs_min ≥", value=float(ac["Rs_min"]), format="%.1f"),
        "tR_TP_max": ac_cols[1].number_input("t_R(TP) ≤ [分]", value=float(ac["tR_TP_max"]), format="%.1f"),
        # 最遅ピークの上限はデータ取り段階の洗浄前制約であり、デザインスペースの合否には含めない
        "tR_last_max": None,
    }


def augment_inputs():
    """D最適の点数・橋渡し中心点の入力。"""
    global n_augment, n_bridge
    c = st.columns(2)
    n_augment = c[0].slider("D最適 追加点の数", 0, 16, 8)
    n_bridge = c[1].slider("Day2 橋渡し中心点", 0, 5, 3)


# 解析モデルの選択肢 → (予測モジュール, フィットモジュール, タグ)
MODEL_OPTIONS = {
    "メカニズム（推奨・少数データに強い）": ("mech",),
    "二次回帰（フル2次の応答曲面）": ("quad",),
}


def model_inputs():
    """解析モデル（メカニズム / 二次回帰）の選択。active_model / active_fit を確定。"""
    global active_model, active_fit, model_type
    label = st.radio("解析モデル", list(MODEL_OPTIONS.keys()), index=0, horizontal=True,
                     help="メカニズム=クロマトの物理式（少数データ・外挿に強い）。"
                          "二次回帰=(T,φ,F)のフル2次（点数が十分なら有効、少数だと過学習）。")
    model_type = MODEL_OPTIONS[label][0]
    if model_type == "quad":
        active_model, active_fit = quad, quad
    else:
        active_model, active_fit = model, fit


def render_settings():
    """全設定をページ上部の expander にまとめて描画（タブより前に呼ぶ）。"""
    with st.expander("⚙ 共通設定（因子範囲・ピーク・モデル・カラム・合格条件・計画）", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            basic_factor_inputs()
            st.markdown("**解析モデル**")
            model_inputs()
        with c2:
            ccd_design_inputs()
            augment_inputs()
        st.divider()
        column_and_criteria_inputs()


def run_fit_and_designspace(df, header_prefix=""):
    """共通処理: フィット → 診断表示 → 最適化 → 推奨条件 → 3D → DL。
    解析モデル（メカニズム / 二次回帰）は共通設定の選択に従う。"""
    peaks_hat, diag = active_fit.fit_all(df, Vm, L_mm, peak_names=ALL_PEAKS)

    _mdl_name = "二次回帰" if model_type == "quad" else "メカニズム"
    st.caption(f"解析モデル: **{_mdl_name}**")
    if model_type == "quad":
        min_n = min(diag[nm].get("n", 0) for nm in ALL_PEAKS)
        if min_n < 15:
            st.warning(f"⚠ 二次回帰は1応答あたり10パラメータ。最小点数 n={min_n} では過学習しやすく"
                       "外挿が不安定です（LOO検証で確認済み）。少数データではメカニズムを推奨します。")

    st.subheader(f"{header_prefix}モデルフィット")

    def _lof_p(lof):
        return "—" if not lof else round(lof["p"], 3)

    def _r2_triple(r2, adj, q2):
        f = lambda v: "—" if v is None else f"{v:.3f}"
        return f"{r2:.3f} / {f(adj)} / {f(q2)}"

    rows = []
    lof_flag = False
    for nm in ALL_PEAKS:
        d = diag[nm]
        lr, lw = d.get("LOF_retention"), d.get("LOF_width")
        if (lr and lr["p"] < 0.05) or (lw and lw["p"] < 0.05):
            lof_flag = True
        rows.append({
            "ピーク": nm + ("（目的）" if nm == TARGET else ""),
            "n": d.get("n", ""),
            "保持 R²/adj/Q²": _r2_triple(d["R2_retention"], d.get("adjR2_retention"),
                                         d.get("Q2_retention")),
            "RMSE(t_R)秒": round(d["RMSE_tR_min"] * 60, 2),
            "LOF p(保持)": _lof_p(lr),
            "幅 R²/adj/Q²": _r2_triple(d["R2_width"], d.get("adjR2_width"), d.get("Q2_width")),
            "RMSE(W_h)秒": round(d["RMSE_Wh_min"] * 60, 2),
            "LOF p(幅)": _lof_p(lw),
        })
    st.table(pd.DataFrame(rows))
    st.caption("**R²/adj/Q²** = 当てはまり / 自由度調整済み R² / 予測 R²（Q²=LOO交差検証）。"
               "n=使った点数（欠損除外）。RMSE=予測の平均的ズレ。"
               "**Q² が R² に近いほど過学習が小さく予測力が高い**（Q²≪R² は過学習のサイン）。"
               "**LOF p**=lack-of-fit 検定（中心点の純誤差と比較。p>0.05 で当てはまり不足の証拠なし）。「—」は算出不能。")
    if lof_flag:
        st.warning("⚠ 一部で LOF p<0.05（当てはまり不足の兆候）。ただし中心点の純誤差が極めて小さいと"
                   "検定が過敏になり、実用上は無視できる系統ズレでも有意になり得ます。"
                   "RMSE の実寸（秒）や Q² が許容範囲かも併せて判断してください。")

    st.subheader(f"{header_prefix}デザインスペースと推奨条件")

    # ── 計算範囲（内挿 / 外挿）と最適化基準を 3D の手前で選ぶ ──
    oc1, oc2 = st.columns(2)
    range_mode = oc1.radio(
        "計算範囲", ["検証範囲内（内挿）", "外挿あり（範囲外も予測）"],
        key=header_prefix + "rangemode",
        help="外挿は因子範囲の外まで雲・グラフを広げます（検証外の予測）。推奨条件は安全のため検証済み範囲内からのみ選びます。")
    if range_mode.startswith("外挿"):
        extrapolate = oc1.slider("外挿の広さ（範囲幅に対する割合）", 0.0, 0.5, 0.1, step=0.05,
                                 key=header_prefix + "ext")
        restrict_range = False           # 外挿域も推奨候補に含める
        oc1.caption("⚠ 外挿域から推奨点を選びます（検証外の予測のため、採用時は追加検証を推奨）。")
    else:
        extrapolate = 0.0
        restrict_range = True

    MODE_LABELS = {
        "最も頑健（不合格領域から最も遠い）": "robust",
        "変動範囲全域が合格で t_R(TP) 最速": "fastest_tR",
        "変動範囲全域が合格で ACN 消費量が最小": "min_acn",
    }
    mode_label = oc2.radio("最適化の基準", list(MODE_LABELS.keys()),
                           key=header_prefix + "optmode")
    opt_mode = MODE_LABELS[mode_label]
    delta = None
    if opt_mode in ("fastest_tR", "min_acn"):
        oc2.caption("各因子が運用中にブレうる半幅（±）を設定。その箱の全域が合格な点だけを候補にします。")
        dc = oc2.columns(3)
        delta = {
            "T": float(dc[0].number_input("±T [℃]", value=1.0, min_value=0.0, step=0.5,
                                          key=header_prefix + "dT")),
            "phi": float(dc[1].number_input("±φ [分率]", value=0.01, min_value=0.0, step=0.005,
                                            format="%.3f", key=header_prefix + "dphi")),
            "F": float(dc[2].number_input("±F [mL/min]", value=0.02, min_value=0.0, step=0.01,
                                          format="%.2f", key=header_prefix + "dF")),
        }

    grid, rec = opt.optimize(active_model, peaks_hat, factors, Vm, L_mm, criteria, n=grid_n,
                             extrapolate=extrapolate, target=TARGET, interfering=INTERFERING,
                             mode=opt_mode, delta=delta, restrict_range=restrict_range)
    n_pass, n_total = int(grid["pass_mask"].sum()), grid["pass_mask"].size
    c1, c2 = st.columns(2)
    c1.metric("合格領域の広さ", f"{n_pass} / {n_total} 点", f"{100*n_pass/n_total:.1f}%")
    if rec is None:
        if opt_mode == "robust":
            c2.error("合格領域なし。因子範囲か合格条件を見直してください。")
        else:
            c2.error("変動範囲の箱が全域合格となる点がありません。±の幅を小さくするか合格条件を見直してください。")
        return
    s = active_model.separation(peaks_hat, rec["T"], rec["phi"], rec["F"], Vm, L_mm,
                                target=TARGET, interfering=INTERFERING)
    last = float(max(s[nm]["tR"] for nm in ALL_PEAKS))
    # 推奨点での Rs の推定精度（フィット係数の共分散から誤差伝搬・モンテカルロ）
    rsci = opt.rs_confidence(active_model, peaks_hat, diag, rec["T"], rec["phi"], rec["F"],
                             Vm, L_mm, target=TARGET, interfering=INTERFERING, n_samples=600)
    # 基準ごとの補足（目的関数の達成値）
    if opt_mode == "robust":
        obj_line = f"- 余裕（正規化距離）= {rec['margin']:.3f}\n"
    elif opt_mode == "fastest_tR":
        obj_line = f"- 変動範囲全域が合格、t_R(TP) 最速 = {rec['objective']:.2f} 分\n"
    else:
        obj_line = f"- 変動範囲全域が合格、ACN 消費量最小 = {rec['objective']:.3f} mL\n"
    c2.success(
        f"**推奨条件（{mode_label}）**\n\n"
        f"- T = {rec['T']:.1f} ℃\n- φ = {rec['phi']:.3f}（ACN 分率）\n"
        f"- F = {rec['F']:.2f} mL/min\n"
        f"{obj_line}\n"
        f"→ Rs_min={float(s['Rs_min']):.2f} "
        f"（95%CI {rsci['lo']:.2f}–{rsci['hi']:.2f}, ±{rsci['sd']:.2f}） "
        f"/ t_R(TP)={float(s[TARGET]['tR']):.2f}分 / 最遅={last:.2f}分"
    )
    if rsci["lo"] < float(criteria["Rs_min"]):
        c2.caption("⚠ Rs の95%信頼区間の下限が合格基準を下回ります（フィットの不確かさを考えると"
                   "ギリギリ）。余裕のある条件か、データ追加（③D最適）での精度向上を検討してください。")

    st.subheader(f"{header_prefix}3D デザインスペース")
    cloud_style = "volume"
    cc2, cc3 = st.columns(2)
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
    # 変動範囲を設定する基準（t_R最速 / ACN最小）のときは推奨点に ±δ の箱を重ねる
    robust_box = None
    if delta is not None and rec is not None:
        robust_box = {"center": (rec["T"], rec["phi"], rec["F"]), "delta": delta}
    fig = ds.plot_designspace_3d(grid, rec, model_mod=active_model, peaks=peaks_hat,
                                 factors=factors, Vm=Vm, L_mm=L_mm,
                                 cloud_style=cloud_style, wall_side=wall_side,
                                 surface_count=surface_count, rotate_duration_ms=rot_dur,
                                 robust_box=robust_box)
    st.plotly_chart(fig, use_container_width=True)
    _box_note = ("、破線の箱＝設定した変動範囲（この箱全域が合格になる推奨点）" if robust_box else "")
    st.caption("雲＝合格領域（Viridis: 紫=ギリギリ→黄=余裕大）、壁の線＝デザインスペース内のRs等高線5本"
               f"（太黒線が Rs=2.0 の合格境界）、黒ドット＝推奨条件{_box_note}。左下の「▶ 自動回転」で回転。")

    rec_df = pd.DataFrame([{
        "T_degC": rec["T"], "phi_ACN": rec["phi"], "F_mL_min": rec["F"],
        "criterion": mode_label,
        "margin_normalized": rec.get("margin", ""),
        "objective": rec.get("objective", ""),
        "Rs_min": float(s["Rs_min"]),
        "Rs_min_CI_lo": rsci["lo"], "Rs_min_CI_hi": rsci["hi"], "Rs_min_sd": rsci["sd"],
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
# 共通設定（タブより前に確定）＋ タブ構成
# ──────────────────────────────
render_settings()

tab1, tab2, tab3, tab_demo = st.tabs(
    ["① 計画", "② 解析", "③ D最適（任意）", "デモ"])

# ── ① 計画 ──
with tab1:
    _plan_desc = ("Box-Behnken 計画（辺中点12＋中心点）" if design_kind == "bbd"
                  else "中心複合計画（頂点8＋軸上6＋中心点）")
    st.caption(f"{_plan_desc}。雛形をDLし、{len(ALL_PEAKS)} ピーク（{', '.join(ALL_PEAKS)}）の "
               "t_R・W_h を記入 → ② で読み込みます。")
    ccd = design.ccd_design(factors, n_center=n_center, alpha=alpha_ccd, day=0, kind=design_kind).copy()
    ccd.insert(0, "run", np.arange(1, len(ccd) + 1))
    for col in RESPONSE_COLS:
        ccd[col] = np.nan
    st.dataframe(ccd[["run", "day", "type", "T", "phi", "F"]], use_container_width=True)
    st.download_button(f"Day1 入力用 Excel 雛形をDL（{len(ccd)}本）", to_excel_bytes(ccd),
                       file_name="runs_day1_template.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.plotly_chart(ds.plot_design_points_3d(ccd, factors=factors), use_container_width=True)
    if design_kind == "bbd":
        st.caption("水色=BBD点（辺中点）、緑=中心点、灰箱=指定範囲。全点が範囲内。")
    else:
        st.caption("青=頂点、赤=軸上点、緑=中心点、灰箱=指定範囲。"
                   "α=1.682 なら頂点が箱の角・軸上点は箱の外。")

# ── ② 解析（CCD だけでも、Day1+Day2 でも。ファイル複数可）──
with tab2:
    st.caption("記入済みデータ（xlsx/csv、複数可）を読み込み → フィット → デザインスペース → 推奨条件。"
               "**CCD だけで完結**します（③ D最適は任意）。")
    ups = st.file_uploader("記入済みデータ（1つでも複数でも可）", type=["xlsx", "csv"],
                           accept_multiple_files=True, key="upall")
    if ups:
        dfs, bad = [], []
        for u in ups:
            d, miss = read_runs(u, REQUIRED_COLS)
            (dfs.append(d) if d is not None else bad.append((u.name, miss)))
        for name, miss in bad:
            st.error(f"{name}: 必要列が不足 {miss}")
        if dfs:
            df_all = pd.concat(dfs, ignore_index=True)
            counts = df_all["day"].value_counts().sort_index()
            st.caption(f"全 {len(df_all)} 行（day 別: "
                       + ", ".join(f"day{int(k)}={v}" for k, v in counts.items()) + "）")
            st.dataframe(df_all.head(15), use_container_width=True)
            run_fit_and_designspace(df_all, header_prefix="")

# ── ③ D最適 augment（任意）──
with tab3:
    st.caption("**任意**。② の結果に、境界の予測精度を上げたいときだけ Day2 の追加点を生成します。"
               "別日実施のため冒頭に橋渡し中心点（日間差測定用）を入れます。")
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

    ccd_for_aug = design.ccd_design(factors, n_center=n_center, alpha=alpha_ccd, day=0, kind=design_kind)
    aug_alpha = alpha_ccd if design_kind == "ccd" else 1.0   # BBD は候補格子を範囲内に
    parts = []
    if n_bridge > 0:
        parts.append(design.bridge_center(factors, n_bridge=n_bridge, day=1))
    if n_augment > 0:
        if use_rs and peaks_for_aug is None:
            st.info("(B) は Day1 データの読み込み後に追加点を表示します。")
        elif use_rs:
            parts.append(design.augment_design(
                factors, ccd_for_aug, n_augment, alpha=aug_alpha, day=1, method="rs_local",
                Vm=Vm, L_mm=L_mm, model_mod=model, peaks=peaks_for_aug,
                Rs_target=criteria["Rs_min"]))
        else:
            parts.append(design.augment_design(factors, ccd_for_aug, n_augment, alpha=aug_alpha,
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
        both = pd.concat([ccd_for_aug.assign(type=ccd_for_aug["type"]), day2], ignore_index=True)
        st.plotly_chart(ds.plot_design_points_3d(both, factors=factors,
                                                 title="Day1(CCD) ＋ Day2(D最適) の配置"),
                        use_container_width=True)
        st.caption("Day1 の CCD 点に、Day2 の D最適追加点（橙）・橋渡し中心点（紫）を重ねた全体配置。")
    else:
        st.warning("追加点・橋渡し中心点がどちらも 0 です。点数を増やしてください。")

# ── デモ ──
with tab_demo:
    st.caption("実測データ（Day1 CCD 20本・TP+IP1+IP2）で ② 解析の流れをそのまま体験。"
               "ピーク構成・因子範囲・V_m はこのデータに合わせて自動設定します。")
    # ボタンは押した瞬間だけ True なので、状態を session_state に保持する。
    if st.button("デモを実行"):
        st.session_state["demo_ran"] = True
    if st.session_state.get("demo_ran"):
        df_demo = pd.read_csv(os.path.join(HERE, "data", "demo_runs.csv"))
        # デモは実測データに合わせてピーク構成・因子範囲・カラムを固定（共通設定より優先）
        TARGET = "TP"
        INTERFERING = ["IP1", "IP2"]
        ALL_PEAKS = [TARGET] + INTERFERING
        RESPONSE_COLS = [f"tR_{p}" for p in ALL_PEAKS] + [f"Wh_{p}" for p in ALL_PEAKS]
        REQUIRED_COLS = ["T", "phi", "F", "day"] + RESPONSE_COLS
        factors = {
            "T":   {"low": 45.0, "center": 50.0, "high": 55.0},
            "phi": {"low": 0.42, "center": 0.45, "high": 0.48},
            "F":   {"low": 0.55, "center": 0.60, "high": 0.65},
        }
        L_mm = 100.0
        Vm = 0.66 * np.pi * (2.1 / 2.0) ** 2 * L_mm / 1000.0   # 2.1×100mm, 空隙率0.66
        st.dataframe(df_demo, use_container_width=True)
        run_fit_and_designspace(df_demo, header_prefix="デモ ")

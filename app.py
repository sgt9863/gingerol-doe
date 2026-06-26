"""
app.py — HPLC デザインスペース最適化の Streamlit Web アプリ（薄い入口）

起動: streamlit run app.py

役割:
  scripts/01〜05 の関数を呼ぶだけの「入口」。ロジックは持たない（二重管理回避）。
  画面の流れ:
    1. 設定（config.yaml or 画面入力）で因子範囲・カラム・合格条件を決める
    2. 実測データ（runs.xlsx/csv）をアップロード、または合成デモデータを使う
    3. フィット（保持3・幅3）→ デザインスペース判定 → 最大余裕点
    4. 対話的 3D（雲＋壁の等高線）と推奨条件を表示、結果をダウンロード

注: 中核ロジック（01〜04）は numpy 系のみ。plotly/streamlit はこの入口と 05 専用。
"""

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


# ──────────────────────────────
# 画面
# ──────────────────────────────
st.set_page_config(page_title="HPLC デザインスペース最適化", layout="wide")
st.title("HPLC デザインスペース最適化（10-gingerol）")
st.caption("T（温度）・φ（ACN比率）・F（流速）を最適化し、ロバストな条件領域を 3D で可視化")

model, design, fit, opt, ds = load_modules()
cfg, cfg_name = load_config()
if cfg is None:
    st.error("config.yaml / config.example.yaml が見つかりません。")
    st.stop()

# ── サイドバー：設定 ──
st.sidebar.header("設定")
st.sidebar.caption(f"読込: {cfg_name}")

fc = cfg["factors"]
st.sidebar.subheader("因子範囲")
col = st.sidebar.columns(3)
T_lo = col[0].number_input("T 下限", value=float(fc["T"]["low"]))
T_hi = col[2].number_input("T 上限", value=float(fc["T"]["high"]))
P_lo = col[0].number_input("φ 下限", value=float(fc["phi"]["low"]), format="%.3f")
P_hi = col[2].number_input("φ 上限", value=float(fc["phi"]["high"]), format="%.3f")
F_lo = col[0].number_input("F 下限", value=float(fc["F"]["low"]), format="%.2f")
F_hi = col[2].number_input("F 上限", value=float(fc["F"]["high"]), format="%.2f")

factors = {
    "T":   {"low": T_lo, "center": (T_lo + T_hi) / 2, "high": T_hi},
    "phi": {"low": P_lo, "center": (P_lo + P_hi) / 2, "high": P_hi},
    "F":   {"low": F_lo, "center": (F_lo + F_hi) / 2, "high": F_hi},
}

ac = cfg["acceptance_criteria"]
st.sidebar.subheader("合格条件")
criteria = {
    "Rs_min": st.sidebar.number_input("Rs_min ≥", value=float(ac["Rs_min"]), format="%.1f"),
    "tR_TP_max": st.sidebar.number_input("t_R(TP) ≤ [分]", value=float(ac["tR_TP_max"]), format="%.1f"),
    "tR_last_max": st.sidebar.number_input("max(t_R 全3本) ≤ [分]", value=float(ac["tR_last_max"]), format="%.1f"),
}

colu = cfg["column"]
Vm = st.sidebar.number_input("V_m [mL]", value=float(colu["Vm_mL"]), format="%.3f")
L_mm = float(colu["length_mm"])
grid_n = st.sidebar.slider("格子の細かさ（1辺の点数）", 11, 41, 21, step=2)

# ── データ入力 ──
st.header("1. 実測データ")
src = st.radio("データ源", ["合成デモデータを使う", "ファイルをアップロード（xlsx/csv）"],
               horizontal=True)

REQUIRED_COLS = ["T", "phi", "F", "day",
                 "tR_IP1", "tR_TP", "tR_IP2", "Wh_IP1", "Wh_TP", "Wh_IP2"]

df = None
if src == "合成デモデータを使う":
    st.caption("CCD＋D最適の計画に、既知パラメータ（交互作用入り）で合成した t_R・W_h を当てたデモ。")
    plan = design.build_runs_template(factors, n_center=6, alpha=1.0,
                                      n_bridge=3, n_augment=8)
    true_peaks = model.example_peaks()
    for nm in ("IP1", "TP", "IP2"):
        true_peaks[nm]["e"] = 80.0
        true_peaks[nm]["delta"] = 0.03
    df = fit.simulate_measurements(model, true_peaks, plan, Vm, L_mm, seed=1)
else:
    up = st.file_uploader("runs.xlsx または runs.csv", type=["xlsx", "csv"])
    if up is not None:
        df = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)
        missing = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing:
            st.error(f"必要な列が足りません: {missing}")
            st.info(f"必要列: {REQUIRED_COLS}")
            df = None

if df is None:
    st.stop()

st.dataframe(df.head(12), use_container_width=True)
st.caption(f"全 {len(df)} 行")

# ── フィット ──
st.header("2. モデルフィット")
peaks_hat, diag = fit.fit_all(df, Vm, L_mm)
diag_rows = []
for nm in ("IP1", "TP", "IP2"):
    d = diag[nm]
    diag_rows.append({
        "ピーク": nm,
        "R²(保持)": round(d["R2_retention"], 4),
        "R²(幅)": round(d["R2_width"], 4),
        "RMSE(t_R) [秒]": round(d["RMSE_tR_min"] * 60, 2),
        "RMSE(W_h) [秒]": round(d["RMSE_Wh_min"] * 60, 2),
    })
st.table(pd.DataFrame(diag_rows))
st.caption("R² は当てはまりの良さ、RMSE は予測の平均的なズレ（小さいほど良い）。"
           "保持の個別係数は実験範囲が狭く多重共線のため深読みせず、予測精度で評価する。")

# ── 最適化 ──
st.header("3. デザインスペースと推奨条件")
grid, rec = opt.optimize(model, peaks_hat, factors, Vm, L_mm, criteria, n=grid_n)
n_pass = int(grid["pass_mask"].sum())
n_total = grid["pass_mask"].size

c1, c2 = st.columns([1, 1])
with c1:
    st.metric("合格領域の広さ", f"{n_pass} / {n_total} 点",
              f"{100*n_pass/n_total:.1f}%")
with c2:
    if rec is None:
        st.error("合格領域なし。因子範囲か合格条件を見直してください。")
    else:
        s = model.separation(peaks_hat, rec["T"], rec["phi"], rec["F"], Vm, L_mm)
        last = float(max(s["TP"]["tR"], s["IP1"]["tR"], s["IP2"]["tR"]))
        st.success(
            f"**推奨条件（最大余裕点）**\n\n"
            f"- T = {rec['T']:.1f} ℃\n"
            f"- φ = {rec['phi']:.3f}（ACN 分率）\n"
            f"- F = {rec['F']:.2f} mL/min\n\n"
            f"→ Rs_min={float(s['Rs_min']):.2f} / "
            f"t_R(TP)={float(s['TP']['tR']):.2f}分 / 最遅={last:.2f}分"
        )

# ── 3D 可視化 ──
st.header("4. 3D デザインスペース")
if rec is not None:
    fig = ds.plot_designspace_3d(grid, rec, model_mod=model, peaks=peaks_hat,
                                 factors=factors, Vm=Vm, L_mm=L_mm)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("雲＝合格領域（緑ほど Rs に余裕）、壁の線＝等高線（太黒線が Rs=2.0 の合格境界）、"
               "金ひし形＝推奨条件。ドラッグで回転・スクロールでズーム。")

    # ── ダウンロード ──
    st.header("5. 結果のダウンロード")
    rec_df = pd.DataFrame([{
        "T_degC": rec["T"], "phi_ACN": rec["phi"], "F_mL_min": rec["F"],
        "margin_normalized": rec["margin"],
        "Rs_min": float(s["Rs_min"]), "tR_TP_min": float(s["TP"]["tR"]),
        "tR_last_min": last,
    }])
    st.download_button("推奨条件 CSV をダウンロード",
                       rec_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="recommended_condition.csv", mime="text/csv")
    st.download_button("3D グラフ HTML をダウンロード",
                       fig.to_html(include_plotlyjs="cdn", full_html=True).encode("utf-8"),
                       file_name="designspace_3d.html", mime="text/html")

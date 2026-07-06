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
import re
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


def peaks_from_columns(columns):
    """アップロード表の列名からピーク構成を判定する。
    tR_X と Wh_X の両方が揃う X をピークとして採用し、目的 TP を先頭に並べる。
    IP は末尾の数字順（IP1, IP2, …, IP10 …）にソート。
    見つからなければ (None, None)。"""
    trs = {c[3:] for c in columns if c.startswith("tR_")}
    whs = {c[3:] for c in columns if c.startswith("Wh_")}
    names = trs & whs
    if TARGET not in names:
        return None, None

    def _key(n):
        m = re.search(r"(\d+)$", n)
        return (0, int(m.group(1))) if m else (1, n)

    interfering = sorted((n for n in names if n != TARGET), key=_key)
    return interfering, [TARGET] + interfering


def factors_from_data(df, response_cols):
    """アップロードデータの T/φ/F 列の min–max を評価範囲（内挿範囲）にする。
    応答が全て欠損の行（測定できなかった点）は「データが無い」ので範囲決定から除外する。
    退化（min==max・全欠損など）で範囲が取れない因子があれば None を返す。"""
    resp = df[[c for c in response_cols if c in df.columns]]
    keep = resp.notna().any(axis=1) if resp.shape[1] else pd.Series(True, index=df.index)
    sub = df[keep] if keep.any() else df
    fr = {}
    for k in ("T", "phi", "F"):
        col = pd.to_numeric(sub[k], errors="coerce")
        lo, hi = float(np.nanmin(col)) if col.notna().any() else np.nan, \
            float(np.nanmax(col)) if col.notna().any() else np.nan
        if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
            return None
        fr[k] = {"low": lo, "center": (lo + hi) / 2.0, "high": hi}
    return fr


def read_runs_auto(uploaded):
    """②解析用: ファイルを読み、基本列（T/φ/F/day）を検証し、ピーク構成を列名から判定する。
    返り値は (df, interfering, all_peaks, error)。成功時 error=None、失敗時は df=None・error に理由。"""
    df = (pd.read_csv(uploaded, keep_default_na=True, na_values=["", " "])
          if uploaded.name.endswith(".csv")
          else pd.read_excel(uploaded, keep_default_na=True, na_values=["", " "]))
    miss = [c for c in ("T", "phi", "F", "day") if c not in df.columns]
    if miss:
        return None, None, None, f"基本列が不足: {miss}"
    interfering, all_peaks = peaks_from_columns(df.columns)
    if all_peaks is None:
        return None, None, None, "目的ピークの列（tR_TP と Wh_TP）が見つかりません"
    if not interfering:
        return None, None, None, "夾雑ピークの列（tR_IP*/Wh_IP* など）が見つかりません"
    return df, interfering, all_peaks, None


# ──────────────────────────────
# 画面共通：設定・スタイル
# ──────────────────────────────
st.set_page_config(page_title="HPLC デザインスペース最適化", layout="wide")

st.markdown("""
<style>
  :root { --accent:#0d9488; --accent2:#0891b2; --line:rgba(128,128,128,.22); }
  .block-container { padding-top: 1.1rem; max-width: 1120px; }

  /* ── ヘッダー（帯ではなく、グラデ見出し＋細いルール） ── */
  .app-header { margin:.1rem 0 1.15rem; }
  .app-header h1 { margin:0; font-size:1.55rem; font-weight:650; letter-spacing:-.015em;
    background:linear-gradient(92deg,var(--accent),var(--accent2));
    -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
  .app-header p { margin:.3rem 0 0; font-size:.85rem; font-weight:400; opacity:.68; }
  .app-header .rule { height:2px; margin-top:.75rem; border-radius:2px;
    background:linear-gradient(90deg,var(--accent),var(--accent2) 38%,transparent 92%); }

  /* ── 設定内の小見出しラベル（大文字・トラッキング） ── */
  .sec-label { font-size:.7rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase;
    color:var(--accent); margin:.15rem 0 .45rem; }

  /* ── タブ：下線式のアクティブ表示 ── */
  .stTabs [data-baseweb="tab-list"] { gap:1.5rem; border-bottom:1px solid var(--line); }
  .stTabs [data-baseweb="tab"] { padding:.5rem .15rem; font-weight:600; font-size:.95rem; }
  .stTabs [aria-selected="true"] { color:var(--accent); }
  .stTabs [data-baseweb="tab-highlight"] { background:var(--accent); height:2px; }

  /* ── メトリクスを淡いカードに ── */
  [data-testid="stMetric"] { border:1px solid var(--line); border-radius:12px;
    padding:.7rem 1rem; background:rgba(13,148,136,.035); }
  [data-testid="stMetricValue"] { color:var(--accent); font-weight:700; }

  /* ── expander / popover は角丸・細枠 ── */
  [data-testid="stExpander"] { border-radius:12px; border:1px solid var(--line); }
  [data-testid="stExpander"] summary { font-weight:600; }

  /* ── テーブルのヘッダ強調 ── */
  [data-testid="stTable"] thead th { background:rgba(13,148,136,.07); font-weight:700; }

  /* ── ボタン角丸 ── */
  .stButton button, .stDownloadButton button { border-radius:10px; font-weight:600; }

  /* ── 見出しを引き締める ── */
  h2, h3 { margin-top:.3rem; font-weight:650; letter-spacing:-.006em; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="app-header">
  <h1>HPLC デザインスペース最適化</h1>
  <p>実験計画（CCD / BBD） → メカニズム・二次回帰フィット → デザインスペース → ロバストな最適条件</p>
  <div class="rule"></div>
</div>
""", unsafe_allow_html=True)

model, design, fit, opt, ds, quad = load_modules(_scripts_signature())
cfg, cfg_name = load_config()
if cfg is None:
    st.error("config.yaml / config.example.yaml が見つかりません。")
    st.stop()

# ── 設定の構成 ──
# 共通設定ボックスは廃止。各設定は「実際に必要になるタブ」で入力する:
#   ① 計画  … 因子範囲・ピーク数・実験計画（まだデータが無いので手入力するしかない）
#   ② 解析  … カラム(→V_m)・合格条件・解析モデル。因子範囲とピーク構成は
#             アップロードデータから自動判定（データがある＝範囲もピークも読める）
#   ③ D最適 … 追加点数。①の計画（範囲・ピーク）と②の V_m・合格条件を引き継ぐ
# Streamlit は全タブを毎回描画し ①→②→③→デモ の順に実行するので、後段タブが参照する
# グローバル（①の factors/peaks、②の Vm/criteria/model）は前段タブで確定済みになる。
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


def section_label(text):
    """設定内の小見出し（大文字・トラッキングのアクセントラベル）。"""
    st.markdown(f"<div class='sec-label'>{text}</div>", unsafe_allow_html=True)


def basic_factor_inputs():
    """因子範囲・ピーク構成の入力（共通設定の「分離対象」で呼ぶ）。グローバルに値を設定する。"""
    global factors, INTERFERING, ALL_PEAKS, RESPONSE_COLS, REQUIRED_COLS
    st.caption("因子範囲（T・φ・F の下限／上限）")
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


def column_inputs():
    """カラム寸法 → V_m の入力（共通設定の「カラム」で呼ぶ）。"""
    global Vm, L_mm
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


def criteria_inputs():
    """合格条件（Rs_min・t_R(TP) 上限）の入力（共通設定の「合格条件」で呼ぶ）。"""
    global criteria
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
    with st.popover("モデルの数式を表示"):
        if model_type == "quad":
            st.markdown("**二次回帰（応答曲面）モデル** — t_R・W_h を各ピークごとに (T, φ, F) のフル2次で直接フィット")
            st.latex(r"y = \beta_0 + \beta_1 T + \beta_2 \varphi + \beta_3 F"
                     r" + \beta_4 T^2 + \beta_5 \varphi^2 + \beta_6 F^2"
                     r" + \beta_7 T\varphi + \beta_8 TF + \beta_9 \varphi F")
            st.caption("y は t_R または W_h。分離度 Rs は予測した t_R・W_h から計算。")
        else:
            st.markdown("**メカニズムモデル**（クロマトの物理式）")
            st.markdown("保持係数 k（ファントホッフ × LSS）:")
            st.latex(r"\ln k = a + \frac{b}{T_K} + c\,\varphi + d\,\varphi^2"
                     r" + e\,\frac{\varphi}{T_K} + \delta\,\mathrm{day}")
            st.markdown("保持時間:")
            st.latex(r"t_R = \frac{V_m}{F}\,(1 + k)")
            st.markdown("ピーク幅（保持時間比例。N ほぼ一定 → W_h ∝ t_R）:")
            st.latex(r"W_h = w_{c0} + w_{c1}\,t_R,\qquad W_b = \tfrac{4}{\sqrt{8\ln 2}}\,W_h")
        st.markdown("分離度（クロスオーバー対応・化合物同一性で固定）:")
        st.latex(r"R_s = \frac{2\,|t_R^{\mathrm{TP}} - t_R^{\mathrm{IP}}|}{W_b^{\mathrm{TP}} + W_b^{\mathrm{IP}}},"
                 r"\qquad \text{目標}\ \min_{\mathrm{IP}} R_s \ge 2.0")
        st.caption("T_K=T+273.15[K]、φ=ACN分率、u=L·F/V_m。記号の詳細は references/理論構築の流れ.md。")


def run_fit_and_designspace(df, factors, all_peaks, interfering, Vm, L_mm, header_prefix=""):
    """共通処理: フィット → 診断表示 → 最適化 → 推奨条件 → 3D → DL。
    因子範囲・ピーク構成・V_m は呼び出し側が渡す（②はアップロードデータから自動判定、
    デモはデモデータから）。解析モデル・合格条件はグローバル（②タブで確定）を参照する。"""
    ALL_PEAKS = all_peaks            # 以降の本体は ALL_PEAKS / INTERFERING の名前で参照する
    INTERFERING = interfering
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

    with st.expander("係数の p 値（各項が有意か・p<0.05 で有意）"):
        def _pv_table(key):
            rows = []
            for nm in ALL_PEAKS:
                r = {"ピーク": nm + ("（目的）" if nm == TARGET else "")}
                r.update({k: ("—" if not np.isfinite(v) else round(v, 3))
                          for k, v in diag[nm].get(key, {}).items()})
                rows.append(r)
            return pd.DataFrame(rows)
        st.markdown("**保持モデル 係数 p 値**")
        st.table(_pv_table("ret_pvalues"))
        st.markdown("**幅モデル 係数 p 値**")
        st.table(_pv_table("wid_pvalues"))
        st.caption("p<0.05 でその項が統計的に有意。ただし**保持モデルは実験範囲が狭く多重共線**のため、"
                   "個別係数の p 値・符号は不安定になりやすく深読み非推奨（予測精度＝RMSE/Q² で評価するのが妥当）。"
                   "二次回帰では交差項の有意性の目安になる。")

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
# タブ構成（各タブが自分の設定を持つ）
# ──────────────────────────────
tab1, tab2, tab3, tab_demo = st.tabs(
    ["① 計画", "② 解析", "③ D最適（任意）", "デモ"])

# ── ① 計画（データが無い段階＝範囲・ピーク・計画は手入力）──
with tab1:
    s1, s2 = st.columns([1.15, 1])
    with s1:
        section_label("分離対象")
        basic_factor_inputs()
    with s2:
        section_label("実験計画")
        ccd_design_inputs()
    st.divider()
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

# ── ② 解析（データがある段階＝範囲もピークもファイルから読む）──
with tab2:
    s1, s2 = st.columns(2)
    with s1:
        section_label("カラム（→ V_m）")
        column_inputs()
    with s2:
        section_label("合格条件")
        criteria_inputs()
    section_label("解析モデル")
    model_inputs()
    st.caption("記入済みデータ（xlsx/csv、複数可）を読み込み → フィット → デザインスペース → 推奨条件。"
               "**因子範囲とピーク構成はデータから自動判定**します（範囲＝T/φ/F 列の min–max、"
               "ピーク＝tR_*/Wh_* 列）。**CCD だけで完結**します（③ D最適は任意）。")
    ups = st.file_uploader("記入済みデータ（1つでも複数でも可）", type=["xlsx", "csv"],
                           accept_multiple_files=True, key="upall")
    if ups:
        parsed, bad = [], []
        for u in ups:
            d, itf, allp, err = read_runs_auto(u)
            (parsed.append((u.name, d, tuple(allp))) if d is not None
             else bad.append((u.name, err)))
        for name, err in bad:
            st.error(f"{name}: {err}")
        peak_sets = {p[2] for p in parsed}
        if len(peak_sets) > 1:
            st.error("複数ファイルでピーク構成（tR_*/Wh_* 列）が一致しません: "
                     + " / ".join("{" + ", ".join(ps) + "}" for ps in peak_sets))
        elif parsed:
            all_peaks = list(parsed[0][2])
            interfering = [p for p in all_peaks if p != TARGET]
            response_cols = [f"tR_{p}" for p in all_peaks] + [f"Wh_{p}" for p in all_peaks]
            df_all = pd.concat([p[1] for p in parsed], ignore_index=True)
            factors_data = factors_from_data(df_all, response_cols)
            if factors_data is None:
                st.error("T/φ/F のいずれかで範囲が取れません（全欠損、または最小＝最大）。"
                         "測定値の入った行が各因子で2水準以上あるか確認してください。")
            else:
                counts = df_all["day"].value_counts().sort_index()
                _rng = "、".join(
                    f"{k} {factors_data[k]['low']:g}–{factors_data[k]['high']:g}"
                    for k in ("T", "phi", "F"))
                st.caption(
                    f"全 {len(df_all)} 行（day 別: "
                    + ", ".join(f"day{int(k)}={v}" for k, v in counts.items()) + "）"
                    + f"／自動判定 ピーク: {TARGET}（目的）＋ {', '.join(interfering)}"
                    + f"／評価範囲（データ min–max）: {_rng}")
                st.dataframe(df_all.head(15), use_container_width=True)
                run_fit_and_designspace(df_all, factors_data, all_peaks, interfering,
                                        Vm, L_mm, header_prefix="")

# ── ③ D最適 augment（任意）──
with tab3:
    section_label("D最適の設定")
    augment_inputs()
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
               "ピーク構成・因子範囲は②と同じくデータから自動判定、V_m はこのデータのカラムに固定します。")
    # ボタンは押した瞬間だけ True なので、状態を session_state に保持する。
    if st.button("デモを実行"):
        st.session_state["demo_ran"] = True
    if st.session_state.get("demo_ran"):
        df_demo = pd.read_csv(os.path.join(HERE, "data", "demo_runs.csv"),
                              keep_default_na=True, na_values=["", " "])
        # ②と同じロジックで、ピーク構成・因子範囲をデータから読む
        interfering_demo, all_peaks_demo = peaks_from_columns(df_demo.columns)
        response_cols_demo = ([f"tR_{p}" for p in all_peaks_demo]
                              + [f"Wh_{p}" for p in all_peaks_demo])
        factors_demo = factors_from_data(df_demo, response_cols_demo)
        L_mm_demo = 100.0
        Vm_demo = 0.66 * np.pi * (2.1 / 2.0) ** 2 * L_mm_demo / 1000.0   # 2.1×100mm, 空隙率0.66
        _rng = "、".join(f"{k} {factors_demo[k]['low']:g}–{factors_demo[k]['high']:g}"
                        for k in ("T", "phi", "F"))
        st.caption(f"自動判定 ピーク: {TARGET}（目的）＋ {', '.join(interfering_demo)}"
                   f"／評価範囲（データ min–max）: {_rng}")
        st.dataframe(df_demo, use_container_width=True)
        run_fit_and_designspace(df_demo, factors_demo, all_peaks_demo, interfering_demo,
                                Vm_demo, L_mm_demo, header_prefix="デモ ")

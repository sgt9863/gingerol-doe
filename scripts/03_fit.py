"""
03_fit.py — 実測データからモデルパラメータを推定

依存: numpy / pandas / statsmodels。

フィットの考え方（どちらもパラメータについて線形 → 普通の重回帰でOK）:

  ◆ 保持（1ピークごと）
    実測 t_R から保持係数へ:  k = t_R*F/Vm − 1   （t_0 = Vm/F より）
    応答 y = ln k を次の回帰式に当てる（OLS）:
      ln k = a + b·(1/T_K) + c·φ + d·φ² + e·(φ/T_K) + δ·day
      → 説明変数は [1, 1/T_K, φ, φ², φ/T_K, day]、係数が a,b,c,d,e,δ

  ◆ 幅（1ピークごと）
    実測 W_h から段数へ:  N = 5.54·(t_R/W_h)²、 段高 H = L/N
    線速度 u = L·F/Vm。次の van Deemter を当てる（OLS）:
      H = A + B·(1/u) + C·u
      → 説明変数は [1, 1/u, u]、係数が A,B,C

出力は 01_model.py が使うパラメータ dict（peak ごとに a..e, delta, A,B,C）。
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm

KELVIN = 273.15                  # 01_model と同じ定数（貼付独立のため再掲）
EIGHT_LN2 = 8.0 * np.log(2.0)

PEAKS = ["IP1", "TP", "IP2"]


# ──────────────────────────────
# 実測 → 中間量
# ──────────────────────────────
def k_from_tR(tR, F, Vm):
    """保持係数 k = t_R/t_0 − 1 = t_R*F/Vm − 1。"""
    return tR * F / Vm - 1.0


def N_from_width(tR, Wh):
    """半値幅 → 理論段数 N = 5.54·(t_R/W_h)²。"""
    return EIGHT_LN2 * (tR / Wh) ** 2


def linear_velocity(F, Vm, L_mm):
    """線速度 u = L·F/Vm [mm/min]。"""
    return L_mm * F / Vm


# ──────────────────────────────
# 保持フィット
# ──────────────────────────────
def fit_retention(df, peak, Vm, include_d=True, include_e=True, include_day=True):
    """1ピークの保持パラメータを OLS で推定。(params_dict, statsmodels結果) を返す。"""
    tR = df[f"tR_{peak}"].to_numpy(dtype=float)
    T = df["T"].to_numpy(dtype=float)
    phi = df["phi"].to_numpy(dtype=float)
    F = df["F"].to_numpy(dtype=float)
    day = df["day"].to_numpy(dtype=float)

    T_K = T + KELVIN
    y = np.log(k_from_tR(tR, F, Vm))

    cols = {"a": np.ones_like(T_K), "b": 1.0 / T_K, "c": phi}
    if include_d:
        cols["d"] = phi ** 2
    if include_e:
        cols["e"] = phi / T_K
    if include_day:
        cols["delta"] = day
    X = np.column_stack(list(cols.values()))
    res = sm.OLS(y, X).fit()

    fitted = dict(zip(cols.keys(), res.params))
    params = {key: fitted.get(key, 0.0) for key in ["a", "b", "c", "d", "e", "delta"]}
    return params, res


# ──────────────────────────────
# 幅フィット
# ──────────────────────────────
def fit_width(df, peak, Vm, L_mm):
    """1ピークの幅パラメータ (wc0, wc1) を OLS で推定。W_h = wc0 + wc1·t_R。
    理論段数 N はほぼ一定→ W_h は t_R にほぼ比例（AICc 後退法でも t_R が最良説明変数と支持）。
    Vm, L_mm は署名互換のため受け取るが本モデルでは未使用。"""
    tR = df[f"tR_{peak}"].to_numpy(dtype=float)
    Wh = df[f"Wh_{peak}"].to_numpy(dtype=float)
    X = np.column_stack([np.ones_like(tR), tR])
    res = sm.OLS(Wh, X).fit()
    wc0, wc1 = res.params
    return {"wc0": float(wc0), "wc1": float(wc1)}, res


# ──────────────────────────────
# 調整済み R² ／ Q²（予測 R²・LOO/PRESS ベース）
# ──────────────────────────────
def adj_r2(res):
    """自由度調整済み R²。パラメータ数に対する当てはまりの水増しを補正。
    statsmodels の rsquared_adj をそのまま返す（サンプル/パラメータ不足なら nan → None）。"""
    v = float(res.rsquared_adj)
    return None if not np.isfinite(v) else v


def q2_loo(res):
    """Q²（予測 R²）= 1 − PRESS/SS_total。OLS なら LOO 残差は e_i/(1−h_ii) で
    再フィット不要に求まる（h_ii=ハット行列の対角=レバレッジ）。
    Q² が R² に近いほど過学習が小さく予測力が高い。h_ii≈1 の点があれば計算不能→None。"""
    y = np.asarray(res.model.endog, dtype=float)
    resid = np.asarray(res.resid, dtype=float)
    infl = res.get_influence()
    h = np.asarray(infl.hat_matrix_diag, dtype=float)
    if np.any(h > 1.0 - 1e-8):
        return None
    press = float(np.sum((resid / (1.0 - h)) ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    if sst <= 0:
        return None
    return 1.0 - press / sst


# ──────────────────────────────
# lack-of-fit 検定（純誤差 vs 当てはまり不足）
# ──────────────────────────────
def lack_of_fit(cond_df, res):
    """
    同一条件の繰り返し（レプリケート）から純誤差を測り、モデルの「当てはまり不足
    (lack of fit)」を F 検定する。cond_df は fit に使った行（列 T,phi,F）、res は
    その OLS 結果（res.model.endog=応答, res.resid=残差）。

    分散分解:  SS残差(SSE) = 純誤差(SSPE) + 当てはまり不足(SSLOF)
      SSPE = Σ_group Σ_i (y_i − ȳ_group)²   （同一条件グループ内の変動）, df_PE = Σ(n_g−1)
      SSLOF = SSE − SSPE,  df_LOF = df_E − df_PE
      F = (SSLOF/df_LOF) / (SSPE/df_PE),  p = P(F > 観測値)

    解釈: p が小さい(<0.05)ほど「モデルでは説明しきれない系統的なズレがある」＝要注意。
          p が大きければモデルは棄却されない（当てはまり不足の証拠なし）。
    レプリケートが無い / 自由度が足りなければ検定不能 → None。
    """
    import collections
    from scipy import stats as _stats
    y = np.asarray(res.model.endog, dtype=float)
    sse = float(np.sum(np.asarray(res.resid, dtype=float) ** 2))
    df_e = float(res.df_resid)
    keys = list(zip(np.round(cond_df["T"].to_numpy(float), 6),
                    np.round(cond_df["phi"].to_numpy(float), 6),
                    np.round(cond_df["F"].to_numpy(float), 6)))
    groups = collections.defaultdict(list)
    for i, k in enumerate(keys):
        groups[k].append(i)
    ss_pe, df_pe = 0.0, 0.0
    for idx in groups.values():
        if len(idx) > 1:
            yy = y[idx]
            ss_pe += float(np.sum((yy - yy.mean()) ** 2))
            df_pe += len(idx) - 1
    df_lof = df_e - df_pe
    if df_pe < 1 or df_lof < 1:
        return None
    ss_lof = max(sse - ss_pe, 0.0)
    ms_pe = ss_pe / df_pe
    ms_lof = ss_lof / df_lof
    F = ms_lof / ms_pe if ms_pe > 0 else float("inf")
    p = float(_stats.f.sf(F, df_lof, df_pe))
    return {"F": float(F), "p": p, "df_lof": int(df_lof), "df_pe": int(df_pe)}


# ──────────────────────────────
# 3ピークまとめてフィット
# ──────────────────────────────
def _rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def fit_all(df, Vm, L_mm, include_d=True, include_e=True, include_day=True,
            peak_names=None):
    """
    指定ピーク（既定は IP1/TP/IP2）の保持＋幅をフィットし、peaks dict と診断を返す。
    夾雑ピーク数は peak_names で任意に指定できる。
    各ピークは欠損（NaN）行をそのピークだけ除外してフィットする（部分欠損に頑健）。
    戻り値: (peaks_dict, diagnostics_dict)
      peaks_dict[name] = {a,b,c,d,e,delta,wc0,wc1}
      diagnostics[name] = {'R2_retention','R2_width','RMSE_tR_min','RMSE_Wh_min','n'}

    注: 実験範囲が狭く保持の説明変数は多重共線。個別係数は一意に決まりにくいが、
    予測（t_R・W_h・Rs）は安定する。品質は係数でなく予測スケールの RMSE で見るのが妥当。
    """
    names = PEAKS if peak_names is None else list(peak_names)
    peaks = {}
    diagnostics = {}
    for name in names:
        sub = df.dropna(subset=[f"tR_{name}", f"Wh_{name}"])  # 欠損行を除外
        ret, ret_res = fit_retention(sub, name, Vm, include_d, include_e, include_day)
        wid, wid_res = fit_width(sub, name, Vm, L_mm)   # 幅 = wc0 + wc1·t_R
        peaks[name] = {**ret, **wid}

        # 予測スケールでの当てはまり（本当に意味のある指標）
        F = sub["F"].to_numpy(dtype=float)
        tR_meas = sub[f"tR_{name}"].to_numpy(dtype=float)
        Wh_meas = sub[f"Wh_{name}"].to_numpy(dtype=float)
        tR_hat = (Vm / F) * (1.0 + np.exp(ret_res.fittedvalues))   # ln k → k → t_R
        Wh_hat = np.asarray(wid_res.fittedvalues)                  # W_h = wc0 + wc1·t_R

        # 係数の共分散（誤差伝搬で Rs の信頼区間を出すのに使う）。
        # OLS の cov_params = σ²(XᵀX)⁻¹。列の並びは下のキー順と一致する。
        ret_keys = ["a", "b", "c"] + (["d"] if include_d else []) \
            + (["e"] if include_e else []) + (["delta"] if include_day else [])
        wid_keys = ["wc0", "wc1"]

        diagnostics[name] = {
            "R2_retention": ret_res.rsquared,
            "R2_width": wid_res.rsquared,
            "RMSE_tR_min": _rmse(tR_hat, tR_meas),
            "RMSE_Wh_min": _rmse(Wh_hat, Wh_meas),
            "n": len(sub),
            "ret_keys": ret_keys,
            "ret_cov": np.asarray(ret_res.cov_params()),
            "wid_keys": wid_keys,
            "wid_cov": np.asarray(wid_res.cov_params()),
            "LOF_retention": lack_of_fit(sub, ret_res),   # 保持モデルの当てはまり不足
            "LOF_width": lack_of_fit(sub, wid_res),        # 幅モデルの当てはまり不足
            "adjR2_retention": adj_r2(ret_res),
            "adjR2_width": adj_r2(wid_res),
            "Q2_retention": q2_loo(ret_res),
            "Q2_width": q2_loo(wid_res),
            # 各係数の p 値（列順＝キー順）。保持は多重共線で個別係数は不安定＝参考程度。
            "ret_pvalues": dict(zip(ret_keys, np.asarray(ret_res.pvalues, dtype=float))),
            "wid_pvalues": dict(zip(wid_keys, np.asarray(wid_res.pvalues, dtype=float))),
        }
    return peaks, diagnostics


# ──────────────────────────────
# 合成データ（動作確認用）
# ──────────────────────────────
def simulate_measurements(model_mod, true_peaks, design_df, Vm, L_mm,
                          noise_tR=0.01, noise_Wh=0.002, seed=0, peak_names=None):
    """既知パラメータ true_peaks から t_R・W_h を生成し、計測ノイズを足す（フィット検証用）。
    peak_names で対象ピークを指定（既定は IP1/TP/IP2）。"""
    rng = np.random.default_rng(seed)
    df = design_df.copy()
    T = df["T"].to_numpy(dtype=float)
    phi = df["phi"].to_numpy(dtype=float)
    F = df["F"].to_numpy(dtype=float)
    day = df["day"].to_numpy(dtype=float)
    names = PEAKS if peak_names is None else list(peak_names)
    for name in names:
        pred = model_mod.predict_peak(true_peaks[name], T, phi, F, Vm, L_mm, day=day)
        df[f"tR_{name}"] = pred["tR"] + rng.normal(0, noise_tR, len(df))
        df[f"Wh_{name}"] = pred["Wh"] + rng.normal(0, noise_Wh, len(df))
    return df


def _load_module(path, name):
    """数字始まりのファイル（01_model.py 等）を import する補助。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    import os
    here = os.path.dirname(__file__)
    model_mod = _load_module(os.path.join(here, "01_model.py"), "model01")
    design_mod = _load_module(os.path.join(here, "02_design.py"), "design02")

    Vm, L = 0.24, 100.0
    factors = {
        "T":   {"low": 40, "center": 50, "high": 60},
        "phi": {"low": 0.38, "center": 0.45, "high": 0.52},
        "F":   {"low": 0.4, "center": 0.6, "high": 0.8},
    }
    # Day1 CCD + Day2(橋渡し3 + D最適8)。日間差の復元も見たいので2日分。
    design = design_mod.build_runs_template(factors, n_center=6, alpha=1.0,
                                            n_bridge=3, n_augment=8)

    # 既知の「真の」パラメータ（交互作用 e と日間差 delta を意図的に入れる）
    true_peaks = model_mod.example_peaks()
    for name in PEAKS:
        true_peaks[name]["e"] = 80.0          # 交互作用（クロスオーバー源）
        true_peaks[name]["delta"] = 0.03      # Day2 のオフセット

    sim = simulate_measurements(model_mod, true_peaks, design, Vm, L, seed=1)
    peaks_hat, diag = fit_all(sim, Vm, L)

    print("=== 予測の当てはまり（意味のある指標）===")
    for name in PEAKS:
        d = diag[name]
        print(f"[{name}]  R²(保持)={d['R2_retention']:.4f}  R²(幅)={d['R2_width']:.4f}  "
              f"RMSE(t_R)={d['RMSE_tR_min']*60:.2f}秒  RMSE(W_h)={d['RMSE_Wh_min']*60:.2f}秒")

    # 真値で再現した Rs と、推定モデルで再現した Rs を全格子で比較
    print("\n=== Rs の予測一致（真モデル vs 推定モデル）===")
    rng_T = np.linspace(40, 60, 5)
    rng_phi = np.linspace(0.38, 0.52, 5)
    TT, PP = np.meshgrid(rng_T, rng_phi)
    true_rs = model_mod.separation(true_peaks, TT, PP, 0.6, Vm, L)["Rs_min"]
    hat_rs = model_mod.separation(peaks_hat, TT, PP, 0.6, Vm, L)["Rs_min"]
    print(f"  Rs_min RMSE（格子全体, F=0.6固定）= {_rmse(true_rs, hat_rs):.4f}")
    print(f"  真の Rs_min 範囲 = {true_rs.min():.2f} 〜 {true_rs.max():.2f}")

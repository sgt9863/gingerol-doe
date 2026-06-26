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
    """1ピークの van Deemter パラメータ (A,B,C) を OLS で推定。"""
    tR = df[f"tR_{peak}"].to_numpy(dtype=float)
    Wh = df[f"Wh_{peak}"].to_numpy(dtype=float)
    F = df["F"].to_numpy(dtype=float)

    N = N_from_width(tR, Wh)
    H = L_mm / N
    u = linear_velocity(F, Vm, L_mm)

    X = np.column_stack([np.ones_like(u), 1.0 / u, u])
    res = sm.OLS(H, X).fit()
    A, B, C = res.params
    return {"A": A, "B": B, "C": C}, res


# ──────────────────────────────
# 3ピークまとめてフィット
# ──────────────────────────────
def _rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def fit_all(df, Vm, L_mm, include_d=True, include_e=True, include_day=True):
    """
    全3ピークの保持＋幅をフィットし、01_model 形式の peaks dict と診断を返す。
    戻り値: (peaks_dict, diagnostics_dict)
      peaks_dict[name] = {a,b,c,d,e,delta,A,B,C}
      diagnostics[name] = {'R2_retention','R2_width','RMSE_tR_min','RMSE_Wh_min'}

    注: 実験範囲が狭く保持の説明変数は多重共線。個別係数は一意に決まりにくいが、
    予測（t_R・W_h・Rs）は安定する。品質は係数でなく予測スケールの RMSE で見るのが妥当。
    """
    F = df["F"].to_numpy(dtype=float)
    peaks = {}
    diagnostics = {}
    for name in PEAKS:
        ret, ret_res = fit_retention(df, name, Vm, include_d, include_e, include_day)
        wid, wid_res = fit_width(df, name, Vm, L_mm)
        peaks[name] = {**ret, **wid}

        # 予測スケールでの当てはまり（本当に意味のある指標）
        tR_meas = df[f"tR_{name}"].to_numpy(dtype=float)
        Wh_meas = df[f"Wh_{name}"].to_numpy(dtype=float)
        tR_hat = (Vm / F) * (1.0 + np.exp(ret_res.fittedvalues))   # ln k → k → t_R
        N_hat = L_mm / wid_res.fittedvalues                        # H → N
        Wh_hat = np.sqrt(EIGHT_LN2) * tR_meas / np.sqrt(N_hat)

        diagnostics[name] = {
            "R2_retention": ret_res.rsquared,
            "R2_width": wid_res.rsquared,
            "RMSE_tR_min": _rmse(tR_hat, tR_meas),
            "RMSE_Wh_min": _rmse(Wh_hat, Wh_meas),
        }
    return peaks, diagnostics


# ──────────────────────────────
# 合成データ（動作確認用）
# ──────────────────────────────
def simulate_measurements(model_mod, true_peaks, design_df, Vm, L_mm,
                          noise_tR=0.01, noise_Wh=0.002, seed=0):
    """既知パラメータ true_peaks から t_R・W_h を生成し、計測ノイズを足す（フィット検証用）。"""
    rng = np.random.default_rng(seed)
    df = design_df.copy()
    T = df["T"].to_numpy(dtype=float)
    phi = df["phi"].to_numpy(dtype=float)
    F = df["F"].to_numpy(dtype=float)
    day = df["day"].to_numpy(dtype=float)
    for name in PEAKS:
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

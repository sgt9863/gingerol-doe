"""
06_quadratic.py — 二次回帰（フル2次・応答曲面）モデル

メカニズムモデル（01_model）の代替。各ピークについて t_R と W_h を
(T, φ, F) のフル2次式で直接フィットする（10パラメータ／応答）:

  y = β0 + β1·T + β2·φ + β3·F + β4·T² + β5·φ² + β6·F² + β7·Tφ + β8·TF + β9·φF

01_model と同じ `separation()` / `sample_peaks()` インターフェースを持つので、
evaluate_grid / optimize / 3D描画 / rs_confidence にそのまま差し込める（入口だけ分岐）。

注意（references/モデル比較_メカニズムvs二次回帰.md）:
  二次回帰は10パラメータ固定で、点数が少ないと過学習し外挿が弱い。
  少数データではメカニズムモデルの方が LOO 予測で明確に優れる。用途に応じて選ぶこと。

依存: numpy / statsmodels / pandas。
"""

import numpy as np
import statsmodels.api as sm

EIGHT_LN2 = 8.0 * np.log(2.0)
WB_OVER_WH = 4.0 / np.sqrt(EIGHT_LN2)   # W_b = 4·t_R/√N, W_h = √(8ln2)·t_R/√N → W_b = 1.699·W_h


# ──────────────────────────────
# 2次の計画ベクトル
# ──────────────────────────────
def qdesign(T, phi, F):
    """(T,φ,F) → フル2次の説明変数行列 [1,T,φ,F,T²,φ²,F²,Tφ,TF,φF]（n×10）。
    任意形状（スカラー・1次元・メッシュ）を受け、ブロードキャスト後に平坦化して (n,10) を返す。"""
    T, phi, F = np.broadcast_arrays(np.asarray(T, float), np.asarray(phi, float),
                                    np.asarray(F, float))
    t, p, f = T.ravel(), phi.ravel(), F.ravel()
    one = np.ones_like(t)
    return np.column_stack([one, t, p, f, t**2, p**2, f**2, t*p, t*f, p*f])


def _bshape(T, phi, F):
    """T,φ,F をブロードキャストしたときの形（predict の戻り値をこの形に戻す）。"""
    return np.broadcast(np.asarray(T), np.asarray(phi), np.asarray(F)).shape


# ──────────────────────────────
# フィット（03_fit.fit_all と同じ戻り値形）
# ──────────────────────────────
def _rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def adj_r2(res):
    """自由度調整済み R²（nan なら None）。"""
    v = float(res.rsquared_adj)
    return None if not np.isfinite(v) else v


def q2_loo(res):
    """Q²（予測 R²）= 1 − PRESS/SST。OLS の LOO 残差 e_i/(1−h_ii) から算出（03_fit と同定義）。"""
    y = np.asarray(res.model.endog, dtype=float)
    resid = np.asarray(res.resid, dtype=float)
    h = np.asarray(res.get_influence().hat_matrix_diag, dtype=float)
    if np.any(h > 1.0 - 1e-8):
        return None
    press = float(np.sum((resid / (1.0 - h)) ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    return None if sst <= 0 else 1.0 - press / sst


def lack_of_fit(cond_df, res):
    """同一条件の繰り返し（純誤差）から当てはまり不足を F 検定（03_fit と同定義）。
    レプリケートが無い/自由度不足なら None。p<0.05 で「モデルで説明しきれないズレあり」。"""
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
    ms_pe, ms_lof = ss_pe / df_pe, ss_lof / df_lof
    F = ms_lof / ms_pe if ms_pe > 0 else float("inf")
    return {"F": float(F), "p": float(_stats.f.sf(F, df_lof, df_pe)),
            "df_lof": int(df_lof), "df_pe": int(df_pe)}


def fit_all(df, Vm, L_mm, peak_names=None, **_ignore):
    """
    各ピークの t_R・W_h を (T,φ,F) のフル2次で OLS フィット。
    戻り値 (peaks, diagnostics) は 03_fit.fit_all と同じ形（app 側の表示コードを共有できる）:
      peaks[name] = {"tR_coef": (10,), "Wh_coef": (10,)}
      diagnostics[name] = {R2_retention, R2_width, RMSE_tR_min, RMSE_Wh_min, n, tR_cov, Wh_cov}
    Vm, L_mm は署名互換のため受け取るが 2次回帰では未使用。
    """
    names = list(peak_names) if peak_names is not None else ["IP1", "TP", "IP2"]
    peaks, diagnostics = {}, {}
    for name in names:
        sub = df.dropna(subset=[f"tR_{name}", f"Wh_{name}"])
        T = sub["T"].to_numpy(float); phi = sub["phi"].to_numpy(float); F = sub["F"].to_numpy(float)
        tR = sub[f"tR_{name}"].to_numpy(float); Wh = sub[f"Wh_{name}"].to_numpy(float)
        X = qdesign(T, phi, F)
        rt = sm.OLS(tR, X).fit()
        rw = sm.OLS(Wh, X).fit()
        peaks[name] = {"tR_coef": np.asarray(rt.params), "Wh_coef": np.asarray(rw.params)}
        diagnostics[name] = {
            "R2_retention": rt.rsquared,
            "R2_width": rw.rsquared,
            "RMSE_tR_min": _rmse(rt.fittedvalues, tR),
            "RMSE_Wh_min": _rmse(rw.fittedvalues, Wh),
            "n": len(sub),
            "tR_cov": np.asarray(rt.cov_params()),
            "Wh_cov": np.asarray(rw.cov_params()),
            "LOF_retention": lack_of_fit(sub, rt),
            "LOF_width": lack_of_fit(sub, rw),
            "adjR2_retention": adj_r2(rt),
            "adjR2_width": adj_r2(rw),
            "Q2_retention": q2_loo(rt),
            "Q2_width": q2_loo(rw),
        }
    return peaks, diagnostics


# ──────────────────────────────
# 予測・分離度（01_model.separation と同じインターフェース）
# ──────────────────────────────
def predict_peak(peak, T, phi, F, Vm, L_mm, day=0):
    """1ピークの t_R, W_h, W_b を dict で返す（2次回帰の係数から）。
    外挿で負になり得るので W_h は微小正値でクリップ（Rs の 0 割り回避）。"""
    shape = _bshape(T, phi, F)
    X = qdesign(T, phi, F)
    tR = (X @ peak["tR_coef"]).reshape(shape)                     # 入力形状に戻す
    Wh = np.maximum(X @ peak["Wh_coef"], 1e-6).reshape(shape)     # 外挿で負→微小正にクリップ
    Wb = WB_OVER_WH * Wh
    return {"tR": tR, "Wh": Wh, "Wb": Wb}


def resolution(tR_a, Wb_a, tR_b, Wb_b):
    return 2.0 * np.abs(tR_a - tR_b) / (Wb_a + Wb_b)


def separation(peaks, T, phi, F, Vm, L_mm, day=0, target="TP", interfering=None):
    """01_model.separation と同じ戻り値（target/各IP の予測 ＋ Rs_each ＋ Rs_min）。"""
    if interfering is None:
        interfering = [k for k in peaks.keys() if k != target]
    tp = predict_peak(peaks[target], T, phi, F, Vm, L_mm, day)
    out = {target: tp}
    rs_each, rs_vals = {}, []
    for ip in interfering:
        p = predict_peak(peaks[ip], T, phi, F, Vm, L_mm, day)
        out[ip] = p
        rs = resolution(tp["tR"], tp["Wb"], p["tR"], p["Wb"])
        rs_each[ip] = rs
        rs_vals.append(rs)
    rs_min = rs_vals[0]
    for r in rs_vals[1:]:
        rs_min = np.minimum(rs_min, r)
    out["Rs_each"] = rs_each
    out["Rs_min"] = rs_min
    if "IP1" in rs_each:
        out["Rs1"] = rs_each["IP1"]
    if "IP2" in rs_each:
        out["Rs2"] = rs_each["IP2"]
    return out


# ──────────────────────────────
# Rs 信頼区間用の係数サンプリング（04_optimize.rs_confidence から呼ばれる）
# ──────────────────────────────
def sample_peaks(peaks, diagnostics, rng, target, interfering):
    """各ピークの t_R・W_h の2次係数を OLS 共分散からサンプルした peaks dict を返す。"""
    out = {}
    for nm in [target] + list(interfering):
        d = diagnostics[nm]
        out[nm] = {
            "tR_coef": rng.multivariate_normal(peaks[nm]["tR_coef"], np.atleast_2d(d["tR_cov"])),
            "Wh_coef": rng.multivariate_normal(peaks[nm]["Wh_coef"], np.atleast_2d(d["Wh_cov"])),
        }
    return out

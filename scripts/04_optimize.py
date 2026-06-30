"""
04_optimize.py — デザインスペース判定 ＋ 最大余裕点（推奨条件）

依存は numpy のみ（01_model を呼ぶ。Python in Excel にも貼れる構成）。

やること（references/decisions.md 指摘2・指摘4）:
  1. T-φ-F 空間を格子で評価し、各点が合格条件を満たすか判定する
       合格条件（config.acceptance_criteria）:
         (a) Rs_min = min{Rs1, Rs2} ≥ Rs_min_th        （分離できているか）
         (b) t_R(TP) ≤ tR_TP_max                       （目的ピークが時間内に出るか）
         (c) max(t_R 全3本) ≤ tR_last_max              （最遅ピークが洗浄前に出るか）
       → 3つ全部 True の点の集合が「デザインスペース（合格領域）」。
  2. その合格領域の中で「境界から最も遠い点」＝最大余裕点を推奨条件として返す（ICH Q8）。
       境界からの距離 = 各因子を正規化した空間での、最寄りの不合格点までの距離。
       これが最大の点ほど、条件がブレても合格に留まりやすい（最もロバスト）。

「余裕（margin）」の測り方:
  各因子を範囲幅で 0〜1 に正規化してから距離を測る（単位の違いを吸収）。
  例: T は 40〜60℃ を 0〜1、φ は 0.38〜0.52 を 0〜1 に。
  合格点 p の余裕 = min( 全ての不合格点との正規化距離 )。
  ＝「どの方向にブレたら最初に不合格になるか、その一番近い崖までの距離」。
  この余裕が最大の合格点を選ぶ。
"""

import numpy as np


# ──────────────────────────────
# 格子の生成
# ──────────────────────────────
def expand_factors(factors, extrapolate=0.0):
    """各因子の範囲を上下に extrapolate 割合だけ広げた factors を返す（外挿評価用）。
    F は流速なので下限が正に留まるよう 0.05 でクランプする。"""
    out = {}
    for f, spec in factors.items():
        lo, hi = spec["low"], spec["high"]
        span = hi - lo
        new_lo, new_hi = lo - extrapolate * span, hi + extrapolate * span
        if f == "F":
            new_lo = max(new_lo, 0.05)
        out[f] = {**spec, "low": new_lo, "high": new_hi}
    return out


def make_grid(factors, n=21):
    """
    factors（T/phi/F の low,high を持つ dict）から (n×n×n) の評価格子を作る。
    戻り値: (TT, PP, FF) いずれも 1次元に潰した同じ長さの配列 ＋ 各軸の値。
    """
    T_ax = np.linspace(factors["T"]["low"], factors["T"]["high"], n)
    P_ax = np.linspace(factors["phi"]["low"], factors["phi"]["high"], n)
    F_ax = np.linspace(factors["F"]["low"], factors["F"]["high"], n)
    TT, PP, FF = np.meshgrid(T_ax, P_ax, F_ax, indexing="ij")
    return TT.ravel(), PP.ravel(), FF.ravel(), (T_ax, P_ax, F_ax)


def _in_range_mask(T, phi, F, factors):
    """各点が元の因子範囲（検証済み領域）内かどうかの bool 配列。"""
    return (
        (T >= factors["T"]["low"] - 1e-9) & (T <= factors["T"]["high"] + 1e-9)
        & (phi >= factors["phi"]["low"] - 1e-9) & (phi <= factors["phi"]["high"] + 1e-9)
        & (F >= factors["F"]["low"] - 1e-9) & (F <= factors["F"]["high"] + 1e-9)
    )


# ──────────────────────────────
# 合格判定
# ──────────────────────────────
def evaluate_grid(model_mod, peaks, factors, Vm, L_mm, criteria, n=21, day=0,
                  extrapolate=0.0, target="TP", interfering=None):
    """
    格子の全点で目的＋夾雑ピークを予測し、合格条件を判定する（夾雑ピーク数は任意）。
    extrapolate>0 のとき、評価格子だけ因子範囲の外まで広げる（外挿。検証外の予測）。
    戻り値 dict:
      T, phi, F        : 各点の実条件（1次元配列）
      Rs_min           : 各点の 全夾雑ピークに対する Rs の最小
      tR_TP, tR_last   : 目的ピーク保持時間 / 最遅ピーク保持時間（全ピークの max）
      pass_mask        : 合格条件を満たすか（bool 配列）＝デザインスペース
      in_range         : 元の因子範囲（検証済み）内か。推奨条件はここからのみ選ぶ
      axes             : (T_ax, P_ax, F_ax)
    """
    if interfering is None:
        interfering = [k for k in peaks.keys() if k != target]
    eval_factors = expand_factors(factors, extrapolate) if extrapolate > 0 else factors
    T, phi, F, axes = make_grid(eval_factors, n=n)
    in_range = _in_range_mask(T, phi, F, factors)
    sep = model_mod.separation(peaks, T, phi, F, Vm, L_mm, day=day,
                               target=target, interfering=interfering)

    tR_TP = sep[target]["tR"]
    # クロスオーバー対応: 最遅ピークは全ピークの max（溶出順が入れ替わるため）
    tR_last = np.maximum.reduce([sep[nm]["tR"] for nm in [target] + list(interfering)])

    # 合格条件: Rs_min と t_R(TP)。
    # tR_last_max は「データ取り段階の洗浄前制約」であってデザインスペースの合否ではないため、
    # criteria に与えられた場合のみ任意で適用する（既定は不使用）。
    pass_mask = (sep["Rs_min"] >= criteria["Rs_min"]) & (tR_TP <= criteria["tR_TP_max"])
    if criteria.get("tR_last_max") is not None:
        pass_mask = pass_mask & (tR_last <= criteria["tR_last_max"])
    return {
        "T": T, "phi": phi, "F": F,
        "Rs_min": sep["Rs_min"],
        "tR_TP": tR_TP, "tR_last": tR_last,
        "pass_mask": pass_mask,
        "in_range": in_range,
        "axes": axes,
    }


# ──────────────────────────────
# 最大余裕点
# ──────────────────────────────
def _normalize(T, phi, F, factors):
    """各因子を範囲幅で 0〜1 に正規化（距離計算で単位差を吸収）。"""
    def norm(x, f):
        lo, hi = factors[f]["low"], factors[f]["high"]
        return (np.asarray(x, dtype=float) - lo) / (hi - lo)
    return np.column_stack([norm(T, "T"), norm(phi, "phi"), norm(F, "F")])


def _edge_distance(pass_pts):
    """各点から因子範囲の壁（正規化 0 と 1 の面）までの最短距離。
    各軸で min(x, 1-x)、その軸間の最小が最寄りの壁。範囲の端ほど 0 に近い。"""
    return np.minimum(pass_pts, 1.0 - pass_pts).min(axis=1)


def max_margin_point(grid_result, factors):
    """
    合格領域の中で「最寄りの崖まで最も遠い」点を返す（最大余裕点）。
    崖 = 合格条件を破る不合格点 ＋ 因子範囲の壁（探索範囲の端。外挿を避けるため崖扱い）。
    推奨は検証済みの元範囲内（in_range）からのみ選ぶ。外挿格子があっても外挿点は推奨しない。
    戻り値 dict: T, phi, F（推奨条件）, margin（正規化空間での余裕）, index。
    合格点が無ければ None。
    """
    mask = grid_result["pass_mask"]
    in_range = grid_result.get("in_range")
    cand_mask = mask if in_range is None else (mask & in_range)
    if not cand_mask.any():
        return None

    coords = _normalize(grid_result["T"], grid_result["phi"], grid_result["F"], factors)
    pass_pts = coords[cand_mask]        # 推奨候補は元範囲内の合格点のみ
    fail_pts = coords[~mask]            # 崖は不合格点（外挿域も含む）

    # (1) 因子範囲の壁までの距離（端も崖として扱う）
    edge_margin = _edge_distance(pass_pts)

    # (2) 最寄りの不合格点までの距離。
    #     KDTree（最近傍探索）で O(N log N) に。細かい格子でも高速。
    if len(fail_pts) == 0:
        fail_margin = np.full(len(pass_pts), np.inf)
    else:
        try:
            from scipy.spatial import cKDTree
            fail_margin, _ = cKDTree(fail_pts).query(pass_pts, k=1)
        except ImportError:
            # scipy が無い環境（Excel貼付など）はチャンク全ペアで代替
            fail_margin = np.empty(len(pass_pts))
            chunk = 2000
            for s in range(0, len(pass_pts), chunk):
                blk = pass_pts[s:s + chunk]
                d = np.linalg.norm(blk[:, None, :] - fail_pts[None, :, :], axis=2)
                fail_margin[s:s + chunk] = d.min(axis=1)

    # 余裕 = 2種類の崖までの距離の小さい方（最初にぶつかる崖まで）
    margins = np.minimum(edge_margin, fail_margin)
    best_local = int(np.argmax(margins))
    margin = float(margins[best_local])

    # 候補部分集合の index を全体 index に戻す
    global_idx = np.flatnonzero(cand_mask)[best_local]
    return {
        "T": float(grid_result["T"][global_idx]),
        "phi": float(grid_result["phi"][global_idx]),
        "F": float(grid_result["F"][global_idx]),
        "margin": margin,
        "index": int(global_idx),
    }


# ──────────────────────────────
# 変動範囲（ロバスト箱）を満たす点の中での最適化
# ──────────────────────────────
def _reshape_to_grid(arr, axes):
    """1次元（meshgrid indexing="ij" 由来）を (nT, nφ, nF) の3次元に戻す。"""
    nt, npp, nf = len(axes[0]), len(axes[1]), len(axes[2])
    return np.asarray(arr).reshape(nt, npp, nf)


def robust_box_mask(grid_result, delta):
    """
    各格子点を中心にした「変動範囲の箱」（各因子 ±delta[f]）の全域が合格かを返す。
    ＝合格マスクを箱サイズで収縮（erosion）した bool 配列。
    箱が評価格子の外にはみ出す端の点は「保証できない」ので不合格（=非ロバスト）扱い。
    delta は {"T":℃, "phi":分率, "F":mL/min} の半幅。0 の因子はその軸方向に広げない。
    """
    axes = grid_result["axes"]
    pass3d = _reshape_to_grid(grid_result["pass_mask"], axes).astype(float)
    sizes = []
    for ax, f in zip(axes, ["T", "phi", "F"]):
        step = (ax[1] - ax[0]) if len(ax) > 1 else 1.0
        k = int(np.floor((delta.get(f, 0.0)) / step + 1e-9)) if step > 0 else 0
        sizes.append(2 * k + 1)            # ±k 格子 → 箱の一辺
    try:
        from scipy.ndimage import minimum_filter
        eroded = minimum_filter(pass3d, size=sizes, mode="constant", cval=0.0)
    except ImportError:
        eroded = pass3d                    # scipy 無し（Excel貼付）は収縮なしで代替
    return (eroded >= 0.5).ravel()


def _candidate_mask(grid_result, robust):
    """推奨候補 = ロバスト合格 かつ 検証済み範囲内（in_range）。"""
    in_range = grid_result.get("in_range")
    return robust if in_range is None else (robust & in_range)


def _pack(grid_result, idx, extra):
    """格子 index から推奨条件 dict を組む。"""
    out = {
        "T": float(grid_result["T"][idx]),
        "phi": float(grid_result["phi"][idx]),
        "F": float(grid_result["F"][idx]),
        "index": int(idx),
    }
    out.update(extra)
    return out


def fastest_tR_point(grid_result, delta):
    """変動範囲の箱が全域合格な点のうち、t_R(TP) が最速の点を返す。無ければ None。"""
    cand = _candidate_mask(grid_result, robust_box_mask(grid_result, delta))
    if not cand.any():
        return None
    idx = np.flatnonzero(cand)
    best = int(idx[np.argmin(grid_result["tR_TP"][idx])])
    return _pack(grid_result, best, {"objective": float(grid_result["tR_TP"][best])})


def min_acn_point(grid_result, delta):
    """変動範囲の箱が全域合格な点のうち、TP 溶出までの ACN 消費量が最小の点を返す。
    ACN 消費量 = φ × F × t_R(TP)（移動相通液量 F·t_R に ACN 分率 φ を掛けた体積 [mL]）。"""
    cand = _candidate_mask(grid_result, robust_box_mask(grid_result, delta))
    if not cand.any():
        return None
    acn = grid_result["phi"] * grid_result["F"] * grid_result["tR_TP"]
    idx = np.flatnonzero(cand)
    best = int(idx[np.argmin(acn[idx])])
    return _pack(grid_result, best, {"objective": float(acn[best])})


def recommend(grid_result, factors, mode="robust", delta=None):
    """最適化基準を選んで推奨条件を返す。
      mode="robust"     … 最大余裕点（不合格領域から最も遠い）
      mode="fastest_tR" … 変動範囲全域が合格で t_R(TP) 最速（delta 必須）
      mode="min_acn"    … 変動範囲全域が合格で ACN 消費量最小（delta 必須）
    """
    if mode == "robust":
        return max_margin_point(grid_result, factors)
    if mode == "fastest_tR":
        return fastest_tR_point(grid_result, delta or {})
    if mode == "min_acn":
        return min_acn_point(grid_result, delta or {})
    raise ValueError(f"unknown mode: {mode}")


def optimize(model_mod, peaks, factors, Vm, L_mm, criteria, n=21, day=0,
             extrapolate=0.0, target="TP", interfering=None,
             mode="robust", delta=None):
    """格子評価 → 推奨条件までを一括実行。戻り値: (grid_result, recommend dict or None)。
    extrapolate>0 で評価格子を因子範囲の外まで広げる（推奨は元範囲内から選ぶ）。
    mode で最適化基準を選ぶ（robust / fastest_tR / min_acn）。
    夾雑ピーク数は interfering で任意（None なら target 以外すべて）。"""
    grid = evaluate_grid(model_mod, peaks, factors, Vm, L_mm, criteria, n=n, day=day,
                         extrapolate=extrapolate, target=target, interfering=interfering)
    rec = recommend(grid, factors, mode=mode, delta=delta)
    return grid, rec


# ──────────────────────────────
# 動作確認（合成パラメータでデザインスペースが出るか）
# ──────────────────────────────
def _load_module(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    import os
    here = os.path.dirname(__file__)
    model_mod = _load_module(os.path.join(here, "01_model.py"), "model01")

    Vm, L = 0.24, 100.0
    factors = {
        "T":   {"low": 40, "high": 60},
        "phi": {"low": 0.38, "high": 0.52},
        "F":   {"low": 0.4, "high": 0.8},
    }
    criteria = {"Rs_min": 2.0, "tR_TP_max": 7.5, "tR_last_max": 10.0}

    # 交互作用入りの例パラメータ（クロスオーバーありの状況を模擬）
    peaks = model_mod.example_peaks()
    for name in ("IP1", "TP", "IP2"):
        peaks[name]["e"] = 80.0

    grid, rec = optimize(model_mod, peaks, factors, Vm, L, criteria, n=21)

    n_pass = int(grid["pass_mask"].sum())
    n_total = grid["pass_mask"].size
    print(f"格子点 {n_total} 点中、合格（デザインスペース内）= {n_pass} 点 "
          f"（{100*n_pass/n_total:.1f}%）")
    print(f"  Rs_min 範囲   = {grid['Rs_min'].min():.2f} 〜 {grid['Rs_min'].max():.2f}")
    print(f"  t_R(TP) 範囲  = {grid['tR_TP'].min():.2f} 〜 {grid['tR_TP'].max():.2f} 分")
    print(f"  最遅 t_R 範囲 = {grid['tR_last'].min():.2f} 〜 {grid['tR_last'].max():.2f} 分")

    if rec is None:
        print("\n合格領域なし。因子範囲か合格条件を見直してください。")
    else:
        print("\n=== 推奨条件（最大余裕点）===")
        print(f"  T   = {rec['T']:.1f} ℃")
        print(f"  phi = {rec['phi']:.3f}（ACN 分率）")
        print(f"  F   = {rec['F']:.2f} mL/min")
        print(f"  余裕（正規化距離）= {rec['margin']:.3f}")
        # 推奨点での実際の分離を表示
        s = model_mod.separation(peaks, rec["T"], rec["phi"], rec["F"], Vm, L)
        print(f"  → Rs_min={float(s['Rs_min']):.2f}, "
              f"t_R(TP)={float(s['TP']['tR']):.2f}分, "
              f"最遅={float(max(s['TP']['tR'], s['IP1']['tR'], s['IP2']['tR'])):.2f}分")

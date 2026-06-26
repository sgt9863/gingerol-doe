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


# ──────────────────────────────
# 合格判定
# ──────────────────────────────
def evaluate_grid(model_mod, peaks, factors, Vm, L_mm, criteria, n=21, day=0):
    """
    格子の全点で 3 ピークを予測し、合格条件を判定する。
    戻り値 dict:
      T, phi, F        : 各点の実条件（1次元配列）
      Rs_min           : 各点の min{Rs1,Rs2}
      tR_TP, tR_last   : 各点の TP 保持時間 / 最遅ピーク保持時間
      pass_mask        : 3条件すべて満たすか（bool 配列）＝デザインスペース
      axes             : (T_ax, P_ax, F_ax)
    """
    T, phi, F, axes = make_grid(factors, n=n)
    sep = model_mod.separation(peaks, T, phi, F, Vm, L_mm, day=day)

    tR_TP = sep["TP"]["tR"]
    # クロスオーバー対応: 最遅ピークは3本のうちの max（入れ替わるため）
    tR_last = np.maximum.reduce([sep["TP"]["tR"], sep["IP1"]["tR"], sep["IP2"]["tR"]])

    pass_mask = (
        (sep["Rs_min"] >= criteria["Rs_min"])
        & (tR_TP <= criteria["tR_TP_max"])
        & (tR_last <= criteria["tR_last_max"])
    )
    return {
        "T": T, "phi": phi, "F": F,
        "Rs_min": sep["Rs_min"],
        "tR_TP": tR_TP, "tR_last": tR_last,
        "pass_mask": pass_mask,
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
    戻り値 dict: T, phi, F（推奨条件）, margin（正規化空間での余裕）, index。
    合格点が無ければ None。
    """
    mask = grid_result["pass_mask"]
    if not mask.any():
        return None

    coords = _normalize(grid_result["T"], grid_result["phi"], grid_result["F"], factors)
    pass_pts = coords[mask]
    fail_pts = coords[~mask]

    # (1) 因子範囲の壁までの距離（端も崖として扱う）
    edge_margin = _edge_distance(pass_pts)

    # (2) 最寄りの不合格点までの距離
    if len(fail_pts) == 0:
        fail_margin = np.full(len(pass_pts), np.inf)
    else:
        fail_margin = np.empty(len(pass_pts))
        chunk = 2000   # メモリ節約のためチャンクで距離計算
        for s in range(0, len(pass_pts), chunk):
            blk = pass_pts[s:s + chunk]
            d = np.linalg.norm(blk[:, None, :] - fail_pts[None, :, :], axis=2)
            fail_margin[s:s + chunk] = d.min(axis=1)

    # 余裕 = 2種類の崖までの距離の小さい方（最初にぶつかる崖まで）
    margins = np.minimum(edge_margin, fail_margin)
    best_local = int(np.argmax(margins))
    margin = float(margins[best_local])

    # pass 部分集合の index を全体 index に戻す
    global_idx = np.flatnonzero(mask)[best_local]
    return {
        "T": float(grid_result["T"][global_idx]),
        "phi": float(grid_result["phi"][global_idx]),
        "F": float(grid_result["F"][global_idx]),
        "margin": margin,
        "index": int(global_idx),
    }


def optimize(model_mod, peaks, factors, Vm, L_mm, criteria, n=21, day=0):
    """格子評価 → 最大余裕点までを一括実行。戻り値: (grid_result, recommend dict or None)。"""
    grid = evaluate_grid(model_mod, peaks, factors, Vm, L_mm, criteria, n=n, day=day)
    rec = max_margin_point(grid, factors)
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

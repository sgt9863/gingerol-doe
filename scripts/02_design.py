"""
02_design.py — 実験計画の生成（CCD ＋ 日のブロッキング ＋ D最適 augment）

依存は numpy / pandas のみ（01_model には依存しない。DoE の幾何だけ扱う）。

設計（references/decisions.md 指摘5）:
  Day1: CCD = 頂点 2³=8 + 軸上点 6 + 中心点 6 = 20 本
  Day2: D最適 augment + 中心点3本（Day1↔Day2 の日間差を橋渡し）
  別日のため day をブロック列として持つ（0=Day1, 1=Day2 …）

座標系:
  coded（符号化）… 各因子を -alpha〜+alpha に正規化した値。中心=0。
    factorial（頂点）: 各因子 ±1
    axial（軸上点）  : 1因子だけ ±alpha、他は 0
    center（中心点）  : すべて 0
  real（実値）   … 実際の T[℃] / phi[ACN分率] / F[mL/min]。

alpha（軸上点の距離）:
  既定 1.0 = 面心複合計画（CCF）。軸上点が low/high にちょうど乗るので、
  温度上限・ACN沸点などの「超えてはいけない範囲」を守れる（今回の制約向き）。
  回転可能性を優先するなら alpha=(2^3)^(1/4)=1.682 だが範囲を超えるので注意。

real への変換: real = center + coded * (half_range / alpha),  half_range=(high-low)/2
  → axial(±alpha) は center±half_range = low/high にちょうど乗る。
"""

import itertools

import numpy as np
import pandas as pd

FACTOR_NAMES = ["T", "phi", "F"]
# 実測で埋める応答列（テンプレートに空欄で用意する）
RESPONSE_COLS = ["tR_IP1", "tR_TP", "tR_IP2", "Wh_IP1", "Wh_TP", "Wh_IP2"]


# ──────────────────────────────
# 符号化 ↔ 実値
# ──────────────────────────────
def coded_to_real(coded, low, center, high, alpha):
    """符号化値 coded を実値に変換。 real = center + coded*(half_range/alpha)。"""
    half_range = (high - low) / 2.0
    step = half_range / alpha
    return center + np.asarray(coded, dtype=float) * step


def _factor_specs(factors):
    """config の factors dict から (low, center, high) を取り出す。"""
    return {f: (factors[f]["low"], factors[f]["center"], factors[f]["high"])
            for f in FACTOR_NAMES}


# ──────────────────────────────
# CCD（Day1）
# ──────────────────────────────
def ccd_coded(n_center=6, alpha=1.0):
    """CCD の符号化計画を返す（type 列付き）。頂点8 + 軸上6 + 中心n。"""
    rows = []
    # 頂点（factorial）: ±1 の全組み合わせ 2³=8
    for combo in itertools.product([-1.0, 1.0], repeat=3):
        rows.append(("factorial", *combo))
    # 軸上点（axial）: 1因子だけ ±alpha
    for i in range(3):
        for sign in (-alpha, alpha):
            pt = [0.0, 0.0, 0.0]
            pt[i] = sign
            rows.append(("axial", *pt))
    # 中心点（center）
    for _ in range(n_center):
        rows.append(("center", 0.0, 0.0, 0.0))
    cols = ["type"] + [f"c{f}" for f in FACTOR_NAMES]
    return pd.DataFrame(rows, columns=cols)


def ccd_design(factors, n_center=6, alpha=1.0, day=0):
    """CCD を実値つきの DataFrame で返す（Day1 用）。"""
    coded = ccd_coded(n_center=n_center, alpha=alpha)
    specs = _factor_specs(factors)
    df = coded.copy()
    for f in FACTOR_NAMES:
        low, center, high = specs[f]
        df[f] = coded_to_real(coded[f"c{f}"], low, center, high, alpha)
    df.insert(0, "day", day)
    return df


def bridge_center(factors, n_bridge=3, day=1):
    """Day2 冒頭の橋渡し中心点（日間差の測定用）。"""
    coded = pd.DataFrame(
        [("center", 0.0, 0.0, 0.0)] * n_bridge,
        columns=["type"] + [f"c{f}" for f in FACTOR_NAMES],
    )
    specs = _factor_specs(factors)
    df = coded.copy()
    for f in FACTOR_NAMES:
        low, center, high = specs[f]
        df[f] = coded_to_real(coded[f"c{f}"], low, center, high, alpha=1.0)
    df.insert(0, "day", day)
    df["type"] = "bridge_center"
    return df


# ──────────────────────────────
# D最適 augment（Day2）
# ──────────────────────────────
def second_order_model_matrix(coded_array):
    """符号化点 (n×3) → 2次応答曲面モデルの計画行列 X。
    列: [1, x1, x2, x3, x1², x2², x3², x1x2, x1x3, x2x3]（10列）。"""
    x = np.atleast_2d(np.asarray(coded_array, dtype=float))
    x1, x2, x3 = x[:, 0], x[:, 1], x[:, 2]
    ones = np.ones_like(x1)
    return np.column_stack([
        ones, x1, x2, x3,
        x1 ** 2, x2 ** 2, x3 ** 2,
        x1 * x2, x1 * x3, x2 * x3,
    ])


def d_optimal_augment(existing_coded, n_add, alpha=1.0, grid_levels=5, ridge=1e-6):
    """
    既存計画 existing_coded（n×3 の符号化点）に、D最適基準で n_add 点を貪欲追加する。
    候補は [-alpha, alpha]^3 の格子（grid_levels 段）。
    各ステップで予測分散（レバレッジ x'·(X'X)^-1·x）最大の候補を選ぶ
    ＝ det(X'X) を最も増やす点（行列式補題による貪欲 Fedorov）。
    戻り値: 追加点の符号化座標 (n_add×3)。
    """
    levels = np.linspace(-alpha, alpha, grid_levels)
    candidates = np.array(list(itertools.product(levels, levels, levels)))

    chosen = np.atleast_2d(np.asarray(existing_coded, dtype=float)).copy()
    added = []
    for _ in range(n_add):
        X = second_order_model_matrix(chosen)
        M = X.T @ X + ridge * np.eye(X.shape[1])   # ridge で初期の特異性を回避
        Minv = np.linalg.inv(M)
        Xc = second_order_model_matrix(candidates)
        # 各候補のレバレッジ = diag(Xc · Minv · Xc^T)
        leverage = np.einsum("ij,jk,ik->i", Xc, Minv, Xc)
        best = int(np.argmax(leverage))
        pick = candidates[best]
        added.append(pick)
        chosen = np.vstack([chosen, pick])
    return np.array(added)


def augment_design(factors, existing_df, n_add, alpha=1.0, day=1):
    """D最適 augment を実値つき DataFrame で返す（Day2 用、橋渡し中心点は別途）。"""
    existing_coded = existing_df[[f"c{f}" for f in FACTOR_NAMES]].to_numpy()
    add_coded = d_optimal_augment(existing_coded, n_add, alpha=alpha)
    df = pd.DataFrame(add_coded, columns=[f"c{f}" for f in FACTOR_NAMES])
    df.insert(0, "type", "d_optimal")
    specs = _factor_specs(factors)
    for f in FACTOR_NAMES:
        low, center, high = specs[f]
        df[f] = coded_to_real(df[f"c{f}"], low, center, high, alpha)
    df.insert(0, "day", day)
    return df


# ──────────────────────────────
# 計画表の組み立て（テンプレート出力）
# ──────────────────────────────
def build_runs_template(factors, n_center=6, alpha=1.0,
                        n_bridge=3, n_augment=0):
    """Day1 CCD（＋任意で Day2 橋渡し中心点・D最適）を1枚に結合し、応答列を空欄で付ける。"""
    parts = [ccd_design(factors, n_center=n_center, alpha=alpha, day=0)]
    if n_bridge > 0:
        parts.append(bridge_center(factors, n_bridge=n_bridge, day=1))
    if n_augment > 0:
        parts.append(augment_design(factors, parts[0], n_augment, alpha=alpha, day=1))
    df = pd.concat(parts, ignore_index=True)
    df.insert(0, "run", np.arange(1, len(df) + 1))
    for col in RESPONSE_COLS:
        df[col] = np.nan          # 実測で埋める空欄
    return df


if __name__ == "__main__":
    # config.example.yaml と同じ因子設定で動作確認（yaml は読まずベタ書き＝Excel貼付可）
    factors = {
        "T":   {"low": 40, "center": 50, "high": 60},
        "phi": {"low": 0.38, "center": 0.45, "high": 0.52},
        "F":   {"low": 0.4, "center": 0.6, "high": 0.8},
    }
    plan = build_runs_template(factors, n_center=6, alpha=1.0,
                               n_bridge=3, n_augment=8)
    print("各ブロック・種別の本数:")
    print(plan.groupby(["day", "type"]).size())
    print(f"\n合計 {len(plan)} 本")
    print("\n先頭の数行:")
    cols = ["run", "day", "type", "T", "phi", "F"]
    print(plan[cols].head(12).to_string(index=False))

    out = "data/runs_template.csv"
    plan.to_csv(out, index=False)
    print(f"\nテンプレートを書き出しました: {out}（応答列 {RESPONSE_COLS} は空欄）")

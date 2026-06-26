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


KELVIN = 273.15   # ℃ → K（01_model と同じ。モデル基準 D最適で 1/T_K を作るため）


def mechanistic_model_matrix(T, phi, F, Vm, L_mm):
    """
    メカニズムモデルの説明変数で計画行列 X を作る（実値ベース）。
    保持: ln k = a + b/T_K + c·φ + d·φ² + e·φ/T_K  → 列 [1, 1/T_K, φ, φ², φ/T_K]
    幅  : H = A + B/u + C·u（u=L·F/Vm）            → 列 [1/u, u]（切片は保持側と共有）
    合わせて [1, 1/T_K, φ, φ², φ/T_K, 1/u, u] の7列。
    ※ これらは係数について線形なので、X は係数の値に依存しない（フィット前でも作れる）。
    """
    T = np.asarray(T, dtype=float)
    phi = np.asarray(phi, dtype=float)
    F = np.asarray(F, dtype=float)
    T_K = T + KELVIN
    u = L_mm * F / Vm
    ones = np.ones_like(T_K)
    return np.column_stack([
        ones, 1.0 / T_K, phi, phi ** 2, phi / T_K,   # 保持モデルの説明変数
        1.0 / u, u,                                   # 幅モデルの説明変数
    ])


def d_optimal_augment_model(existing_real, n_add, factors, Vm, L_mm,
                            alpha=1.0, grid_levels=5, ridge=1e-9):
    """
    メカニズムモデル基準の D最適 augment（実値）。
    既存点 existing_real（列 T,phi,F）に、モデルの説明変数で det(X'X) を最大化する
    点を貪欲に n_add 個追加する（各ステップでレバレッジ最大の候補を採用）。
    候補は符号化格子 [-alpha,alpha]^3（grid_levels 段）を実値へ変換したもの。
    戻り値: 追加点の実値 DataFrame（列 T,phi,F と符号化 cT,cphi,cF）。
    レバレッジは列の線形変換に不変なので、説明変数のスケール差（1/T_K 対 u 等）は無害。
    """
    specs = _factor_specs(factors)
    levels = np.linspace(-alpha, alpha, grid_levels)
    cand_coded = np.array(list(itertools.product(levels, levels, levels)))
    cand_real = np.column_stack([
        coded_to_real(cand_coded[:, i], *specs[f], alpha)
        for i, f in enumerate(FACTOR_NAMES)
    ])

    chosen = np.atleast_2d(np.asarray(existing_real, dtype=float)).copy()
    Xc = mechanistic_model_matrix(cand_real[:, 0], cand_real[:, 1], cand_real[:, 2], Vm, L_mm)
    added_real, added_coded = [], []
    for _ in range(n_add):
        X = mechanistic_model_matrix(chosen[:, 0], chosen[:, 1], chosen[:, 2], Vm, L_mm)
        M = X.T @ X + ridge * np.eye(X.shape[1])
        Minv = np.linalg.inv(M)
        leverage = np.einsum("ij,jk,ik->i", Xc, Minv, Xc)
        best = int(np.argmax(leverage))
        added_real.append(cand_real[best])
        added_coded.append(cand_coded[best])
        chosen = np.vstack([chosen, cand_real[best]])

    out = pd.DataFrame(added_real, columns=FACTOR_NAMES)
    for i, f in enumerate(FACTOR_NAMES):
        out[f"c{f}"] = [c[i] for c in added_coded]
    return out


def augment_design(factors, existing_df, n_add, alpha=1.0, day=1, method="model",
                   Vm=0.24, L_mm=100.0):
    """
    D最適 augment を実値つき DataFrame で返す（Day2 用、橋渡し中心点は別途）。
    method="model": メカニズムモデル基準（推奨）。Vm, L_mm が必要。
    method="poly" : 符号化空間の2次多項式基準（従来）。
    """
    if method == "model":
        existing_real = existing_df[FACTOR_NAMES].to_numpy()
        df = d_optimal_augment_model(existing_real, n_add, factors, Vm, L_mm, alpha=alpha)
        df.insert(0, "type", "d_optimal")
        df.insert(0, "day", day)
        return df

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
                        n_bridge=3, n_augment=0, method="model",
                        Vm=0.24, L_mm=100.0):
    """Day1 CCD（＋任意で Day2 橋渡し中心点・D最適）を1枚に結合し、応答列を空欄で付ける。"""
    parts = [ccd_design(factors, n_center=n_center, alpha=alpha, day=0)]
    if n_bridge > 0:
        parts.append(bridge_center(factors, n_bridge=n_bridge, day=1))
    if n_augment > 0:
        parts.append(augment_design(factors, parts[0], n_augment, alpha=alpha,
                                     day=1, method=method, Vm=Vm, L_mm=L_mm))
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

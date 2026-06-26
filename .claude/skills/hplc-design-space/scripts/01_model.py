"""
01_model.py — HPLC 数理モデル（保持・幅・分離度）

このモジュールは「物理化学のメカニズムに基づく」中核ロジック。
依存は numpy のみ（yaml も pandas も使わない）。
→ 通常環境の import / Python in Excel のセル貼付 / Streamlit から呼ぶ、の3経路すべてで使える。

記号の意味（全関数共通）:
  T    : カラム温度 [℃]
  phi  : 移動相の ACN 体積分率（0〜1、例 0.45 = 45% ACN）
  F    : 流速 [mL/min]
  Vm   : カラム死容量 [mL]（カラム内の移動相の体積）
  L_mm : カラム長 [mm]
  k    : 保持係数（ピークがどれだけ長く保持されるかの無次元量）
  t_R  : 保持時間 [min]（ピークが出てくる時刻）
  t_0  : ボイド時間 [min]（保持されない物質が出る時刻、t_0 = Vm/F）
  N    : 理論段数（カラム効率。大きいほどピークが鋭い）
  W_h  : 半値幅 [min]（ピーク高さ半分での幅）
  W_b  : ベースライン幅 [min]（= 4σ。分離度 Rs の式で使う）
  day  : 実験日（ブロック因子。0=Day1, 1=Day2 …）

1ピークのパラメータは dict で持つ:
  retention（保持）: a, b, c, d, e, delta
    ln k = a + b/T_K + c*phi + d*phi^2 + e*phi/T_K + delta*day   （T_K = T+273.15 [K]）
      a     : 切片
      b     : 温度項の係数（ファントホッフ。b>0 なら低温ほど高保持）[K]
      c     : 溶媒1次項の係数（LSS/Snyder。c<0 なら ACN 増で低保持）
      d     : 溶媒2次項の係数（曲がりの補正。不要なら 0）
      e     : 温度×溶媒の交互作用項（溶媒傾き S が温度で変わる効果。
              ピークごとに違うとクロスオーバーが起きる。不要なら 0）
      delta : 日間差（ブロック項。別日のオフセット）
  width（幅・van Deemter）: A, B, C
    H = A + B/u + C*u    （H=段高 [mm], u=線速度 [mm/min]）
      A : 渦拡散項 [mm]
      B : 縦拡散項 [mm^2/min]
      C : 物質移動抵抗項 [min]

すべての関数は scalar でも numpy 配列でも動く（グリッド評価のためベクトル化対応）。
"""

import numpy as np

KELVIN = 273.15          # ℃ → K の変換オフセット
EIGHT_LN2 = 8.0 * np.log(2.0)   # = 5.545…（半値幅 ↔ 段数の換算定数）


# ──────────────────────────────
# 保持（retention）
# ──────────────────────────────
def retention_factor(T, phi, a, b, c, d=0.0, e=0.0, day=0, delta=0.0):
    """保持係数 k を返す。 ln k = a + b/T_K + c*phi + d*phi^2 + e*phi/T_K + delta*day"""
    T_K = np.asarray(T, dtype=float) + KELVIN
    phi_arr = np.asarray(phi, dtype=float)
    ln_k = (a + b / T_K + c * phi_arr + d * phi_arr ** 2
            + e * phi_arr / T_K + delta * day)
    return np.exp(ln_k)


def void_time(Vm, F):
    """ボイド時間 t_0 = Vm / F [min]。"""
    return Vm / F


def retention_time(T, phi, F, Vm, a, b, c, d=0.0, e=0.0, day=0, delta=0.0):
    """保持時間 t_R = (Vm/F)*(1+k) [min]。"""
    k = retention_factor(T, phi, a, b, c, d, e, day, delta)
    return (Vm / F) * (1.0 + k)


# ──────────────────────────────
# 幅・効率（band broadening）
# ──────────────────────────────
def linear_velocity(F, Vm, L_mm):
    """線速度 u = L/t_0 = L*F/Vm [mm/min]。"""
    return L_mm * F / Vm


def plate_count(F, Vm, L_mm, A, B, C):
    """理論段数 N。van Deemter H = A + B/u + C*u、N = L/H。"""
    u = linear_velocity(F, Vm, L_mm)
    H = A + B / u + C * u
    return L_mm / H


def width_half_height(t_R, N):
    """半値幅 W_h = sqrt(8 ln2) * t_R / sqrt(N)。逆に N = 5.54*(t_R/W_h)^2。"""
    return np.sqrt(EIGHT_LN2) * t_R / np.sqrt(N)


def width_baseline(t_R, N):
    """ベースライン幅 W_b = 4*t_R/sqrt(N)（= 4σ）。Rs の式で使う。"""
    return 4.0 * t_R / np.sqrt(N)


def plate_count_from_width(t_R, W_h):
    """実測の半値幅 W_h から理論段数 N を逆算: N = 8ln2*(t_R/W_h)^2 = 5.54*(t_R/W_h)^2。
    03_fit で「実測幅 → N → van Deemter フィット」に使う（width_half_height の逆関数）。"""
    return EIGHT_LN2 * (t_R / W_h) ** 2


# ──────────────────────────────
# 1ピックの予測をまとめる
# ──────────────────────────────
def predict_peak(peak, T, phi, F, Vm, L_mm, day=0):
    """1ピークの t_R, N, W_h, W_b を dict で返す。peak は上記パラメータの dict。"""
    tR = retention_time(
        T, phi, F, Vm,
        peak["a"], peak["b"], peak["c"],
        peak.get("d", 0.0), peak.get("e", 0.0), day, peak.get("delta", 0.0),
    )
    N = plate_count(F, Vm, L_mm, peak["A"], peak["B"], peak["C"])
    return {
        "tR": tR,
        "N": N,
        "Wh": width_half_height(tR, N),
        "Wb": width_baseline(tR, N),
    }


# ──────────────────────────────
# 分離度（resolution）— 化合物の同一性で定義（クロスオーバー対応）
# ──────────────────────────────
def resolution(tR_a, Wb_a, tR_b, Wb_b):
    """Rs = 2*|t_R(a) - t_R(b)| / (Wb_a + Wb_b)。絶対値なので溶出順が入れ替わっても正しい。"""
    return 2.0 * np.abs(tR_a - tR_b) / (Wb_a + Wb_b)


def separation(peaks, T, phi, F, Vm, L_mm, day=0):
    """
    3ピーク（'TP','IP1','IP2'）の予測と Rs1/Rs2/min を返す。
      Rs1 = TP–IP1、 Rs2 = TP–IP2（いずれも化合物の同一性で固定）
    最適化目標は Rs_min = min{Rs1, Rs2}。
    """
    tp = predict_peak(peaks["TP"], T, phi, F, Vm, L_mm, day)
    ip1 = predict_peak(peaks["IP1"], T, phi, F, Vm, L_mm, day)
    ip2 = predict_peak(peaks["IP2"], T, phi, F, Vm, L_mm, day)
    Rs1 = resolution(tp["tR"], tp["Wb"], ip1["tR"], ip1["Wb"])
    Rs2 = resolution(tp["tR"], tp["Wb"], ip2["tR"], ip2["Wb"])
    return {
        "Rs1": Rs1,
        "Rs2": Rs2,
        "Rs_min": np.minimum(Rs1, Rs2),
        "TP": tp, "IP1": ip1, "IP2": ip2,
    }


# ──────────────────────────────
# 例示用パラメータ（実フィット前の動作確認・デモ用のダミー）
# ──────────────────────────────
def example_peaks():
    """
    動作確認・合成データ生成用の暫定パラメータ。
    実際は 03_fit.py が実測データから推定した値で置き換える。
    中水準（T=50, phi=0.45, F=0.6, Vm=0.24, L=100）で3ピークが ~7分付近・IP1<TP<IP2 になるよう設定。
    """
    vd = {"A": 0.003, "B": 0.3, "C": 2.0e-5}   # van Deemter（3ピーク共通の例）
    return {
        "IP1": {"a": -1.39, "b": 1800.0, "c": -3.2, "d": 0.0, "e": 0.0, "delta": 0.0, **vd},
        "TP":  {"a": -0.49, "b": 1500.0, "c": -3.0, "d": 0.0, "e": 0.0, "delta": 0.0, **vd},
        "IP2": {"a":  0.10, "b": 1300.0, "c": -2.8, "d": 0.0, "e": 0.0, "delta": 0.0, **vd},
    }


if __name__ == "__main__":
    # 直接実行で中水準のサニティチェック: python scripts/01_model.py
    peaks = example_peaks()
    Vm, L = 0.24, 100.0
    T, phi, F = 50.0, 0.45, 0.6
    res = separation(peaks, T, phi, F, Vm, L)
    print(f"条件: T={T}℃, phi={phi}, F={F} mL/min, Vm={Vm} mL, L={L} mm")
    print(f"t_0 = {void_time(Vm, F):.3f} min")
    for name in ("IP1", "TP", "IP2"):
        p = res[name]
        print(f"  {name}: t_R={p['tR']:.3f} min, N={p['N']:.0f}, "
              f"W_h={p['Wh']:.4f} min, W_b={p['Wb']:.4f} min")
    print(f"Rs1(TP-IP1) = {res['Rs1']:.3f}")
    print(f"Rs2(TP-IP2) = {res['Rs2']:.3f}")
    print(f"Rs_min      = {res['Rs_min']:.3f}")

"""
05_designspace.py — デザインスペースの対話的 3D 可視化（plotly）

依存: plotly。numpy / 01_model / 04_optimize を呼ぶ。
plotly は Python in Excel 非対応のため、このスクリプトだけ通常 Python 環境専用。
（Excel 側は 04_optimize の結果を matplotlib 等で静止画にする）

出力:
  outputs/designspace_3d.html  — ブラウザで開ける対話的 3D 散布図（回転・ズーム可）
  outputs/designspace_3d.json  — 格子評価結果の軽量キャッシュ（任意）

グラフの見方:
  - 青〜赤の点 = デザインスペース（合格領域）。赤いほど Rs_min が高く分離余裕が大きい
  - 薄いグレーの点 = 不合格領域（どこで落ちているか輪郭がわかる）
  - 大きな★ = 推奨条件（最大余裕点）
  軸: X=T[℃]、Y=φ（ACN 分率）、Z=F[mL/min]
"""

import os
import numpy as np

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError as e:
    raise ImportError("plotly が必要です: pip install plotly") from e


# ──────────────────────────────
# 3D デザインスペースプロット
# ──────────────────────────────
def _wall_contour_surface(model_mod, peaks, factors, Vm, L_mm, rec,
                          which, n=41, day=0):
    """
    箱の1つの壁に貼る等高線サーフェスを作る。
    壁に垂直な因子を推奨値（rec）に固定し、残り2因子で Rs_min を計算、
    壁の位置（その因子の low 側）に平らな go.Surface として置く。

    which: "TP_floor"(F壁・T-φ面) / "TF_wall"(φ壁・T-F面) / "PF_wall"(T壁・φ-F面)
    """
    T_lo, T_hi = factors["T"]["low"], factors["T"]["high"]
    P_lo, P_hi = factors["phi"]["low"], factors["phi"]["high"]
    F_lo, F_hi = factors["F"]["low"], factors["F"]["high"]
    T_ax = np.linspace(T_lo, T_hi, n)
    P_ax = np.linspace(P_lo, P_hi, n)
    F_ax = np.linspace(F_lo, F_hi, n)

    if which == "TP_floor":          # T-φ 面、F=推奨値固定 → F の床に置く
        TT, PP = np.meshgrid(T_ax, P_ax)
        FF = np.full_like(TT, rec["F"])
        Rs = model_mod.separation(peaks, TT, PP, FF, Vm, L_mm, day=day)["Rs_min"]
        X, Y, Z = TT, PP, np.full_like(TT, F_lo)
    elif which == "TF_wall":         # T-F 面、φ=推奨値固定 → φ の壁に置く
        TT, FF = np.meshgrid(T_ax, F_ax)
        PP = np.full_like(TT, rec["phi"])
        Rs = model_mod.separation(peaks, TT, PP, FF, Vm, L_mm, day=day)["Rs_min"]
        X, Y, Z = TT, np.full_like(TT, P_lo), FF
    else:                            # "PF_wall": φ-F 面、T=推奨値固定 → T の壁に置く
        PP, FF = np.meshgrid(P_ax, F_ax)
        TT = np.full_like(PP, rec["T"])
        Rs = model_mod.separation(peaks, TT, PP, FF, Vm, L_mm, day=day)["Rs_min"]
        X, Y, Z = np.full_like(PP, T_lo), PP, FF

    return go.Surface(
        x=X, y=Y, z=Z, surfacecolor=Rs,
        colorscale="RdYlGn", cmin=0.0, cmax=3.0,
        showscale=False, opacity=0.85,
        contours=dict(
            x=dict(highlight=False), y=dict(highlight=False),
            z=dict(highlight=False),
        ),
        hovertemplate="Rs_min=%{surfacecolor:.2f}<extra>壁の等高線</extra>",
        name="壁等高線",
    )


def plot_designspace_3d(grid, rec, title="Design Space — 10-gingerol HPLC",
                        model_mod=None, peaks=None, factors=None,
                        Vm=None, L_mm=None, day=0):
    """
    04_optimize.evaluate_grid の結果と推奨条件 rec から
    対話的 3D 図を作成し plotly Figure を返す。

    中央: デザインスペースの点群（雲）。
    壁:   model_mod 等が渡されれば、各壁に「垂直因子＝推奨値固定」の Rs 等高線を投影。

    grid : evaluate_grid() の戻り値 dict（T, phi, F, Rs_min, pass_mask, ...）
    rec  : max_margin_point() の戻り値 dict（T, phi, F, margin）または None
    壁を描くには model_mod, peaks, factors, Vm, L_mm が必要（無ければ点群のみ）。
    """
    mask = grid["pass_mask"]
    T_pass = grid["T"][mask]
    P_pass = grid["phi"][mask]
    F_pass = grid["F"][mask]
    Rs_pass = grid["Rs_min"][mask]

    T_fail = grid["T"][~mask]
    P_fail = grid["phi"][~mask]
    F_fail = grid["F"][~mask]

    fig = go.Figure()

    # ── 各壁に等高線を投影（垂直な因子を推奨値に固定）──
    can_walls = (rec is not None and model_mod is not None and peaks is not None
                 and factors is not None and Vm is not None and L_mm is not None)
    if can_walls:
        for which in ("TP_floor", "TF_wall", "PF_wall"):
            fig.add_trace(_wall_contour_surface(
                model_mod, peaks, factors, Vm, L_mm, rec, which, day=day))

    # ── 不合格点（背景として薄く）──
    if len(T_fail) > 0:
        # 描画点を間引いて軽くする（多すぎると HTML が重い）
        step = max(1, len(T_fail) // 2000)
        fig.add_trace(go.Scatter3d(
            x=T_fail[::step], y=P_fail[::step], z=F_fail[::step],
            mode="markers",
            marker=dict(size=2, color="lightgray", opacity=0.15),
            name="不合格領域",
            hovertemplate="T=%{x:.1f}℃<br>φ=%{y:.3f}<br>F=%{z:.2f}<extra>不合格</extra>",
        ))

    # ── 合格点（Rs_min でグラデーション）──
    if len(T_pass) > 0:
        fig.add_trace(go.Scatter3d(
            x=T_pass, y=P_pass, z=F_pass,
            mode="markers",
            marker=dict(
                size=4,
                color=Rs_pass,
                colorscale="RdYlGn",       # 赤（ギリギリ）→黄→緑（余裕あり）
                cmin=0.0, cmax=3.0,        # 壁の等高線と共通スケール（色の整合）
                opacity=0.8,
                colorbar=dict(title="Rs_min", thickness=15, len=0.6),
                line=dict(width=0),
            ),
            name="デザインスペース（合格）",
            hovertemplate=(
                "T=%{x:.1f}℃<br>φ=%{y:.3f}<br>F=%{z:.2f}<br>"
                "Rs_min=%{marker.color:.2f}<extra>合格</extra>"
            ),
        ))

    # ── 推奨条件（最大余裕点）──
    if rec is not None:
        # 推奨点でのより詳細な情報をホバーに入れる
        hover_txt = (
            f"T={rec['T']:.1f}℃<br>"
            f"φ={rec['phi']:.3f}<br>"
            f"F={rec['F']:.2f} mL/min<br>"
            f"余裕={rec['margin']:.3f}"
        )
        fig.add_trace(go.Scatter3d(
            x=[rec["T"]], y=[rec["phi"]], z=[rec["F"]],
            mode="markers+text",
            marker=dict(
                size=14,
                color="gold",
                symbol="diamond",
                line=dict(color="darkorange", width=2),
            ),
            text=["推奨条件"],
            textposition="top center",
            textfont=dict(size=13, color="darkorange"),
            name="推奨条件（最大余裕点）",
            hovertemplate=hover_txt + "<extra>推奨条件</extra>",
        ))

    # ── レイアウト ──
    n_pass = int(mask.sum())
    n_total = mask.size
    subtitle = f"合格領域 {n_pass}/{n_total} 点 ({100*n_pass/n_total:.1f}%)"
    if rec is not None:
        subtitle += (f" | 推奨: T={rec['T']:.1f}℃ / φ={rec['phi']:.3f}"
                     f" / F={rec['F']:.2f} mL/min")

    fig.update_layout(
        title=dict(text=f"{title}<br><sup>{subtitle}</sup>", x=0.5),
        scene=dict(
            xaxis=dict(title="T [℃]"),
            yaxis=dict(title="φ (ACN 分率)"),
            zaxis=dict(title="F [mL/min]"),
            camera=dict(eye=dict(x=1.5, y=-1.8, z=0.8)),
        ),
        legend=dict(x=0.01, y=0.99, bordercolor="gray", borderwidth=1),
        margin=dict(l=0, r=0, t=80, b=0),
        width=900, height=700,
    )
    return fig


# ──────────────────────────────
# 2D スライス（F 固定の T-φ 等高線）— 補助図
# ──────────────────────────────
def plot_slice_2d(model_mod, peaks, factors, Vm, L_mm, criteria,
                  F_fixed=None, n=51, day=0):
    """
    F を固定した T-φ 面の Rs_min 等高線図（合格/不合格境界を直感的に見せる）。
    F_fixed=None のとき因子の center 値を使う。
    """
    if F_fixed is None:
        F_fixed = (factors["F"]["low"] + factors["F"]["high"]) / 2.0

    T_ax = np.linspace(factors["T"]["low"], factors["T"]["high"], n)
    P_ax = np.linspace(factors["phi"]["low"], factors["phi"]["high"], n)
    TT, PP = np.meshgrid(T_ax, P_ax)
    FF = np.full_like(TT, F_fixed)

    sep = model_mod.separation(peaks, TT, PP, FF, Vm, L_mm, day=day)
    Rs = sep["Rs_min"]
    tR_TP = sep["TP"]["tR"]
    tR_last = np.maximum.reduce([sep["TP"]["tR"], sep["IP1"]["tR"], sep["IP2"]["tR"]])

    # 3条件を全て満たす合否マスク（2値）
    pass_2d = (
        (Rs >= criteria["Rs_min"])
        & (tR_TP <= criteria["tR_TP_max"])
        & (tR_last <= criteria["tR_last_max"])
    ).astype(float)

    fig = go.Figure()
    # Rs_min の等高線
    fig.add_trace(go.Contour(
        x=T_ax, y=P_ax, z=Rs,
        colorscale="RdYlGn",
        contours=dict(
            start=0.5, end=3.5, size=0.25,
            showlabels=True, labelfont=dict(size=10),
        ),
        colorbar=dict(title="Rs_min", thickness=12, len=0.5, x=1.02),
        name="Rs_min",
    ))
    # 合格境界（白い太線）
    fig.add_trace(go.Contour(
        x=T_ax, y=P_ax, z=pass_2d,
        contours=dict(start=0.5, end=0.5, size=1),
        line=dict(color="white", width=3, dash="solid"),
        showscale=False,
        name="合格境界",
    ))

    fig.update_layout(
        title=f"T-φ 断面（F={F_fixed:.2f} mL/min 固定）",
        xaxis_title="T [℃]",
        yaxis_title="φ (ACN 分率)",
        width=600, height=480,
    )
    return fig


# ──────────────────────────────
# HTML 書き出し
# ──────────────────────────────
def save_html(fig, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fig.write_html(path, include_plotlyjs="cdn", full_html=True)
    print(f"  → 保存: {path}")


# ──────────────────────────────
# 動作確認
# ──────────────────────────────
def _load_module(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    here = os.path.dirname(__file__)
    model_mod = _load_module(os.path.join(here, "01_model.py"), "model01")
    opt_mod = _load_module(os.path.join(here, "04_optimize.py"), "opt04")

    Vm, L = 0.24, 100.0
    factors = {
        "T":   {"low": 40, "center": 50, "high": 60},
        "phi": {"low": 0.38, "center": 0.45, "high": 0.52},
        "F":   {"low": 0.4, "center": 0.6, "high": 0.8},
    }
    criteria = {"Rs_min": 2.0, "tR_TP_max": 7.5, "tR_last_max": 10.0}

    peaks = model_mod.example_peaks()
    for name in ("IP1", "TP", "IP2"):
        peaks[name]["e"] = 80.0    # クロスオーバーが起きる例パラメータ

    print("格子評価中...")
    grid, rec = opt_mod.optimize(model_mod, peaks, factors, Vm, L, criteria, n=25)

    print(f"合格点: {int(grid['pass_mask'].sum())}/{grid['pass_mask'].size} 点")
    if rec:
        print(f"推奨条件: T={rec['T']:.1f}℃ / φ={rec['phi']:.3f} / F={rec['F']:.2f} mL/min")
        print(f"余裕（正規化）: {rec['margin']:.3f}")

    print("\n3D グラフを生成中...")
    fig3d = plot_designspace_3d(grid, rec, model_mod=model_mod, peaks=peaks,
                                factors=factors, Vm=Vm, L_mm=L)
    save_html(fig3d, "outputs/designspace_3d.html")

    print("2D スライスを生成中（F=中水準固定）...")
    fig2d = plot_slice_2d(model_mod, peaks, factors, Vm, L, criteria,
                          F_fixed=factors["F"]["center"])
    save_html(fig2d, "outputs/designspace_slice_2d.html")

    print("\n完了。ブラウザで outputs/ 内の HTML を開いてください。")

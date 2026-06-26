"""
05_designspace.py — デザインスペースの対話的 3D 可視化（plotly）

依存: plotly。numpy / 01_model / 04_optimize を呼ぶ。
plotly は Python in Excel 非対応のため、このスクリプトだけ通常 Python 環境専用。
（Excel 側は 04_optimize の結果を matplotlib 等で静止画にする）

出力:
  outputs/designspace_3d.html  — ブラウザで開ける対話的 3D 散布図（回転・ズーム可）
  outputs/designspace_3d.json  — 格子評価結果の軽量キャッシュ（任意）

グラフの見方:
  - 緑〜赤の雲 = デザインスペース（合格領域）。緑ほど Rs_min が高く分離余裕が大きい
    （既定は go.Volume の無段階ボリューム。cloud_style="scatter" で散布点にも切替可）
  - 壁の線 = Rs_min の等高線（太い黒線が Rs=2.0 の合格境界）
  - 金のひし形 = 推奨条件（最大余裕点）
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
WALL_LEVELS = [1.0, 1.5, 2.0, 2.5, 3.0]   # 壁に描く Rs_min の等高線レベル（既定）


def build_levels(step, lo=0.5, hi=3.5):
    """Rs の等高線レベルを刻み step で作る。合格境界 2.0 を必ず含める。"""
    step = max(float(step), 0.05)
    kmin = int(np.floor((lo - 2.0) / step))
    kmax = int(np.ceil((hi - 2.0) / step))
    levels = [round(2.0 + k * step, 6) for k in range(kmin, kmax + 1)]
    return [v for v in levels if lo - 1e-9 <= v <= hi + 1e-9]


def _level_color(level, lo=0.0, hi=3.0):
    """Rs レベル → RdYlGn 上の色（赤=低→緑=高）。plotly のサンプラを使う。"""
    from plotly.colors import sample_colorscale
    t = (level - lo) / (hi - lo)
    return sample_colorscale("RdYlGn", [max(0.0, min(1.0, t))])[0]


def _wall_contour_lines(model_mod, peaks, factors, Vm, L_mm, rec,
                        which, n=81, day=0, wall_side="low", levels=None):
    """
    箱の1つの壁に「等高線（ライン）」を描く Scatter3d トレース群を返す。
    壁に垂直な因子を推奨値（rec）に固定し、残り2面内因子で Rs_min を計算、
    matplotlib で等値線の座標を取り出して壁の平面に 3D ラインとして配置する。
    Rs=2.0（合格境界）は太線で強調。

    which: "TP_floor"(F壁・T-φ面) / "TF_wall"(φ壁・T-F面) / "PF_wall"(T壁・φ-F面)
    wall_side: "low"=下限側の壁／"high"=上限側の壁（デザインスペースに近い面を選べる）
    """
    import matplotlib
    matplotlib.use("Agg")            # 画面を使わず座標計算だけ
    import matplotlib.pyplot as plt

    T_lo, T_hi = factors["T"]["low"], factors["T"]["high"]
    P_lo, P_hi = factors["phi"]["low"], factors["phi"]["high"]
    F_lo, F_hi = factors["F"]["low"], factors["F"]["high"]
    T_ax = np.linspace(T_lo, T_hi, n)
    P_ax = np.linspace(P_lo, P_hi, n)
    F_ax = np.linspace(F_lo, F_hi, n)
    hi = (wall_side == "high")       # True なら上限側の壁に貼る

    # 面内2軸 (a_ax, b_ax) で Rs を計算し、(a,b)→3D への射影関数 to_xyz を決める
    if which == "TP_floor":          # T-φ 面、F=推奨値固定 → F の壁に置く
        a_ax, b_ax = T_ax, P_ax
        AA, BB = np.meshgrid(a_ax, b_ax)
        Rs = model_mod.separation(peaks, AA, BB, rec["F"], Vm, L_mm, day=day)["Rs_min"]
        F_wall = F_hi if hi else F_lo
        to_xyz = lambda a, b: (a, b, np.full_like(a, F_wall))
        wall_name = f"F壁(F={rec['F']:.2f})"
    elif which == "TF_wall":         # T-F 面、φ=推奨値固定 → φ の壁に置く
        a_ax, b_ax = T_ax, F_ax
        AA, BB = np.meshgrid(a_ax, b_ax)
        Rs = model_mod.separation(peaks, AA, rec["phi"], BB, Vm, L_mm, day=day)["Rs_min"]
        P_wall = P_hi if hi else P_lo
        to_xyz = lambda a, b: (a, np.full_like(a, P_wall), b)
        wall_name = f"φ壁(φ={rec['phi']:.3f})"
    else:                            # "PF_wall": φ-F 面、T=推奨値固定 → T の壁に置く
        a_ax, b_ax = P_ax, F_ax
        AA, BB = np.meshgrid(a_ax, b_ax)
        Rs = model_mod.separation(peaks, rec["T"], AA, BB, Vm, L_mm, day=day)["Rs_min"]
        T_wall = T_hi if hi else T_lo
        to_xyz = lambda a, b: (np.full_like(a, T_wall), a, b)
        wall_name = f"T壁(T={rec['T']:.1f})"

    # matplotlib で等値線の座標（segments）を取得（描画はしない）
    use_levels = WALL_LEVELS if levels is None else levels
    fig_tmp, ax_tmp = plt.subplots()
    cs = ax_tmp.contour(AA, BB, Rs, levels=use_levels)
    traces = []
    for level, segs in zip(cs.levels, cs.allsegs):
        if not segs:
            continue
        is_pass = abs(level - 2.0) < 1e-9
        color = "black" if is_pass else _level_color(level)
        width = 6 if is_pass else 2.5
        for seg in segs:
            a, b = seg[:, 0], seg[:, 1]
            x, y, z = to_xyz(a, b)
            traces.append(go.Scatter3d(
                x=x, y=y, z=z, mode="lines",
                line=dict(color=color, width=width),
                name=(f"{wall_name} Rs={level:g}"
                      + ("（合格境界）" if is_pass else "")),
                showlegend=False,
                hovertemplate=f"Rs_min={level:g}<extra>{wall_name}</extra>",
            ))
    plt.close(fig_tmp)
    return traces


def _designspace_volume_trace(grid, criteria_Rs=2.0, surface_count=30):
    """
    デザインスペースを「無段階の雲」として描く go.Volume トレース。
    合格領域だけを残し（不合格点の値は 0 にして isomin で消す）、Rs_min で着色。
    格子は make_grid の meshgrid(indexing='ij') 由来の規則格子である前提。
    滑らかさ＝格子の細かさ（呼び出し側 n）× surface_count（等値層の枚数）。
    """
    mask = grid["pass_mask"]
    # 合格点は Rs_min、不合格点は 0（isomin で描画対象外にする）
    value = np.where(mask, grid["Rs_min"], 0.0)
    rs_max = float(grid["Rs_min"][mask].max()) if mask.any() else 3.0
    return go.Volume(
        x=grid["T"], y=grid["phi"], z=grid["F"], value=value,
        isomin=criteria_Rs,                 # 合格境界（Rs≥2.0）から上だけ雲にする
        isomax=rs_max,
        opacity=0.10,                       # 半透明（無段階の靄）
        opacityscale="uniform",             # 層ごとの不透明度を均一にして靄を滑らかに
        surface_count=surface_count,        # 等値層の枚数（多いほど滑らか）
        colorscale="RdYlGn", cmin=0.0, cmax=3.0,
        caps=dict(x_show=False, y_show=False, z_show=False),
        colorbar=dict(title="Rs_min", thickness=15, len=0.6),
        name="デザインスペース（雲）",
        hovertemplate=("T=%{x:.1f}℃<br>φ=%{y:.3f}<br>F=%{z:.2f}<br>"
                       "Rs_min=%{value:.2f}<extra>合格</extra>"),
    )


def _auto_wall_side(grid, factor_key):
    """合格領域がどちら寄りかで壁の置き場所を自動判定。
    合格点のその因子の重心が範囲中央より上なら上限側、下なら下限側に壁を置く
    （等高線の壁をデザインスペースの近くに来させて見やすくする）。"""
    mask = grid["pass_mask"]
    if not mask.any():
        return "low"
    vals = grid[factor_key][mask]
    mid = 0.5 * (grid[factor_key].min() + grid[factor_key].max())
    return "high" if vals.mean() >= mid else "low"


def plot_designspace_3d(grid, rec, title="Design Space — 10-gingerol HPLC",
                        model_mod=None, peaks=None, factors=None,
                        Vm=None, L_mm=None, day=0, cloud_style="volume",
                        wall_side="auto", contour_step=0.5, surface_count=30):
    """
    04_optimize.evaluate_grid の結果と推奨条件 rec から
    対話的 3D 図を作成し plotly Figure を返す。

    中央: デザインスペースの雲。cloud_style で表現を選ぶ:
      "volume"  … 無段階の半透明ボリューム（go.Volume。WebGL 必須）
      "scatter" … 合格点の散布点（go.Scatter3d）
    壁:   model_mod 等が渡されれば、各壁に「垂直因子＝推奨値固定」の Rs 等高線を投影。
    wall_side: 等高線の壁の置き場所。文字列で全壁一括、または因子ごとの dict で個別指定。
      文字列: "auto"（合格領域に近い面へ自動）／"low"（下限側）／"high"（上限側）
      dict  : {"T": .., "phi": .., "F": ..} 各値は "auto"/"low"/"high"。
              F壁は床(low)/天井(high)、T壁・φ壁は手前(low)/奥(high) に対応。

    grid : evaluate_grid() の戻り値 dict（T, phi, F, Rs_min, pass_mask, ...）
    rec  : max_margin_point() の戻り値 dict（T, phi, F, margin）または None
    壁を描くには model_mod, peaks, factors, Vm, L_mm が必要（無ければ雲のみ）。
    """
    mask = grid["pass_mask"]
    Rs_th = 2.0

    fig = go.Figure()

    # ── 各壁に等高線を投影（垂直な因子を推奨値に固定）──
    # which と「その壁に垂直な因子キー」の対応（auto 配置の判定に使う）
    perp_key = {"TP_floor": "F", "TF_wall": "phi", "PF_wall": "T"}

    def _resolve_side(perp):
        # wall_side が dict ならその因子の指定、文字列なら全壁共通
        spec = wall_side.get(perp, "auto") if isinstance(wall_side, dict) else wall_side
        return _auto_wall_side(grid, perp) if spec == "auto" else spec

    can_walls = (rec is not None and model_mod is not None and peaks is not None
                 and factors is not None and Vm is not None and L_mm is not None)
    contour_levels = build_levels(contour_step)
    if can_walls:
        for which in ("TP_floor", "TF_wall", "PF_wall"):
            side = _resolve_side(perp_key[which])
            for tr in _wall_contour_lines(
                    model_mod, peaks, factors, Vm, L_mm, rec, which,
                    day=day, wall_side=side, levels=contour_levels):
                fig.add_trace(tr)

    # ── デザインスペースの雲 ──
    if mask.any():
        if cloud_style == "volume":
            fig.add_trace(_designspace_volume_trace(grid, criteria_Rs=Rs_th,
                                                    surface_count=surface_count))
        else:
            fig.add_trace(go.Scatter3d(
                x=grid["T"][mask], y=grid["phi"][mask], z=grid["F"][mask],
                mode="markers",
                marker=dict(
                    size=4, color=grid["Rs_min"][mask],
                    colorscale="RdYlGn", cmin=0.0, cmax=3.0, opacity=0.8,
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
            mode="markers",
            marker=dict(
                size=7,
                color="#111111",                 # 締まった黒のドット
                symbol="circle",
                line=dict(color="white", width=2),  # 白ハロで背景から浮かせる
            ),
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

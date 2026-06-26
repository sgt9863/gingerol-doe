# SKILL.md（骨格）— HPLC 条件最適化 ＆ デザインスペース3D

> これは将来 `.claude/skills/` に切り出す skill の下書き。
> いまは見出しだけ。各 scripts/ を実装するたびに該当節を埋める。

## このskillは何をするか
HPLC のカラム温度・流速・溶媒比の3条件を、メカニズムモデル（保持＝ファントホッフ×LSS、幅＝van Deemter）でフィットし、分離度 Rs を最大化・かつブレに強い**デザインスペース**を3Dで可視化する。

## いつ使うか
夾雑ピークに挟まれた目的成分の HPLC 条件を、実験計画法で頑健に最適化したいとき。

## 入力
- `config.yaml`（因子範囲・ピーク定義・Vm・合格条件）… [config.example.yaml](config.example.yaml) 参照
- 実測データ（各条件での3ピークの保持時間・ピーク幅）

### config.yaml に含めるべき項目（水準設定関連）

```yaml
peaks:
  target: TP               # 目的ピーク名
  interfering: [IP1, IP2]  # 夾雑ピーク名（溶出順不問）

factors:
  T:   {low: 40,   center: 50,   high: 60,   unit: "°C"}
  phi: {low: 0.38, center: 0.45, high: 0.52, unit: "ACN fraction"}
  F:   {low: 0.4,  center: 0.6,  high: 0.8,  unit: "mL/min"}
  # F の水準は t_R = Vm*(1+k)/F の反比例で決まる
  # 実測後の更新式: F_low = Vm*(1+k_center)/tR_high, F_high = Vm*(1+k_center)/tR_low

column:
  Vm: 0.24         # カラム死容量 [mL]。幾何推算 Vm ≈ 0.68 × π r² L（2.1×100mm）
                   # 厳密化するなら不保持物質(ウラシル等)注入で t_0 実測 → Vm = t_0 × F
  length_mm: 100   # カラム長
  id_mm: 2.1       # 内径
  dp_um: 1.7       # 粒径
  porosity: 0.68   # 全空隙率（BEH 全多孔性の概算値）
  peak_width: half_height  # ピーク幅の定義（半値幅 W_h、N = 5.54·(t_R/W_h)²）

acceptance_criteria:
  Rs_min: 2.0      # min{Rs1, Rs2} の下限
  tR_TP_max: 7.5   # 目的ピーク保持時間の上限 [分]
  tR_IP2_max: 10.0 # 最遅溶出ピーク保持時間の上限 [分]（洗浄ステップ開始時間）

design:
  type: ccd            # 初回は中心複合計画
  center_points: 6     # 中心点繰り返し（純誤差推定・湾曲検定用）
  budget_per_day: 50   # 1日あたり実験本数上限
  run_time_min: 22     # 1注入の所要時間 [分]（洗浄込み）
  blocking: true       # CCD と D最適を別日に実施 → 日間変動をブロック項で補正
  augment: d_optimal   # 2日目以降の追加実験は D最適
```

## 手順（scripts の段階）
1. **モデル設計** — `scripts/01_model.py`（未実装）
   - 保持 `ln k = a + b/T + c·φ (+ δ·day)`、幅 `W(T,φ,F)` を各ピーク3本
   - 別日実施に備え day をブロック項として持つ
2. **実験計画生成** — `scripts/02_design.py`（CCD → D最適 逐次、別日ブロッキング）（未実装）
   - Day1: CCD（頂点8+軸6+中心6=20本）/ Day2: D最適 augment + 中心点3本（橋渡し）
3. **フィット** — `scripts/03_fit.py`（k(T,φ) ×3、W(T,φ,F) ×3、day オフセット推定）（未実装）
4. **最適化** — `scripts/04_optimize.py`（Rs=min{Rs1,Rs2} 最大／デザインスペース判定）（未実装）
5. **3D描画** — `scripts/05_designspace.py`（plotly html）（未実装）
6. **Web アプリ** — `app.py`（Streamlit。01〜05 を呼ぶだけの薄い入口）（未実装）

## 出力
- 推奨条件（最も頑健な点）と、Rs≥閾値のデザインスペース 3D プロット（plotly html）
- Excel 側プレビュー：matplotlib の静止画（3D / 2D 等高線）

## 実行環境：Excel と Streamlit の両対応
中核ロジックを numpy 系のみで書くことで、2つの入口を1つのロジックで支える。

| 入口 | 用途 | 3D 可視化 |
|------|------|----------|
| **Python in Excel** | Excel に馴染んだ作業・手元計算 | matplotlib 静止画 |
| **Streamlit Web アプリ**（`app.py`） | ボタン操作・報告で見せる | plotly（回転可）|

- **依存ライブラリ制約**：中核ロジック（scripts/01〜04）は numpy/scipy/statsmodels/pandas のみで書く
  → 同じコードを「モジュール import」「Excel セルに貼付」「Streamlit から呼ぶ」全てで使える
  → plotly は scripts/05 と Streamlit 専用
- Python in Excel の制約（自作モジュール import 不可・ローカルファイル出力不可）は
  Streamlit 側で解消される（対話的3D・ファイルDLが可能）
- Streamlit 起動：手元PCで `streamlit run app.py`（または Community Cloud に配置）

## 再利用のための分離方針
- **変わる部分** → `config.yaml`（因子名・範囲・ピーク数・Vm・合格条件・設計設定）
- **固定ロジック** → `scripts/`（数理モデル・計画生成・フィット・最適化・描画）

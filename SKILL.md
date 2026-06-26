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
  target: TP          # 目的ピーク名
  interfering: [IP1, IP2]  # 夾雑ピーク名

factors:
  T:  {low: 40, center: 50, high: 60, unit: "°C"}
  phi: {low: 0.38, center: 0.45, high: 0.52, unit: "ACN fraction"}
  F:   {low: null, center: null, high: null, unit: "mL/min"}  # 指摘6で決定

acceptance_criteria:
  Rs_min: 2.0          # min{Rs1, Rs2} の下限
  tR_TP_max: 7.5       # 目的ピーク保持時間の上限（分）

# 水準範囲の最終確定フロー：
#   1. 指摘7の実測後にモデルをフィット
#   2. tR_TP_max の等高線を T-phi 平面に描く
#   3. 等高線を超える領域を探索範囲から除外して因子範囲を確定
```

## 手順（scripts の段階）
1. **モデル設計** — `scripts/01_model.py`（未実装）
2. **実験計画生成** — `scripts/02_design.py`（CCD → D最適 逐次）（未実装）
3. **フィット** — `scripts/03_fit.py`（k(T,φ) ×3、W(T,φ,F) ×3）（未実装）
4. **最適化** — `scripts/04_optimize.py`（Rs=min{Rs1,Rs2} 最大／デザインスペース判定）（未実装）
5. **3D描画** — `scripts/05_designspace.py`（plotly html）（未実装）

## 出力
- 推奨条件（最も頑健な点）と、Rs≥閾値のデザインスペース3Dプロット（html）

## 再利用のための分離方針
- **変わる部分** → `config.yaml`（因子名・範囲・ピーク数・Vm・Rs閾値）
- **固定ロジック** → `scripts/`（数理モデル・計画生成・フィット・最適化・描画）

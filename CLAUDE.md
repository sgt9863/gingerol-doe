# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

HPLC 条件最適化プロジェクト。漢方中の **10-gingerol（= TP, Target Peak）** を、前後の夾雑ピーク
（**IP1 / IP2**, Interfering Peak）から頑健に分離する条件を統計的に求め、**デザインスペース**
（ブレに強い条件領域）を可視化する。最終的に手順を再利用可能な skill に切り出す。

現状は **設計フェーズ確定・実装も一巡完了**。config.example.yaml ＋ scripts/01〜05 ＋ app.py
（Streamlit・タブ式の正規フロー）が合成データで動作確認済み。残りは skill 化（`.claude/skills/` への
切り出し）と SKILL.md の記述。実データは社外（会社）にあり本リポジトリには無いため、
**合成（ダミー）データで動作確認**してから引き渡す前提。

## 進め方の制約（重要）

- **設計を固めてから実装する**方針。設計判断は対話で1つずつ詰めてきた経緯がある。
  勝手に実装を先走らせない。新しい判断が要る時は決め打ちせず確認する。
- ユーザーは**統計・分析化学とも初級〜中級**（統計検定2級レベル）、**IT エンジニアではない**。
  - 専門用語はかみ砕く。数式は使ってよいが**各記号を必ず説明**する。
  - git / GitHub / クラウド操作は具体的に手順案内する。PR は Claude 側で作成・マージしてよい
    （ユーザーから「じゃんじゃんマージで」と承認済み。MCP の `merge_pull_request` を使う）。
- **作業ブランチは `claude/handoff-md-point-2-rkew9g`**。ここで開発し、push 後 PR を作って main にマージ。

## 設計判断はここを読む（実装前に必読）

1. `references/decisions.md` — **確定した全設計判断の台帳**。指摘1〜7＋Excel連携＋フロント方針。
   末尾の更新履歴で経緯を追える。**新しい確定事項は必ずここに追記**してから実装に入る。
2. `references/handoff.md` — ローカル→クラウドの引き継ぎメモ（出発点）。
3. `references/literature.md` — 仮定モデルの根拠文献集（社内報告用）。
4. `SKILL.md` — skill 化の骨格と `config.yaml` 雛形。実装が進むたびに該当節を埋める。

## 数理モデルの要点（コードの土台）

- **保持係数 k は T と φ のみで決まる。F は k を変えない。**
  - 保持：`ln k = a + b/T[K] + c·φ (+ d·φ²)` を3ピーク分（ファントホッフ×LSS/Snyder）
  - 保持時間復元：`t_R = (V_m/F)(1+k)`、ボイド時間 `t_0 = V_m/F`
  - 幅：`W(T, φ, F)` を3ピーク分（F が主役、van Deemter）。`W = 4·t_R/√N`、`N = 5.54·(t_R/W_h)²`
- **分離度はクロスオーバー対応のため化合物同一性で定義**（溶出順でなく）：
  `Rs1 = 2·|t_R(TP) − t_R(IP1)| / (W_TP + W_IP1)`、Rs2 も同様。最適化目標は `min{Rs1, Rs2}`。
- **デザインスペース**：`min{Rs1,Rs2} ≥ 2.0` かつ `t_R(TP) ≤ 7.5min`。
  （`max(t_R 全3本) ≤ 10min` は**データ取り段階の洗浄前制約**でありデザインスペース合否には含めない。
  運用上課したい場合のみ config の `tR_last_max` を数値に。既定 null）。
  この領域内で**境界からの最短距離が最大の点**（最大余裕点）を推奨条件にする（ICH Q8）。
  境界は「合格条件の崖」＋「因子範囲の端」（外挿回避）。
- **実験計画**：Day1 に CCD（頂点8+軸6+中心6=20本）→ Day2 に D最適 augment。
  別日のため**日をブロック項**にする（`+ δ·day`）。Day2 冒頭に中心点3本で日間差を橋渡し。
- `V_m` は幾何推算 `≈ 0.66 × π r² L ≈ 0.23 mL`（2.1×100mm, 空隙率0.66＝Waters推奨）で足りる。厳密化は不保持物質注入。

## 実装アーキテクチャ（実装済み）

段階別スクリプト。各段の責務は `scripts/README.md` と `SKILL.md`「手順」節を参照。

```
config.example.yaml  設定の実体（因子範囲・ピーク定義・Vm・合格条件・design設定）— 実装済み
scripts/01_model.py  数理モデル（k, W, Rs）          — 実装済み
scripts/02_design.py CCD生成＋ブロッキング＋D最適     — 実装済み
scripts/03_fit.py    フィット（保持3・幅3・day推定）  — 実装済み
scripts/04_optimize.py デザインスペース判定＋最大余裕点 — 実装済み
scripts/05_designspace.py plotly 3D（雲＋等高線）      — 実装済み
app.py               Streamlit Web アプリ（薄い入口） — 実装済み
```

### 依存ライブラリ制約（設計の肝）

**中核ロジック（scripts/01〜04）は numpy / scipy / statsmodels / pandas のみで書く。**
理由：同じコードを「通常環境で import」「Python in Excel のセルに貼付」「Streamlit から呼ぶ」の
3経路すべてで使い回すため（二重管理回避）。**plotly は scripts/05 と app.py 専用**。

Python in Excel は自作モジュール import 不可・ローカルファイル出力不可・上記既定ライブラリのみ、
という制約がある。対話的3D・ファイルDLが要る場面は Streamlit 側で担保する。

### 再利用（skill化）の分離方針

- **変わる部分** → `config.yaml`（因子名・範囲・ピーク数・Vm・合格条件・design設定）
- **固定ロジック** → `scripts/`
- 10-gingerol の実ケースを最後まで通し、動いたら共通部分を `.claude/skills/` に切り出す。

## フォルダ構成

- `data/` — 入力テンプレ・実測データ（xlsx/csv）。`runs.xlsx`（各条件と3ピークの t_R・W_h）等。空。
- `outputs/` — 結果（推奨条件・3D html・フィット残差/R²）。空。
- `references/` — 設計台帳・引き継ぎ・文献（上記「設計判断はここを読む」）。
- `scripts/` — 固定ロジック（01〜05 実装済み）。

## フロントエンド

Excel と Streamlit の**両対応**。中核ロジックは共通、入口だけ2つ。

- **Python in Excel**：手元計算・データ入力。3D は matplotlib 静止画。
- **Streamlit**（`app.py`）：`streamlit run app.py` で起動。報告用の対話的 plotly 3D。

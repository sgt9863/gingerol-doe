---
title: HPLC デザインスペース最適化（10-gingerol）
tags: [project, HPLC, 分析化学, 実験計画法, Python, Streamlit]
status: 実装一巡完了・skill化完了
created: 2026-06-27
---

# HPLC デザインスペース最適化（10-gingerol）

> [!summary] 一言で
> 漢方中の **10-gingerol（TP）** を前後の夾雑ピーク（IP1/IP2）から頑健に分離する HPLC 条件を、
> 物理化学のメカニズムモデル＋実験計画法で求め、**デザインスペース**（ブレに強い条件領域）を 3D 可視化する。

## 目的
- カラム温度 **T**・移動相 ACN 比率 **φ**・流速 **F** の3条件を最適化
- 分離度 `min{Rs1, Rs2} ≥ 2.0` かつ `t_R(TP) ≤ 7.5分` を満たす領域＝デザインスペース
- その中で**境界から最も遠い点（最大余裕点）**を推奨条件に（ICH Q8）

## 数理モデル（メカニズムベース）
- 保持（係数について線形）：`ln k = a + b/T_K + c·φ + d·φ² + e·φ/T_K (+ δ·day)`
  - ファントホッフ（温度）× LSS/Snyder（溶媒）。`e·φ/T_K` が交互作用＝**クロスオーバー**の源
- 保持時間：`t_R = (V_m/F)(1+k)`（ここで指数が入るので t_R は係数について**非線形**）
- 幅：van Deemter `H = A + B/u + C·u`、`N = 5.54·(t_R/W_h)²`、`W_b = 4·t_R/√N`
- 分離度：`Rs = 2·|Δt_R|/(W_b1+W_b2)`（絶対値でクロスオーバー対応）

## 実装構成
```
config.example.yaml  設定（因子範囲・ピーク・カラム・合格条件・design）
scripts/01_model.py  数理モデル（k, W, Rs）         numpy
scripts/02_design.py CCD＋ブロッキング＋D最適(A/B)   numpy/pandas
scripts/03_fit.py    フィット（保持3・幅3・day）     statsmodels
scripts/04_optimize.py デザインスペース＋最大余裕点＋外挿  scipy(cKDTree)
scripts/05_designspace.py 3D（雲＋等高線・Viridis）   plotly/matplotlib
app.py               Streamlit（タブ式の正規フロー）
```
- **依存制約**：中核(01〜04)は numpy/scipy/statsmodels/pandas のみ（Python in Excel 互換）。plotly は 05・app 専用
- **アプリのフロー**：①CCD計画→②Day1フィット→③D最適augment→④最終解析（＋デモ）。各段で Excel 雛形DL

## 主要な設計判断（抜粋）
- D最適は2基準：**(A) 係数精度**（線形・係数非依存・頑健）／**(B) Rs境界標的**（局所D最適・Day1フィット要）
- 合格条件から `max(t_R 全3本)` を除外（データ取り段階の制約でデザインスペース合否ではない）
- V_m はカラム寸法プルダウンから幾何推算（空隙率 **0.66**＝Waters 推奨、≈0.23 mL）
- 外挿オプション（評価格子だけ拡張・推奨は検証範囲内のみ・検証範囲を破線の箱で表示）
- 可視化：Viridis、デザインスペース内に色を引き伸ばし、等高線5本固定、自動回転ボタン＋GIF書き出し

## 再利用（skill化）
- `.claude/skills/hplc-design-space/` に固定ロジック一式＋config テンプレ＋frontmatter付き SKILL.md を自己完結で切り出し済み
- **別化合物へは `config.yaml` の差し替えだけで転用**

## 状態・残タスク
- 設計確定・実装一巡・skill化 完了。合成（ダミー）データで動作確認済み
- 実データは会社にあり本リポジトリには無い → 会社で `runs.xlsx` を取得しアップロードすれば本番フロー
- 社内報告用：[[理論構築の流れ]]（統計2級レベル解説）＋ 文献リスト（DOI/URL）作成済み

## 関連ノート
- [[理論構築の流れ]]
- [[私について（作業メモ）]]

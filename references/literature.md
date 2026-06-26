# 仮定モデルの根拠文献集（社内報告用）

本プロジェクトの数理モデルは「2次回帰の当てはめ」ではなく、HPLC のメカニズム（物理化学）に基づく。
各構成要素がどの確立した理論に由来するかを、引用可能な文献とともに整理する。

> 注：URL 付きは本セッションで実在を確認した文献。末尾の「基礎文献（古典）」は分野の定番で、
> 正式な巻号・ページは報告書作成時に各自データベースで確認のこと。

---

## 1. 保持の温度依存：ファントホッフ式 `ln k = a + b/T`

**自モデルの対応**：保持係数 k の温度項。`ln k = a + b/T[K] + c·φ` の `b/T` 部分。

- 根拠：ΔH°・ΔS° が温度に依存しないと仮定すると ln k は 1/T に対して直線になる（ファントホッフプロット）。
- 注意：実際には非線形になる場合がある（溶質が複数の形を取る、複数の相互作用が混在するなど）。
  逆相での疎水性相互作用が支配的な場合は直線で近似してよい。必要なら 2次項で補正。

文献：
- Sources of Nonlinear van't Hoff Temperature Dependence in HPLC, *ACS Omega* (2019).
  https://pubs.acs.org/doi/10.1021/acsomega.9b02689 ／ https://pmc.ncbi.nlm.nih.gov/articles/PMC6882149/
  → 直線が成り立つ条件・崩れる原因（2次近似でよく合うこと）を論じている。我々が「必要なら +d·φ² / 高次項」とした根拠。

---

## 2. 保持の溶媒依存：LSS／Snyder モデル `ln k = ln k_w − S·φ`

**自モデルの対応**：保持係数 k の溶媒項。`ln k = a + b/T + c·φ` の `c·φ` 部分（c が −S に相当）。

- 根拠：逆相 HPLC では log k と有機溶媒の体積分率 φ が広い範囲で直線関係（線形溶媒強度＝LSS）。
- 切片 log k_w と傾き S は系の性質で、回帰式で記述できる。

文献：
- Poole & Atapattu, "Analysis of the Solvent Strength Parameter (Linear Solvent Strength Model)
  for Isocratic Separations in RP-LC," *J. Chromatogr. A* (2022).
  https://www.sciencedirect.com/science/article/abs/pii/S0021967322003466
  → アイソクラティック条件での LSS 傾き・切片の意味づけ。我々の現行アイソクラティック条件に直結。
- Guillarme et al., "A simple mathematical treatment for predicting LSS behavior...," *J. Sep. Sci.* (2022).
  https://pubmed.ncbi.nlm.nih.gov/35562641/
  → LSS の数理的な扱い方の実例。

---

## 3. ピーク幅／効率：van Deemter 式 `H = A + B/u + C·u`

**自モデルの対応**：幅モデル `W(T, φ, F)`。流速 F（線速度 u）が幅に効く部分。
理論段数 N を介して `W = 4·t_R/√N` で幅に戻す案の土台。

- 根拠：段高 H を 渦拡散(A)・縦拡散(B/u)・物質移動抵抗(C·u) の和で表す。最適流速で H が最小。
- UPLC（粒径 <2µm）では H が小さく、広い流速範囲で効率が保たれる（我々の 1.7µm カラムに該当）。

文献：
- van Deemter Equation, *ScienceDirect Topics*（総説的解説）
  https://www.sciencedirect.com/topics/agricultural-and-biological-sciences/van-deemter-equation
- "Comparison of equations describing band broadening in HPLC," *J. Chromatogr. A* (2003).
  https://www.sciencedirect.com/science/article/abs/pii/S0021967303020636
  → van Deemter 系の各式の比較。幅モデルの式選定の根拠。

---

## 4. 分離度の定義：`Rs = 2·|Δt_R| / (W1 + W2)`

**自モデルの対応**：Rs1（TP–IP1）/ Rs2（TP–IP2）の計算式。絶対値でクロスオーバー対応（指摘3）。

- 標準的な分離度の定義。教科書記載の基本式（下記「基礎文献」参照）。

---

## 5. デザインスペース：ICH Q8(R2)

**自モデルの対応**：合格領域（Rs≥2.0 かつ t_R 制約）＝デザインスペースの定義、
および境界から最も遠い点を採る考え方（指摘2）。

- 定義：「品質を保証できると実証された入力変数・工程パラメータの多次元的な組合せと相互作用の範囲」。
- 承認後はデザインスペース内での操作は変更とみなされない（運用の柔軟性）。

文献：
- ICH Q8(R2) Pharmaceutical Development（EMA 掲載の科学ガイドライン）
  https://www.ema.europa.eu/en/ich-q8-r2-pharmaceutical-development-scientific-guideline

---

## 6. 実験計画法：CCD（応答曲面法）→ D最適

**自モデルの対応**：指摘5の実験計画（CCD 20本 → D最適 augment、別日ブロッキング）。

- CCD（中心複合計画）＋応答曲面法は HPLC 条件最適化の定番。温度・有機溶媒比などを
  系統的に最適化し、デザインスペース／頑健性を評価する AQbD の枠組みで広く使われる。

文献：
- "Central Composite Design for Response Surface Methodology and Its Application in Pharmacy" (2021).
  https://www.researchgate.net/publication/348910011
- AQbD による RP-HPLC 法開発例（カラム温度・有機溶媒比等を CCD で評価）, *PMC7070322*.
  https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7070322/
  → 我々と同種の因子（温度・溶媒比）を CCD で最適化した実例。

---

## 7. 対象化合物：gingerol の HPLC 分析（背景・現実性の裏づけ）

**自モデルの対応**：TP=10-gingerol、夾雑 IP1/IP2 の分離という課題設定の現実性。

- gingerol 類（6-/8-/10-gingerol, 6-shogaol）は C18/C8 逆相・ACN 系移動相で分離するのが定番。
  我々の C8・水:ACN 条件は文献の常套と整合。

文献：
- "HPLC analysis of 6-, 8-, 10-gingerol and 6-shogaol in ginger-containing supplements...,"
  *J. Chromatogr. B* (2007). https://pubmed.ncbi.nlm.nih.gov/17561453/
- "Validation of RP-HPLC for simultaneous determination of 6-,8-,10-gingerols and 6-shogaol,"
  *Int. J. Pharm. Pharm. Sci.* https://journals.innovareacademics.in/index.php/ijpps/article/view/36446
  → C8 逆相・ACN 系での gingerol 分離。我々の条件設定の妥当性の傍証。

---

## 基礎文献（古典・教科書／正式引用は各自確認）

これらは分野の定番で、報告書では一次資料として引くと説得力が増す。

- **L. R. Snyder, J. J. Kirkland, J. W. Dolan,** *Introduction to Modern Liquid Chromatography*,
  3rd ed., Wiley（2010）. — LSS、保持理論、分離度の標準テキスト。項目2・4の一次資料。
- **J. J. van Deemter, F. J. Zuiderweg, A. Klinkenberg,** *Chem. Eng. Sci.* **5**, 271 (1956). —
  van Deemter 式の原著。項目3の一次資料。
- **G. E. P. Box, K. B. Wilson,** *J. R. Stat. Soc. B* **13**, 1 (1951). —
  応答曲面法・CCD の原著。項目6の一次資料。
- **ICH Q8(R2),** *Pharmaceutical Development* (2009). — デザインスペースの規制上の定義。項目5の一次資料。

---

## モデル全体像（報告書用サマリ）

| 構成要素 | 採用した式 | 理論的根拠（章） |
|----------|-----------|----------------|
| 保持 × 温度 | `ln k = a + b/T` | ファントホッフ（§1） |
| 保持 × 溶媒 | `+ c·φ (+d·φ²)` | LSS / Snyder（§2） |
| 保持時間復元 | `t_R = (V_m/F)(1+k)` | 死容量の定義（§3周辺） |
| ピーク幅 | `W(T,φ,F)`、`W=4·t_R/√N` | van Deemter（§3） |
| 分離度 | `Rs=2|Δt_R|/(W1+W2)` | 標準定義（§4） |
| 合格領域 | Rs≥2.0 ∧ t_R 制約 | ICH Q8 デザインスペース（§5） |
| 実験計画 | CCD→D最適・ブロッキング | RSM / AQbD（§6） |

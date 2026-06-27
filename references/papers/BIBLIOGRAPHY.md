# 参考文献リスト（理論構築の根拠）

本プロジェクトの数理モデル・統計手法の各要素が、どの確立した理論・文献に由来するかを
完全な書誌情報とともにまとめる。`理論構築の流れ.md` の各節からここを参照する。

> **PDF の保存について**：本リポジトリを作成した実行環境は外部ネットワーク（出版社サイト・
> PubMed・DOI 解決等）へのアクセスがポリシーで遮断されているため、**論文 PDF を自動ダウンロード
> できなかった**。代わりに、各文献の DOI / URL と取得方法をここに記録する。社内ネットワークや
> 大学図書館の購読経由で DOI から本文を取得し、必要なら本フォルダ（`references/papers/`）に
> `01_vant_hoff.pdf` のような名前で保存していくことを推奨する。

凡例：⭐＝一次資料（原著・規制ガイドライン・標準教科書）。

---

## A. 保持の温度依存（ファントホッフ式）

1. **van't Hoff（原理）** — 反応の平衡定数 K の対数が 1/T に比例するという熱力学の関係
   （`ln K = −ΔH°/(RT) + ΔS°/R`）。クロマトでは分配平衡に適用し `ln k = a + b/T` となる。
   - 標準教科書（下記 C-1 Snyder ら）に記載。⭐

2. Chester, T. L. & Coym, J. W. ら系統の解説 — **Sources of Nonlinear van't Hoff Temperature
   Dependence in HPLC.** *ACS Omega* **4**, 21347–21354 (2019).
   - DOI: 10.1021/acsomega.9b02689
   - URL: https://pubs.acs.org/doi/10.1021/acsomega.9b02689 ／ PMC: PMC6882149
   - 関連：van't Hoff プロットが直線になる条件と、崩れて曲線（2次的）になる原因。
     本プロジェクトで「必要なら 2次項 d·φ² 等で補正」とした根拠。

---

## B. 保持の溶媒依存（LSS / Snyder モデル）

3. **Snyder, L. R.（LSS 原理）** — 逆相 HPLC で `log k = log k_w − S·φ`
   （φ＝有機溶媒体積分率）。線形溶媒強度（Linear Solvent Strength）理論。⭐（C-1 に集約）

4. Poole, C. F. & Atapattu, S. N. — **Analysis of the solvent strength parameter (linear solvent
   strength model) for isocratic separations in reversed-phase liquid chromatography.**
   *J. Chromatogr. A* **1675**, 463134 (2022).
   - DOI: 10.1016/j.chroma.2022.463134
   - URL: https://www.sciencedirect.com/science/article/abs/pii/S0021967322003466
   - 関連：アイソクラティック条件での LSS 傾き S・切片 log k_w の意味づけ。本プロジェクトの
     アイソクラティック前提に直結。

5. Guillarme, D. ら — LSS 挙動予測の数理的扱い. *J. Sep. Sci.*（2022）.
   - PubMed: 35562641 ／ URL: https://pubmed.ncbi.nlm.nih.gov/35562641/
   - 関連：LSS の数式的な扱いの実例。

---

## C. ピーク幅・カラム効率（van Deemter 式）

6. ⭐ **van Deemter, J. J.; Zuiderweg, F. J.; Klinkenberg, A.** — Longitudinal diffusion and
   resistance to mass transfer as causes of nonideality in chromatography.
   *Chem. Eng. Sci.* **5**(6), 271–289 (1956).
   - DOI: 10.1016/0009-2509(56)80003-1
   - 関連：段高 `H = A + B/u + C·u` の原著。幅モデルの一次資料。

7. 比較総説 — Comparison of equations describing band broadening in HPLC.
   *J. Chromatogr. A*（2003）.
   - URL: https://www.sciencedirect.com/science/article/abs/pii/S0021967303020636
   - 関連：van Deemter 系各式の比較。式選定の根拠。

---

## D. 理論段数・分離度（標準定義）

8. ⭐ **Snyder, L. R.; Kirkland, J. J.; Dolan, J. W.** — *Introduction to Modern Liquid
   Chromatography*, 3rd ed., Wiley (2010).
   - 関連：`N = 5.54·(t_R/W_h)²`、`Rs = 2·|Δt_R|/(W_b1+W_b2)`、保持・LSS・分離度の標準テキスト。
     項目 A・B・D の一次資料。ISBN: 978-0-470-16754-0

---

## E. デザインスペース（規制・品質設計）

9. ⭐ **ICH Q8(R2) Pharmaceutical Development** (2009).
   - URL: https://www.ema.europa.eu/en/ich-q8-r2-pharmaceutical-development-scientific-guideline
   - 関連：「デザインスペース＝品質を保証できると実証された入力変数・工程パラメータの多次元的な
     組合せの範囲」。最大余裕点（ロバスト運転点）を採る考え方の根拠。

---

## F. 実験計画法（応答曲面法・CCD・D最適）

10. ⭐ **Box, G. E. P.; Wilson, K. B.** — On the experimental attainment of optimum conditions.
    *J. R. Stat. Soc. B* **13**(1), 1–45 (1951).
    - DOI: 10.1111/j.2517-6161.1951.tb00067.x
    - 関連：応答曲面法（RSM）・中心複合計画（CCD）の原著。

11. ⭐ **Montgomery, D. C.** — *Design and Analysis of Experiments*, Wiley（各版）.
    - 関連：CCD、ブロッキング、D最適計画、計画行列、分散と det(XᵀX) の関係の標準教科書。
      ISBN: 978-1-119-49244-3（10th ed.）

12. CCD/RSM の製薬応用 — Central Composite Design for Response Surface Methodology and Its
    Application in Pharmacy (2021).
    - URL: https://www.researchgate.net/publication/348910011

13. AQbD による RP-HPLC 法開発（温度・有機溶媒比を CCD で評価）. PMC7070322.
    - URL: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7070322/
    - 関連：本プロジェクトと同種の因子を CCD で最適化した実例。

---

## G. 多重共線性・回帰診断（統計）

14. ⭐ **Montgomery, D. C.; Peck, E. A.; Vining, G. G.** — *Introduction to Linear Regression
    Analysis*, Wiley（各版）.
    - 関連：最小二乗、`Var(β̂)=σ²(XᵀX)⁻¹`、多重共線性（VIF・係数の不安定化）、RMSE。
      本プロジェクトの「個別係数は深読みせず予測精度で評価」の根拠。ISBN: 978-1-119-57872-7

---

## H. 対象化合物（gingerol の HPLC・背景の現実性）

15. Schwertner, H. A.; Rios, D. C. — High-performance liquid chromatographic analysis of
    6-gingerol, 8-gingerol, 10-gingerol, and 6-shogaol in ginger-containing dietary supplements,
    spices, teas, and beverages. *J. Chromatogr. B* **856**(1–2), 41–47 (2007).
    - PubMed: 17561453 ／ URL: https://pubmed.ncbi.nlm.nih.gov/17561453/
    - 関連：C18/C8 逆相・ACN 系での gingerol 分離。条件設定の現実性の裏づけ。

16. Validation of RP-HPLC for simultaneous determination of 6-,8-,10-gingerols and 6-shogaol.
    *Int. J. Pharm. Pharm. Sci.*
    - URL: https://journals.innovareacademics.in/index.php/ijpps/article/view/36446

---

## 取得状況メモ

| # | 文献 | DOI/ID | PDF 取得 |
|---|------|--------|----------|
| 2 | ACS Omega 2019（非線形van't Hoff） | 10.1021/acsomega.9b02689 | 未（要購読/PMC） |
| 4 | J. Chromatogr. A 2022（LSS） | 10.1016/j.chroma.2022.463134 | 未（要購読） |
| 6 | van Deemter 1956（原著） | 10.1016/0009-2509(56)80003-1 | 未（要購読） |
| 8 | Snyder ら 教科書 3rd ed. | ISBN 978-0-470-16754-0 | 書籍 |
| 9 | ICH Q8(R2) | — | 無料（EMA） |
| 10 | Box & Wilson 1951（RSM原著） | 10.1111/j.2517-6161.1951.tb00067.x | 未（要購読） |
| 11 | Montgomery DOE 教科書 | ISBN 978-1-119-49244-3 | 書籍 |
| 14 | Montgomery 回帰分析 教科書 | ISBN 978-1-119-57872-7 | 書籍 |
| 15 | Schwertner 2007（gingerol） | PMID 17561453 | 未（要購読） |

※ 本環境はネットワーク遮断のため未取得。DOI から各自取得し本フォルダに保存のこと。

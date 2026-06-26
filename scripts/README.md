# scripts/

段階別の Python スクリプトを置く（固定ロジック側）。設計確定後に実装。

- `01_model.py` … 数理モデル（k(T,φ)、W(T,φ,F)、Rs）の定義
- `02_design.py` … 実験計画生成（CCD → D最適 逐次）
- `03_fit.py` … 実測データへのフィット（保持3本・幅3本）
- `04_optimize.py` … Rs=min{Rs1,Rs2} 最大化・デザインスペース判定
- `05_designspace.py` … デザインスペース3D描画（plotly html）

※ まだ空。指摘2以降で設計を固めてから実装する。

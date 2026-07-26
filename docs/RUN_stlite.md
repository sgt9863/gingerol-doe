# アプリを HTML 1枚で動かす（stlite 版）

`docs/app.html` は、このアプリを **Python もサーバーも入れずに** 動かすためのファイルです。
ブラウザの中で Python（Pyodide＝WebAssembly 版 Python）が動き、その上で本物の Streamlit が
走る「stlite」という仕組みを使っています。**中身の計算コードは通常版とまったく同じ**です。

---

## 使い方（どちらでもOK）

**A. リンクを開くだけ**
　https://sgt9863.github.io/gingerol-doe/app.html

**B. ファイルを配って開く**
1. `docs/app.html` をダウンロード（GitHub の画面右上「Download raw file」）
2. 保存した `app.html` を**ダブルクリック**（既定のブラウザで開きます）
   - うまく開かないときは、ブラウザに**ドラッグ＆ドロップ**しても同じです
   - 推奨ブラウザ: Chrome / Edge

USB メモリやメール添付で配っても、受け取った人はこの1ファイルだけで使えます。

---

## 初回だけ時間がかかります

最初に開いたときは、ブラウザが Python 本体と計算ライブラリ（numpy・pandas・scipy・
statsmodels など、数十 MB）を取りに行くため、**30 秒〜数分**かかります。
その間は「ブラウザ内で Python を準備しています」という画面が出ます。

**2 回目以降はブラウザのキャッシュから読むので速く起動します。**

> **ネット接続について**：初回の読み込みだけインターネットが必要です（CDN から取得）。
> 以降はオフラインでも開けますが、キャッシュを消すと再取得が要ります。
> 社内ネットワークが CDN（`cdn.jsdelivr.net`・`pypi.org`）を遮断していると起動できません。
> その場合は通常版（`streamlit run app.py`）か、資産一式を同梱したオフライン版が必要です。

---

## 通常版との違い

| | 通常版（`streamlit run app.py`） | stlite 版（`app.html`） |
|---|---|---|
| 準備 | Python と各ライブラリのインストールが必要 | 不要（ブラウザだけ） |
| 起動 | 数秒 | 初回 30 秒〜数分、2回目以降は速い |
| 計算・グラフ | 同じ | **同じ**（結果も一致することを確認済み） |
| データの置き場所 | PC 内 | **ブラウザ内だけ**（外部に送信されません） |
| 回転 GIF の書き出し | できる | **できない**（描画に Chrome 本体が要る kaleido が WebAssembly で動かないため、この機能だけ自動的に非表示） |

3D グラフの HTML ダウンロード・推奨条件の CSV ダウンロード・Excel 雛形の
ダウンロードは stlite 版でも使えます。

---

## 中身を更新したら作り直す

`app.py` や `scripts/*.py`、`config.example.yaml`、デモデータを変更したら、
次のコマンドで `docs/app.html` を作り直します。

```bash
python tools/build_stlite.py
```

このスクリプトは、必要なファイルをすべて HTML の中に JSON として埋め込みます。
出力前に自己検査（埋め込み内容が元ファイルと一致するか、JavaScript の構文が壊れていないか）
を通すので、壊れた HTML が出来上がることはありません。

埋め込まれるもの: `app.py` / `scripts/01〜06` / `config.example.yaml` /
`data/demo_runs.csv` / `.streamlit/config.toml`

---

## 動作確認の記録

実ブラウザ（Chromium）で、資産をローカルに置いた同等構成にして確認しました。

- 起動 **約 30 秒**、タブ4つ（①計画 / ②解析 / ③D最適 / デモ）が表示
- 埋め込んだ 10 ファイルが仮想ファイルシステムに正しく展開
- numpy・pandas・scipy・**statsmodels**・matplotlib・pyyaml の読み込み成功
- デモ実行 → モデルフィット表・デザインスペース・3D グラフまで到達、**JS/Python の例外 0 件**
- 結果が通常版と一致（合格領域 48.9%、推奨条件 T=45.3℃ / φ=0.483 / F=0.55 mL/min、
  Rs_min=2.23（95%CI 1.94–2.54））
- kaleido が無い環境なので、GIF 書き出しの節が**意図どおり非表示**

技術的な内訳:
Pyodide 0.29.3（Python 3.13）＋ Streamlit 1.57 / stlite 1.8.1。
numpy・pandas・scipy・statsmodels・matplotlib・pyyaml は Pyodide 同梱版、
plotly・openpyxl は PyPI から取得（いずれも純 Python なので WebAssembly でも動きます）。

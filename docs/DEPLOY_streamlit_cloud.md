# Streamlit Community Cloud で公開する手順

このアプリ（`app.py`）を、無料の **Streamlit Community Cloud** で Web 公開する手順です。
GitHub リポジトリと連携するだけで、URL で誰でもアクセスできるようになります。

> 前提：このリポジトリ（`sgt9863/gingerol-doe`）が GitHub にあり、`app.py` と
> `requirements.txt` がリポジトリ直下にあること（すでに満たしています）。

## 手順（ブラウザだけで完結）

1. **https://share.streamlit.io** を開く
2. 右上 **「Sign in」** → **「Continue with GitHub」** で、リポジトリの持ち主（sgt9863）の
   GitHub アカウントでログイン
   - 初回は Streamlit に GitHub へのアクセス許可を求められる → 許可する
3. **「Create app」**（または「New app」）をクリック
4. 次を選ぶ：
   - **Repository**：`sgt9863/gingerol-doe`
   - **Branch**：`main`
   - **Main file path**：`app.py`
5. **「Deploy」** をクリック
6. 数分待つと（依存ライブラリの自動インストール後）アプリが起動し、
   `https://<適当な名前>.streamlit.app` のような **公開 URL** が発行される

これで完了です。URL を共有すれば、誰でもブラウザでアプリを使えます。

## 使い方（公開後）

- そのまま「デモ」タブで合成データの動作を見せられます。
- 実データは「④ 最終解析」タブに CSV/xlsx をアップロード（列名は `T, phi, F, day,
  tR_TP, tR_IP1, …, Wh_TP, Wh_IP1, …`）。
- サイドバーで夾雑ピークの数・因子範囲・合格条件・カラム寸法を変えられます。

## 更新の反映

- リポジトリの `main` に push すると、**Streamlit Cloud が自動で再デプロイ**します
  （数分後に最新版が反映）。手動で再起動したい場合はアプリ管理画面の「Reboot」。

## 注意・既知の制約

- **回転 GIF の書き出し**：Cloud 上では `kaleido==0.2.1`（Chromium 同梱）で動くよう
  設定済みですが、サーバー資源が限られるため**生成に時間がかかる／稀に失敗**することがあります。
  失敗してもアプリ本体や「▶ 自動回転」ボタン（ブラウザ内回転）は動きます。
- **公開範囲**：Community Cloud の無料枠はデフォルトで URL を知っていれば誰でも閲覧可。
  限定公開したい場合はアプリ設定で閲覧者のメール制限（viewer allowlist）をかけられます。
- **スリープ**：一定時間アクセスがないとアプリがスリープし、次回アクセス時に数十秒の
  起動待ちが入ります（無料枠の仕様）。

## トラブル時

- デプロイが失敗する → アプリ管理画面の「Manage app」→ ログ（Logs）を確認。
  多くは依存関係。`requirements.txt` はこのリポジトリに用意済みなので通常は問題なし。
- それでも詰まったら、ログの文面を教えてください。

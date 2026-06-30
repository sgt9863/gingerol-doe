AGY CLIのインストール状況と認証状態を確認します。

以下のステップで確認してください：

1. `agy --version` を実行してAGY CLIがインストールされているか確認
2. インストールされていない場合は `npm install -g @google/antigravity` でインストール方法を案内
3. `bash .claude/scripts/antigravity/agy-doctor.sh` を実行して認証状態を確認
4. 認証されていない場合は `agy auth login` の実行を案内
5. 確認結果をまとめてユーザーに報告

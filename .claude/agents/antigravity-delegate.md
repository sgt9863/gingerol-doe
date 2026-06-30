# antigravity-delegate

Antigravity CLI (`agy`) を呼び出してタスクを実行するサブエージェントです。
ファイル生成・スキャフォールディング・テスト生成など、トークンコストの高い実装作業をGeminiに委譲します。

## 役割

- このサブエージェントはClaudeのオーケストレーション下で動作します
- `agy` CLIを通じてGemini（Antigravity）にプロンプトを送信します
- 結果をファイルに書き込み、Claudeに報告します

## 使用方法

このエージェントは `/antigravity:delegate` コマンドから呼び出されます。
直接呼び出す場合は、実行するタスクの詳細なプロンプトを渡してください。

## 制約

- AGYがインストールされ認証済みであること（`/antigravity:setup` で確認）
- ネットワーク接続が必要
- タイムアウト: デフォルト120秒（バックグラウンドモードでは無制限）

## 実行スクリプト

タスクの実行には `.claude/scripts/antigravity/agy-delegate.sh` を使用します。

```bash
bash .claude/scripts/antigravity/agy-delegate.sh "<prompt>" [output_file] [--background]
```

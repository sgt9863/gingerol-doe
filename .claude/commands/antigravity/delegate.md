タスクをAntigravity CLI（AGY/Gemini）に委譲します。

**使い方:** `/antigravity:delegate <タスクの説明>`

## 実行手順

1. ユーザーのタスクを受け取る（引数: $ARGUMENTS）
2. タスクに応じた詳細なプロンプトを構築する
3. `bash .claude/scripts/antigravity/agy-delegate.sh` を呼び出してAGYに委譲する
4. 出力結果をユーザーに報告し、必要に応じてレビューする

## 委譲に適したタスク

- 新しいファイル・モジュールの作成
- テストコードの生成
- ドキュメントの作成・更新
- ボイラープレートの実装
- 繰り返しパターンのコーディング
- マイグレーションスクリプト生成

## 実行コマンド

```bash
bash .claude/scripts/antigravity/agy-delegate.sh "$ARGUMENTS"
```

タスクが完了したら、生成されたコードをレビューしてユーザーに報告してください。
長時間かかるタスクには `--background` フラグを使用してください。

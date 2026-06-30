AGY（Gemini）によるクロスモデルコードレビューを実行します。

**使い方:** `/antigravity:review [ファイルパスまたはdiff]`

## 実行手順

1. レビュー対象を特定する（引数がなければ `git diff HEAD` を使用）
2. レビュープロンプトを構築する
3. `bash .claude/scripts/antigravity/agy-delegate.sh` でAGYにレビューを依頼する
4. AGYのレビュー結果をClaudeが評価・補足してユーザーに提示する

## レビュー観点

AGYには以下の観点でレビューするよう指示します：
- バグ・論理エラーの検出
- コードの可読性・保守性
- パフォーマンス上の問題
- セキュリティ上のリスク
- テストカバレッジの不足

## 実行コマンド

```bash
# 引数がある場合
bash .claude/scripts/antigravity/agy-delegate.sh "以下のコードをレビューしてください:\n$ARGUMENTS"

# 引数がない場合（gitの差分をレビュー）
DIFF=$(git diff HEAD 2>/dev/null || git diff --cached)
bash .claude/scripts/antigravity/agy-delegate.sh "以下のgit diffをレビューしてください:\n$DIFF"
```

結果を受け取ったら、Claudeとして追加の洞察や判断を加えてユーザーに報告してください。

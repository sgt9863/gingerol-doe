AGY（Gemini）のウェブ検索機能を使って深層調査を実行します。

**使い方:** `/antigravity:research <調査テーマ>`

## 特徴

AGYはGoogleの検索・Vertex AI Searchにアクセスできるため、最新情報の調査に優れています。
Claudeはその結果を評価・統合し、プロジェクトの文脈に合わせて提示します。

## 実行手順

1. 調査テーマを受け取る（引数: $ARGUMENTS）
2. 調査プロンプトを構築する
3. `bash .claude/scripts/antigravity/agy-delegate.sh` でAGYに調査を依頼する
4. 結果を評価してプロジェクトへの適用可能性をまとめる

## 実行コマンド

```bash
bash .claude/scripts/antigravity/agy-delegate.sh "以下のテーマについて、最新の情報を検索して詳しく調査してください。信頼できるソースを引用し、実装に役立つ具体的な情報を提供してください:\n\n$ARGUMENTS"
```

調査結果が返ってきたら：
1. 情報の信頼性を評価する
2. プロジェクトの文脈で関連する部分を強調する
3. 次のアクションを提案する

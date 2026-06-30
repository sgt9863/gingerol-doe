Cloud RunのログをAGY（Gemini）で分析・診断します。

**使い方:** `/antigravity:cloud-run-debug <サービス名> [--project <project_id>] [--region <region>]`

## 実行手順

1. 引数からサービス名・プロジェクト・リージョンを取得する
2. `bash .claude/scripts/antigravity/cloud-debug.sh` でログを取得・圧縮する
3. AGYにログのダイジェストを送って診断させる
4. ClaudeがAGYの診断結果を評価し、修正案を提示する

## アーキテクチャ

```
生ログ → cloud-debug.sh（取得・圧縮） → AGY（ダイジェスト→診断） → Claude（評価・提案）
```

AGYがログを構造化サマリーに圧縮することで、Claudeに送るトークン数を最小化します。

## 実行コマンド

```bash
bash .claude/scripts/antigravity/cloud-debug.sh $ARGUMENTS
```

スクリプトが実行された後、AGYの診断結果を評価して：
1. 根本原因の特定
2. 修正手順の提案
3. 再発防止策の提案

を行ってください。

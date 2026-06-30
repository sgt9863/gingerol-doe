#!/usr/bin/env bash
# Claude単体 vs ClaudeオーケストレーションAGYのコスト比較測定スクリプト
set -euo pipefail

TASK="${1:-}"
OUTPUT_DIR="./cost-reports"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

if [[ -z "$TASK" ]]; then
  echo "Usage: agy-cost-compare.sh <task_description>" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "=== コスト比較測定 ==="
echo "タスク: $TASK"
echo ""

# AGYに委譲した場合の実行
echo "1. AGYでタスクを実行中..."
START=$(date +%s%3N)
bash "$(dirname "$0")/agy-delegate.sh" "$TASK" "${OUTPUT_DIR}/agy-output-${TIMESTAMP}.txt"
END=$(date +%s%3N)
AGY_TIME=$((END - START))

echo ""
echo "=== 測定結果 ==="
echo "  AGY実行時間: ${AGY_TIME}ms"
echo "  出力ファイル: ${OUTPUT_DIR}/agy-output-${TIMESTAMP}.txt"
echo ""
echo "補足: Claude単体との比較は、同じタスクをClaude Codeで直接実行して"
echo "      /cost コマンドでトークン使用量を確認してください。"
echo ""
echo "記事の実測値: ハイブリッド運用でClaudeコスト -27〜64% を達成"

#!/usr/bin/env bash
# AGY CLIにタスクを委譲するスクリプト
set -euo pipefail

PROMPT="${1:-}"
OUTPUT_FILE="${2:-}"
BACKGROUND=false
TIMEOUT=120

# 引数解析
for arg in "$@"; do
  case $arg in
    --background) BACKGROUND=true ;;
    --timeout=*) TIMEOUT="${arg#*=}" ;;
  esac
done

if [[ -z "$PROMPT" ]]; then
  echo "Usage: agy-delegate.sh <prompt> [output_file] [--background] [--timeout=<seconds>]" >&2
  exit 1
fi

# AGY CLIの存在確認
if ! command -v agy &>/dev/null; then
  echo "ERROR: agy CLI が見つかりません。インストールしてください:" >&2
  echo "  npm install -g @google/antigravity" >&2
  exit 1
fi

# 実行
if [[ "$BACKGROUND" == true ]]; then
  JOB_ID="agy-job-$(date +%s)"
  LOG_FILE="/tmp/${JOB_ID}.log"

  echo "バックグラウンドジョブを開始: ${JOB_ID}"
  echo "ログ: ${LOG_FILE}"

  nohup agy -p "$PROMPT" >"$LOG_FILE" 2>&1 &
  echo $! > "/tmp/${JOB_ID}.pid"
  echo "PID: $(cat /tmp/${JOB_ID}.pid)"
  echo "結果確認: cat ${LOG_FILE}"
elif [[ -n "$OUTPUT_FILE" ]]; then
  echo "AGYに委譲中..."
  timeout "$TIMEOUT" agy -p "$PROMPT" | tee "$OUTPUT_FILE"
else
  echo "AGYに委譲中..."
  timeout "$TIMEOUT" agy -p "$PROMPT"
fi

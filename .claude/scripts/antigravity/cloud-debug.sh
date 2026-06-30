#!/usr/bin/env bash
# Cloud RunのログをAGYで診断するスクリプト
set -euo pipefail

SERVICE="${1:-}"
PROJECT="${GOOGLE_CLOUD_PROJECT:-}"
REGION="${CLOUD_RUN_REGION:-asia-northeast1}"
LINES=200

# 引数解析
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project=*) PROJECT="${1#*=}" ;;
    --project)   PROJECT="$2"; shift ;;
    --region=*)  REGION="${1#*=}" ;;
    --region)    REGION="$2"; shift ;;
    --lines=*)   LINES="${1#*=}" ;;
  esac
  shift || true
done

if [[ -z "$SERVICE" ]]; then
  echo "Usage: cloud-debug.sh <service-name> [--project <id>] [--region <region>]" >&2
  exit 1
fi

if [[ -z "$PROJECT" ]]; then
  PROJECT=$(gcloud config get-value project 2>/dev/null || echo "")
  if [[ -z "$PROJECT" ]]; then
    echo "ERROR: プロジェクトIDを指定してください (--project または GOOGLE_CLOUD_PROJECT)" >&2
    exit 1
  fi
fi

echo "=== Cloud Run ログ取得 ==="
echo "  サービス: $SERVICE"
echo "  プロジェクト: $PROJECT"
echo "  リージョン: $REGION"
echo ""

# ログ取得
RAW_LOGS=$(gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE}" \
  --project="$PROJECT" \
  --limit="$LINES" \
  --format="value(timestamp,severity,textPayload,jsonPayload.message)" \
  2>/dev/null || echo "ログ取得失敗")

if [[ "$RAW_LOGS" == "ログ取得失敗" ]]; then
  echo "ERROR: ログの取得に失敗しました。gcloud認証を確認してください。" >&2
  exit 1
fi

# AGYでログを診断
PROMPT="以下はGoogle Cloud Run サービス「${SERVICE}」のログです。
エラー・警告・異常なパターンを特定し、根本原因と修正案を提案してください。
構造化されたサマリーで回答してください。

---
${RAW_LOGS}
---"

echo "AGYでログを診断中..."
bash "$(dirname "$0")/agy-delegate.sh" "$PROMPT"

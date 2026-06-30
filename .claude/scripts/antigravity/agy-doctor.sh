#!/usr/bin/env bash
# AGY CLIの動作確認スクリプト
set -uo pipefail

PASS=0
FAIL=0

check() {
  local label="$1"
  local cmd="$2"

  if eval "$cmd" &>/dev/null; then
    echo "  [OK] $label"
    ((PASS++)) || true
  else
    echo "  [NG] $label"
    ((FAIL++)) || true
  fi
}

echo "=== Antigravity CLI 診断 ==="
echo ""

echo "1. インストール確認"
check "agy コマンドが存在する" "command -v agy"

if command -v agy &>/dev/null; then
  echo "   バージョン: $(agy --version 2>/dev/null || echo '不明')"
fi

echo ""
echo "2. 認証確認"
check "agy auth status が成功する" "agy auth status"

echo ""
echo "3. 疎通確認"
check "agy に簡単なプロンプトを送信できる" "timeout 30 agy -p 'hello' --no-interactive"

echo ""
echo "=== 結果 ==="
echo "  成功: ${PASS}, 失敗: ${FAIL}"

if [[ $FAIL -gt 0 ]]; then
  echo ""
  echo "問題を解決するには:"
  echo "  インストール: npm install -g @google/antigravity"
  echo "  認証:         agy auth login"
  exit 1
fi

echo ""
echo "AGY CLIは正常に動作しています。"

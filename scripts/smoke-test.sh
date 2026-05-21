#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0
SKIP=0

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }

check() {
  local name="$1" status="$2" body="$3"
  if [ "$status" -ge 200 ] && [ "$status" -lt 400 ]; then
    green "PASS  $name (HTTP $status)"
    PASS=$((PASS + 1))
  else
    red "FAIL  $name (HTTP $status)"
    echo "      $body" | head -c 200
    echo
    FAIL=$((FAIL + 1))
  fi
}

echo "=========================================="
echo " Smoke Test — $BASE_URL"
echo "=========================================="
echo

# 1. Health
echo "--- Health Check ---"
RESP=$(curl -sw '\n%{http_code}' -o - "$BASE_URL/health" 2>/dev/null)
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "GET /health" "$STATUS" "$BODY"
echo "  $BODY"
echo

# 2. Scope Options (no session)
echo "--- Scope Options ---"
RESP=$(curl -sw '\n%{http_code}' -o - "$BASE_URL/scope/options?customer_key=demo&user_id=smoke.test" 2>/dev/null)
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "GET /scope/options" "$STATUS" "$BODY"
OPTION_COUNT=$(echo "$BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('options',[])))" 2>/dev/null || echo "?")
echo "  Scopes available: $OPTION_COUNT"
echo

# 3. Chat — create session + ask question
echo "--- Chat (new session) ---"
CHAT_PAYLOAD='{"question":"hello","customer_key":"demo","user_id":"smoke.test","role":"officer"}'
RESP=$(curl -sw '\n%{http_code}' -o - -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d "$CHAT_PAYLOAD" 2>/dev/null)
STATUS=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "POST /chat" "$STATUS" "$BODY"
SESSION_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || echo "")
echo "  Session: ${SESSION_ID:-none}"
echo

# 4. Get Session (if we got one)
if [ -n "$SESSION_ID" ] && [ "$SESSION_ID" != "None" ] && [ "$SESSION_ID" != "" ]; then
  echo "--- Session Lookup ---"
  RESP=$(curl -sw '\n%{http_code}' -o - "$BASE_URL/session/$SESSION_ID" 2>/dev/null)
  STATUS=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | head -n -1)
  check "GET /session/$SESSION_ID" "$STATUS" "$BODY"
  echo "  $BODY" | head -c 200
  echo
  echo

  # 5. Scope Select
  echo "--- Scope Select ---"
  SELECT_PAYLOAD="{\"session_id\":\"$SESSION_ID\",\"scope\":\"inmate_data\",\"customer_key\":\"demo\",\"user_id\":\"smoke.test\"}"
  RESP=$(curl -sw '\n%{http_code}' -o - -X POST "$BASE_URL/scope/select" \
    -H "Content-Type: application/json" \
    -d "$SELECT_PAYLOAD" 2>/dev/null)
  STATUS=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | head -n -1)
  check "POST /scope/select" "$STATUS" "$BODY"
  echo "  $BODY" | head -c 200
  echo
  echo

  # 6. History
  echo "--- History ---"
  RESP=$(curl -sw '\n%{http_code}' -o - "$BASE_URL/history?customer_key=demo&user_id=smoke.test" 2>/dev/null)
  STATUS=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | head -n -1)
  check "GET /history" "$STATUS" "$BODY"
  echo "  $BODY" | head -c 200
  echo
  echo
else
  yellow "SKIP  Session-dependent tests (no session_id from /chat)"
  SKIP=$((SKIP + 3))
fi

# 7. Pipeline Health
echo "--- Pipeline Health ---"
for scope in inmate_data document_qa; do
  RESP=$(curl -sw '\n%{http_code}' -o - "$BASE_URL/pipelines/health/$scope" 2>/dev/null)
  STATUS=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | head -n -1)
  check "GET /pipelines/health/$scope" "$STATUS" "$BODY"
done
echo

# 8. CORS preflight
echo "--- CORS Preflight ---"
RESP=$(curl -sw '\n%{http_code}' -o - -X OPTIONS "$BASE_URL/chat" \
  -H "Origin: https://example.com" \
  -H "Access-Control-Request-Method: POST" 2>/dev/null)
STATUS=$(echo "$RESP" | tail -1)
check "OPTIONS /chat (CORS)" "$STATUS" ""
echo

# 9. X-Request-Id header
echo "--- X-Request-Id Header ---"
REQ_ID=$(curl -sI "$BASE_URL/health" 2>/dev/null | grep -i "x-request-id" | awk '{print $2}' | tr -d '\r')
if [ -n "$REQ_ID" ]; then
  green "PASS  X-Request-Id present: $REQ_ID"
  PASS=$((PASS + 1))
else
  red "FAIL  X-Request-Id header missing"
  FAIL=$((FAIL + 1))
fi
echo

# Summary
echo "=========================================="
printf "Results: "
green "$PASS passed"
[ "$FAIL" -gt 0 ] && red "         $FAIL failed"
[ "$SKIP" -gt 0 ] && yellow "         $SKIP skipped"
echo "=========================================="

exit $FAIL

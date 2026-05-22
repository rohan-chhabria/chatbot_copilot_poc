#!/bin/bash
#===============================================================================
# InmateCopilot Production-Grade Test Suite
#===============================================================================
# Comprehensive testing of all chatbot functionality including:
# - Health checks
# - Session management (STM - Redis)
# - Conversation history (LTM - DynamoDB)
# - All three scopes (Daily Activity, Inmate Data, Document QA)
# - Scope switching
# - Multi-turn conversations & follow-ups
# - Cross-scope handlers (global intents)
# - SSE Streaming
# - Input validation
#
# Usage:
#   ./test_chatbot.sh                    # Test against localhost:8000
#   ./test_chatbot.sh http://prod:8000   # Test against custom URL
#
# Output:
#   - Console: Real-time test progress
#   - File: test_report_<timestamp>.json (detailed report)
#===============================================================================

set -o pipefail

# Configuration
BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
CUSTOMER_KEY="${CUSTOMER_KEY:-14}"
FACILITY_IDS="${FACILITY_IDS:-[63]}"
USER_ID="${USER_ID:-test.user.$(date +%s)}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPORT_FILE="${SCRIPT_DIR}/test_report_${TIMESTAMP}.json"

# Counters
PASSED=0
FAILED=0
TOTAL=0

# Results arrays
declare -a RESULTS=()
declare -a STM_TESTS=()
declare -a LTM_TESTS=()
declare -a SCOPE_SWITCH_TESTS=()
declare -a DAILY_ACTIVITY_TESTS=()
declare -a INMATE_DATA_TESTS=()
declare -a DOCUMENT_QA_TESTS=()
declare -a CROSS_SCOPE_TESTS=()

# Session tracking
SESSION_ID=""
PREV_SCOPE=""

#-------------------------------------------------------------------------------
# Helper Functions
#-------------------------------------------------------------------------------

log_info() { echo -e "\033[1;34m[INFO]\033[0m $1"; }
log_test() { echo -e "\033[1;36m[TEST]\033[0m $1"; }
log_pass() { echo -e "\033[1;32m[PASS]\033[0m $1"; PASSED=$((PASSED+1)); }
log_fail() { echo -e "\033[1;31m[FAIL]\033[0m $1"; FAILED=$((FAILED+1)); }
log_section() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

add_result() {
    local test_id="$1" test_name="$2" status="$3" category="$4"
    local request="$5" response="$6" duration_ms="$7"
    local result="{\"id\":\"$test_id\",\"name\":\"$test_name\",\"status\":\"$status\",\"category\":\"$category\",\"duration_ms\":$duration_ms,\"request\":$request,\"response\":$response}"
    RESULTS+=("$result")
    TOTAL=$((TOTAL+1))
    
    case "$category" in
        stm) STM_TESTS+=("$result") ;;
        ltm) LTM_TESTS+=("$result") ;;
        scope_switch) SCOPE_SWITCH_TESTS+=("$result") ;;
        daily_activity) DAILY_ACTIVITY_TESTS+=("$result") ;;
        inmate_data) INMATE_DATA_TESTS+=("$result") ;;
        document_qa) DOCUMENT_QA_TESTS+=("$result") ;;
        cross_scope) CROSS_SCOPE_TESTS+=("$result") ;;
    esac
}

do_request() {
    local method="$1" endpoint="$2" data="$3"
    local start_time=$(date +%s%3N)
    local resp
    
    if [ "$method" = "GET" ]; then
        resp=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint" 2>&1)
    else
        resp=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" -d "$data" 2>&1)
    fi
    
    local end_time=$(date +%s%3N)
    local duration=$((end_time - start_time))
    local http_code=$(echo "$resp" | tail -1)
    local body=$(echo "$resp" | sed '$d')
    
    echo "$body"
    echo "$http_code"
    echo "$duration"
}

create_session() {
    local data="{\"question\":\"hello\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"facility_ids\":$FACILITY_IDS}"
    local body=$(curl -s -X POST "$BASE_URL/chat" -H "Content-Type: application/json" -d "$data")
    SESSION_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
    echo "$SESSION_ID"
}

select_scope() {
    local scope="$1"
    local data="{\"session_id\":\"$SESSION_ID\",\"scope\":\"$scope\"}"
    curl -s -X POST "$BASE_URL/scope/select" -H "Content-Type: application/json" -d "$data"
}

#-------------------------------------------------------------------------------
# Test Functions
#-------------------------------------------------------------------------------

test_health() {
    log_test "Health Endpoint"
    local result=$(do_request GET "/health" "")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ] && echo "$body" | grep -q '"status":"healthy"'; then
        log_pass "Health: OK (${duration}ms)"
        add_result "health" "Health Check" "pass" "health" "{\"endpoint\":\"/health\"}" "$body" "$duration"
    else
        log_fail "Health: HTTP $code"
        add_result "health" "Health Check" "fail" "health" "{\"endpoint\":\"/health\"}" "$body" "$duration"
    fi
}

test_health_deep() {
    log_test "Deep Health Check"
    local result=$(do_request GET "/health/deep" "")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ]; then
        log_pass "Deep Health: OK (${duration}ms)"
        add_result "health_deep" "Deep Health Check" "pass" "health" "{\"endpoint\":\"/health/deep\"}" "$body" "$duration"
    else
        log_fail "Deep Health: HTTP $code"
        add_result "health_deep" "Deep Health Check" "fail" "health" "{\"endpoint\":\"/health/deep\"}" "$body" "$duration"
    fi
}

#-------------------------------------------------------------------------------
# STM (Short-Term Memory) Tests
#-------------------------------------------------------------------------------

test_stm_session_create() {
    log_test "STM: Session Creation"
    local data="{\"question\":\"hello\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"facility_ids\":$FACILITY_IDS}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    SESSION_ID=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
    
    if [ "$code" = "200" ] && [ -n "$SESSION_ID" ]; then
        log_pass "STM: Session created ${SESSION_ID:0:12}... (${duration}ms)"
        add_result "stm_create" "Session Creation" "pass" "stm" "$data" "$body" "$duration"
    else
        log_fail "STM: Session creation failed"
        add_result "stm_create" "Session Creation" "fail" "stm" "$data" "$body" "$duration"
    fi
}

test_stm_session_retrieve() {
    log_test "STM: Session Retrieval"
    local result=$(do_request GET "/session/$SESSION_ID" "")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ]; then
        local turn_count=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('turn_count',0))" 2>/dev/null)
        local active_scope=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('active_scope','None'))" 2>/dev/null)
        log_pass "STM: Retrieved (turns=$turn_count, scope=$active_scope) (${duration}ms)"
        add_result "stm_retrieve" "Session Retrieval" "pass" "stm" "{\"session_id\":\"$SESSION_ID\"}" "$body" "$duration"
    else
        log_fail "STM: Retrieval failed"
        add_result "stm_retrieve" "Session Retrieval" "fail" "stm" "{\"session_id\":\"$SESSION_ID\"}" "$body" "$duration"
    fi
}

test_stm_session_update() {
    log_test "STM: Session Update on Query"
    # Get initial turn count
    local initial=$(curl -s "$BASE_URL/session/$SESSION_ID" | python3 -c "import sys,json; print(json.load(sys.stdin).get('turn_count',0))" 2>/dev/null)
    
    # Make a query
    local data="{\"question\":\"test query\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    curl -s -X POST "$BASE_URL/chat" -H "Content-Type: application/json" -d "$data" > /dev/null
    
    # Check turn count increased
    local result=$(do_request GET "/session/$SESSION_ID" "")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    local new_count=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('turn_count',0))" 2>/dev/null)
    
    if [ "$new_count" -gt "$initial" ]; then
        log_pass "STM: Turn count updated ($initial -> $new_count) (${duration}ms)"
        add_result "stm_update" "Session Update" "pass" "stm" "{}" "$body" "$duration"
    else
        log_fail "STM: Turn count not updated"
        add_result "stm_update" "Session Update" "fail" "stm" "{}" "$body" "$duration"
    fi
}

test_stm_invalid_session() {
    log_test "STM: Invalid Session Handling"
    local data="{\"question\":\"test\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"invalid-session-12345\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if echo "$body" | grep -q '"error":"session_expired"'; then
        log_pass "STM: Invalid session handled correctly (${duration}ms)"
        add_result "stm_invalid" "Invalid Session" "pass" "stm" "$data" "$body" "$duration"
    else
        log_fail "STM: Invalid session not handled"
        add_result "stm_invalid" "Invalid Session" "fail" "stm" "$data" "$body" "$duration"
    fi
}

#-------------------------------------------------------------------------------
# LTM (Long-Term Memory) Tests
#-------------------------------------------------------------------------------

test_ltm_history_stored() {
    log_test "LTM: Conversation History Storage"
    # Make sure we have some conversation
    local data="{\"question\":\"how many inmates\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    curl -s -X POST "$BASE_URL/chat" -H "Content-Type: application/json" -d "$data" > /dev/null
    
    local result=$(do_request GET "/history?customer_key=$CUSTOMER_KEY&user_id=$USER_ID&limit=10" "")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ]; then
        local total=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null)
        log_pass "LTM: History stored ($total turns) (${duration}ms)"
        add_result "ltm_stored" "History Storage" "pass" "ltm" "{\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\"}" "$body" "$duration"
    else
        log_fail "LTM: History retrieval failed"
        add_result "ltm_stored" "History Storage" "fail" "ltm" "{}" "$body" "$duration"
    fi
}

test_ltm_cross_session() {
    log_test "LTM: Cross-Session Persistence"
    # Create new session for same user
    local old_session=$SESSION_ID
    local data="{\"question\":\"new session query\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"facility_ids\":$FACILITY_IDS}"
    local new_body=$(curl -s -X POST "$BASE_URL/chat" -H "Content-Type: application/json" -d "$data")
    local new_session=$(echo "$new_body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
    
    # Check history still contains old data
    local result=$(do_request GET "/history?customer_key=$CUSTOMER_KEY&user_id=$USER_ID&limit=20" "")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ] && [ "$new_session" != "$old_session" ]; then
        local total=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null)
        log_pass "LTM: Cross-session persistence OK ($total turns) (${duration}ms)"
        add_result "ltm_cross_session" "Cross-Session" "pass" "ltm" "{}" "$body" "$duration"
    else
        log_fail "LTM: Cross-session persistence failed"
        add_result "ltm_cross_session" "Cross-Session" "fail" "ltm" "{}" "$body" "$duration"
    fi
    SESSION_ID=$old_session
}

#-------------------------------------------------------------------------------
# Scope Switching Tests
#-------------------------------------------------------------------------------

test_scope_options() {
    log_test "Scope: Available Options"
    local result=$(do_request GET "/scope/options?customer_key=$CUSTOMER_KEY&user_id=$USER_ID" "")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ]; then
        local scopes=$(echo "$body" | python3 -c "import sys,json; print([o['id'] for o in json.load(sys.stdin).get('options',[])])" 2>/dev/null)
        log_pass "Scope: Options $scopes (${duration}ms)"
        add_result "scope_options" "Scope Options" "pass" "scope_switch" "{}" "$body" "$duration"
    else
        log_fail "Scope: Options failed"
        add_result "scope_options" "Scope Options" "fail" "scope_switch" "{}" "$body" "$duration"
    fi
}

test_scope_select() {
    local scope="$1"
    log_test "Scope: Select $scope"
    
    local data="{\"session_id\":\"$SESSION_ID\",\"scope\":\"$scope\"}"
    local result=$(do_request POST "/scope/select" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ] && echo "$body" | grep -q "\"scope\":\"$scope\""; then
        local prev=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('previous_scope','None'))" 2>/dev/null)
        log_pass "Scope: Selected $scope (prev=$prev) (${duration}ms)"
        add_result "scope_select_$scope" "Select $scope" "pass" "scope_switch" "$data" "$body" "$duration"
        PREV_SCOPE="$scope"
    else
        log_fail "Scope: Select $scope failed"
        add_result "scope_select_$scope" "Select $scope" "fail" "scope_switch" "$data" "$body" "$duration"
    fi
}

test_scope_switch() {
    log_test "Scope: Switch from $PREV_SCOPE to inmate_data"
    
    local data="{\"session_id\":\"$SESSION_ID\",\"scope\":\"inmate_data\"}"
    local result=$(do_request POST "/scope/select" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ]; then
        local prev=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('previous_scope','None'))" 2>/dev/null)
        local is_change=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('is_scope_change',False))" 2>/dev/null)
        if [ "$is_change" = "True" ]; then
            log_pass "Scope: Switch OK (prev=$prev, is_change=$is_change) (${duration}ms)"
            add_result "scope_switch" "Scope Switch" "pass" "scope_switch" "$data" "$body" "$duration"
        else
            log_fail "Scope: is_scope_change not True"
            add_result "scope_switch" "Scope Switch" "fail" "scope_switch" "$data" "$body" "$duration"
        fi
    else
        log_fail "Scope: Switch failed"
        add_result "scope_switch" "Scope Switch" "fail" "scope_switch" "$data" "$body" "$duration"
    fi
}

#-------------------------------------------------------------------------------
# Daily Activity Tests (Rule-based, no follow-ups)
#-------------------------------------------------------------------------------

test_daily_activity() {
    log_test "Daily Activity: Auto-execute on scope select"
    
    # Select scope - should auto-execute
    local data="{\"session_id\":\"$SESSION_ID\",\"scope\":\"daily_activity\"}"
    local result=$(do_request POST "/scope/select" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ] && echo "$body" | grep -q "activities"; then
        log_pass "Daily Activity: Auto-executed on select (${duration}ms)"
        add_result "da_auto_execute" "Auto Execute" "pass" "daily_activity" "$data" "$body" "$duration"
    else
        log_fail "Daily Activity: Auto-execute failed"
        add_result "da_auto_execute" "Auto Execute" "fail" "daily_activity" "$data" "$body" "$duration"
    fi
}

test_daily_activity_refresh() {
    log_test "Daily Activity: Refresh command"
    
    local data="{\"question\":\"refresh\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ]; then
        local missed=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin).get('data',{}); print(d.get('total_missed',0))" 2>/dev/null)
        local upcoming=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin).get('data',{}); print(d.get('total_upcoming',0))" 2>/dev/null)
        log_pass "Daily Activity: Refresh OK (missed=$missed, upcoming=$upcoming) (${duration}ms)"
        add_result "da_refresh" "Refresh" "pass" "daily_activity" "$data" "$body" "$duration"
    else
        log_fail "Daily Activity: Refresh failed"
        add_result "da_refresh" "Refresh" "fail" "daily_activity" "$data" "$body" "$duration"
    fi
}

test_daily_activity_response_structure() {
    log_test "Daily Activity: Response structure (keyword_id, tag_status_id)"
    
    local data="{\"question\":\"refresh\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local body=$(curl -s -X POST "$BASE_URL/chat" -H "Content-Type: application/json" -d "$data")
    
    local has_structure=$(echo "$body" | python3 -c "
import sys, json
d = json.load(sys.stdin)
data = d.get('data', {})
has_missed = 'missed_activities' in data
has_upcoming = 'upcoming_activities' in data
has_config = 'config' in data
print('pass' if (has_missed and has_upcoming and has_config) else 'fail')
" 2>/dev/null)
    
    if [ "$has_structure" = "pass" ]; then
        log_pass "Daily Activity: Response structure OK"
        add_result "da_structure" "Response Structure" "pass" "daily_activity" "$data" "$body" "0"
    else
        log_fail "Daily Activity: Missing response fields"
        add_result "da_structure" "Response Structure" "fail" "daily_activity" "$data" "$body" "0"
    fi
}

test_daily_activity_non_refresh() {
    log_test "Daily Activity: Non-refresh question"
    
    local data="{\"question\":\"show me inmates\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local duration=$(echo "$result" | tail -1)
    
    if echo "$body" | grep -q "refresh"; then
        log_pass "Daily Activity: Non-refresh handled (instruction shown) (${duration}ms)"
        add_result "da_non_refresh" "Non-Refresh Question" "pass" "daily_activity" "$data" "$body" "$duration"
    else
        log_fail "Daily Activity: Non-refresh not handled"
        add_result "da_non_refresh" "Non-Refresh Question" "fail" "daily_activity" "$data" "$body" "$duration"
    fi
}

#-------------------------------------------------------------------------------
# Inmate Data Tests (Multi-turn, Follow-ups)
#-------------------------------------------------------------------------------

test_inmate_data_query() {
    log_test "Inmate Data: Basic query"
    select_scope "inmate_data" > /dev/null
    
    local data="{\"question\":\"how many inmates are there\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ] && echo "$body" | grep -q '"success":true'; then
        local rows=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('row_count',0))" 2>/dev/null)
        log_pass "Inmate Data: Query OK (rows=$rows) (${duration}ms)"
        add_result "id_basic" "Basic Query" "pass" "inmate_data" "$data" "$body" "$duration"
    else
        log_fail "Inmate Data: Query failed"
        add_result "id_basic" "Basic Query" "fail" "inmate_data" "$data" "$body" "$duration"
    fi
}

test_inmate_data_followup() {
    log_test "Inmate Data: Follow-up query"
    
    local data="{\"question\":\"show their names\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ] && echo "$body" | grep -q '"success":true'; then
        local rows=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('row_count',0))" 2>/dev/null)
        log_pass "Inmate Data: Follow-up OK (rows=$rows) (${duration}ms)"
        add_result "id_followup" "Follow-up Query" "pass" "inmate_data" "$data" "$body" "$duration"
    else
        log_fail "Inmate Data: Follow-up failed"
        add_result "id_followup" "Follow-up Query" "fail" "inmate_data" "$data" "$body" "$duration"
    fi
}

test_inmate_data_response_structure() {
    log_test "Inmate Data: Response structure (rows, insights)"
    
    local data="{\"question\":\"list recent bookings\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local body=$(curl -s -X POST "$BASE_URL/chat" -H "Content-Type: application/json" -d "$data")
    
    local has_structure=$(echo "$body" | python3 -c "
import sys, json
d = json.load(sys.stdin)
data = d.get('data', {})
has_rows = 'rows' in data
has_insights = 'insights' in data
print('pass' if (has_rows or has_insights) else 'fail')
" 2>/dev/null)
    
    if [ "$has_structure" = "pass" ]; then
        log_pass "Inmate Data: Response structure OK"
        add_result "id_structure" "Response Structure" "pass" "inmate_data" "$data" "$body" "0"
    else
        log_fail "Inmate Data: Missing response fields"
        add_result "id_structure" "Response Structure" "fail" "inmate_data" "$data" "$body" "0"
    fi
}

#-------------------------------------------------------------------------------
# Document QA Tests (Multi-turn, Follow-ups)
#-------------------------------------------------------------------------------

test_document_qa_query() {
    log_test "Document QA: Basic query"
    select_scope "document_qa" > /dev/null
    
    local data="{\"question\":\"what is chow call\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ] && echo "$body" | grep -q '"success":true'; then
        local chunks=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('row_count',0))" 2>/dev/null)
        log_pass "Document QA: Query OK (chunks=$chunks) (${duration}ms)"
        add_result "dq_basic" "Basic Query" "pass" "document_qa" "$data" "$body" "$duration"
    else
        log_fail "Document QA: Query failed"
        add_result "dq_basic" "Basic Query" "fail" "document_qa" "$data" "$body" "$duration"
    fi
}

test_document_qa_followup() {
    log_test "Document QA: Follow-up query"
    
    local data="{\"question\":\"tell me more about documentation\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if [ "$code" = "200" ] && echo "$body" | grep -q '"success":true'; then
        log_pass "Document QA: Follow-up OK (${duration}ms)"
        add_result "dq_followup" "Follow-up Query" "pass" "document_qa" "$data" "$body" "$duration"
    else
        log_fail "Document QA: Follow-up failed"
        add_result "dq_followup" "Follow-up Query" "fail" "document_qa" "$data" "$body" "$duration"
    fi
}

test_document_qa_response_structure() {
    log_test "Document QA: Response structure (sources, chunks_used)"
    
    local data="{\"question\":\"what are restraint types\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local body=$(curl -s -X POST "$BASE_URL/chat" -H "Content-Type: application/json" -d "$data")
    
    local has_structure=$(echo "$body" | python3 -c "
import sys, json
d = json.load(sys.stdin)
data = d.get('data', {})
has_sources = 'sources' in data
has_chunks = 'chunks_used' in data
print('pass' if (has_sources and has_chunks) else 'fail')
" 2>/dev/null)
    
    if [ "$has_structure" = "pass" ]; then
        log_pass "Document QA: Response structure OK"
        add_result "dq_structure" "Response Structure" "pass" "document_qa" "$data" "$body" "0"
    else
        log_fail "Document QA: Missing response fields"
        add_result "dq_structure" "Response Structure" "fail" "document_qa" "$data" "$body" "0"
    fi
}

#-------------------------------------------------------------------------------
# Cross-Scope Handler Tests
#-------------------------------------------------------------------------------

test_cross_scope_greeting() {
    log_test "Cross-Scope: Greeting (no scope)"
    
    # Create fresh session
    local data="{\"question\":\"hello\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"facility_ids\":$FACILITY_IDS}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if echo "$body" | grep -qi "SARAH\|hello\|help"; then
        log_pass "Cross-Scope: Greeting handled (${duration}ms)"
        add_result "cs_greeting" "Greeting" "pass" "cross_scope" "$data" "$body" "$duration"
    else
        log_fail "Cross-Scope: Greeting not handled"
        add_result "cs_greeting" "Greeting" "fail" "cross_scope" "$data" "$body" "$duration"
    fi
}

test_cross_scope_help() {
    log_test "Cross-Scope: Help intent"
    
    local data="{\"question\":\"help\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if echo "$body" | grep -qi "Daily Activity\|Documents\|Inmate"; then
        log_pass "Cross-Scope: Help shows scopes (${duration}ms)"
        add_result "cs_help" "Help Intent" "pass" "cross_scope" "$data" "$body" "$duration"
    else
        log_fail "Cross-Scope: Help not showing scopes"
        add_result "cs_help" "Help Intent" "fail" "cross_scope" "$data" "$body" "$duration"
    fi
}

test_cross_scope_capabilities() {
    log_test "Cross-Scope: What can you do"
    
    local data="{\"question\":\"what can you do\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\",\"session_id\":\"$SESSION_ID\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local code=$(echo "$result" | sed -n '2p')
    local duration=$(echo "$result" | tail -1)
    
    if echo "$body" | grep -q '"options"'; then
        log_pass "Cross-Scope: Capabilities shown (${duration}ms)"
        add_result "cs_capabilities" "Capabilities" "pass" "cross_scope" "$data" "$body" "$duration"
    else
        log_fail "Cross-Scope: Capabilities not shown"
        add_result "cs_capabilities" "Capabilities" "fail" "cross_scope" "$data" "$body" "$duration"
    fi
}

#-------------------------------------------------------------------------------
# Streaming & Validation Tests
#-------------------------------------------------------------------------------

test_streaming() {
    log_test "Streaming: SSE endpoint"
    
    local data="{\"question\":\"hello\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\"}"
    local start_time=$(date +%s%3N)
    local body=$(timeout 10 curl -s -N -X POST "$BASE_URL/chat/stream" \
        -H "Content-Type: application/json" \
        -H "Accept: text/event-stream" \
        -d "$data" 2>&1 | head -15)
    local end_time=$(date +%s%3N)
    local duration=$((end_time - start_time))
    
    if echo "$body" | grep -q "event:"; then
        log_pass "Streaming: SSE OK (${duration}ms)"
        add_result "streaming" "SSE Streaming" "pass" "streaming" "$data" "\"SSE events received\"" "$duration"
    else
        log_fail "Streaming: No SSE events"
        add_result "streaming" "SSE Streaming" "fail" "streaming" "$data" "\"No events\"" "$duration"
    fi
}

test_validation_customer_key() {
    log_test "Validation: Invalid customer_key"
    
    local data="{\"question\":\"test\",\"customer_key\":\"invalid@key!\",\"user_id\":\"$USER_ID\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local duration=$(echo "$result" | tail -1)
    
    if echo "$body" | grep -q '"detail"'; then
        log_pass "Validation: Invalid key rejected (${duration}ms)"
        add_result "val_key" "Invalid Key" "pass" "validation" "$data" "$body" "$duration"
    else
        log_fail "Validation: Invalid key not rejected"
        add_result "val_key" "Invalid Key" "fail" "validation" "$data" "$body" "$duration"
    fi
}

test_validation_empty_question() {
    log_test "Validation: Empty question"
    
    local data="{\"question\":\"\",\"customer_key\":\"$CUSTOMER_KEY\",\"user_id\":\"$USER_ID\"}"
    local result=$(do_request POST "/chat" "$data")
    local body=$(echo "$result" | head -1)
    local duration=$(echo "$result" | tail -1)
    
    if echo "$body" | grep -q '"detail"'; then
        log_pass "Validation: Empty question rejected (${duration}ms)"
        add_result "val_empty" "Empty Question" "pass" "validation" "$data" "$body" "$duration"
    else
        log_fail "Validation: Empty question not rejected"
        add_result "val_empty" "Empty Question" "fail" "validation" "$data" "$body" "$duration"
    fi
}

#-------------------------------------------------------------------------------
# Generate Report
#-------------------------------------------------------------------------------

generate_report() {
    local results_json=$(printf '%s\n' "${RESULTS[@]}" | paste -sd ',' -)
    local stm_json=$(printf '%s\n' "${STM_TESTS[@]}" | paste -sd ',' -)
    local ltm_json=$(printf '%s\n' "${LTM_TESTS[@]}" | paste -sd ',' -)
    local scope_json=$(printf '%s\n' "${SCOPE_SWITCH_TESTS[@]}" | paste -sd ',' -)
    local da_json=$(printf '%s\n' "${DAILY_ACTIVITY_TESTS[@]}" | paste -sd ',' -)
    local id_json=$(printf '%s\n' "${INMATE_DATA_TESTS[@]}" | paste -sd ',' -)
    local dq_json=$(printf '%s\n' "${DOCUMENT_QA_TESTS[@]}" | paste -sd ',' -)
    local cs_json=$(printf '%s\n' "${CROSS_SCOPE_TESTS[@]}" | paste -sd ',' -)
    
    cat > "$REPORT_FILE" << EOF
{
  "report": {
    "generated_at": "$(date -Iseconds)",
    "base_url": "$BASE_URL",
    "customer_key": "$CUSTOMER_KEY",
    "facility_ids": $FACILITY_IDS,
    "user_id": "$USER_ID"
  },
  "summary": {
    "total_tests": $TOTAL,
    "passed": $PASSED,
    "failed": $FAILED,
    "pass_rate": "$(awk "BEGIN {printf \"%.1f\", ($PASSED/$TOTAL)*100}")%"
  },
  "categories": {
    "stm_session_management": {
      "description": "Short-Term Memory (Redis) - Session creation, retrieval, updates",
      "tests": [${stm_json:-}]
    },
    "ltm_conversation_history": {
      "description": "Long-Term Memory (DynamoDB) - Conversation persistence across sessions",
      "tests": [${ltm_json:-}]
    },
    "scope_switching": {
      "description": "Scope selection and switching between pipelines",
      "tests": [${scope_json:-}]
    },
    "daily_activity_pipeline": {
      "description": "Rule-based activity checking (refresh only, no follow-ups)",
      "tests": [${da_json:-}]
    },
    "inmate_data_pipeline": {
      "description": "Text-to-SQL queries with multi-turn and follow-ups",
      "tests": [${id_json:-}]
    },
    "document_qa_pipeline": {
      "description": "RAG-based document search with follow-ups",
      "tests": [${dq_json:-}]
    },
    "cross_scope_handlers": {
      "description": "Global intents (greeting, help, capabilities)",
      "tests": [${cs_json:-}]
    }
  },
  "all_tests": [${results_json:-}]
}
EOF
    
    log_info "Report saved: $REPORT_FILE"
}

#-------------------------------------------------------------------------------
# Main
#-------------------------------------------------------------------------------

main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║         InmateCopilot Production Test Suite                       ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    log_info "Base URL: $BASE_URL"
    log_info "Customer: $CUSTOMER_KEY"
    log_info "Facilities: $FACILITY_IDS"
    log_info "User: $USER_ID"
    log_info "Report: $REPORT_FILE"
    
    log_section "1. HEALTH CHECKS"
    test_health
    test_health_deep
    
    log_section "2. STM (Session Management)"
    test_stm_session_create
    test_stm_session_retrieve
    test_stm_session_update
    test_stm_invalid_session
    
    log_section "3. LTM (Conversation History)"
    test_ltm_history_stored
    test_ltm_cross_session
    
    log_section "4. SCOPE SWITCHING"
    test_scope_options
    test_scope_select "daily_activity"
    test_scope_switch
    
    log_section "5. DAILY ACTIVITY PIPELINE"
    test_daily_activity
    test_daily_activity_refresh
    test_daily_activity_response_structure
    test_daily_activity_non_refresh
    
    log_section "6. INMATE DATA PIPELINE"
    test_inmate_data_query
    test_inmate_data_followup
    test_inmate_data_response_structure
    
    log_section "7. DOCUMENT QA PIPELINE"
    test_document_qa_query
    test_document_qa_followup
    test_document_qa_response_structure
    
    log_section "8. CROSS-SCOPE HANDLERS"
    test_cross_scope_greeting
    test_cross_scope_help
    test_cross_scope_capabilities
    
    log_section "9. STREAMING & VALIDATION"
    test_streaming
    test_validation_customer_key
    test_validation_empty_question
    
    # Generate report
    generate_report
    
    # Summary
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                         TEST SUMMARY                              ║"
    echo "╠══════════════════════════════════════════════════════════════════╣"
    printf "║  Passed:  \033[1;32m%-5d\033[0m                                                  ║\n" $PASSED
    printf "║  Failed:  \033[1;31m%-5d\033[0m                                                  ║\n" $FAILED
    printf "║  Total:   %-5d                                                  ║\n" $TOTAL
    printf "║  Rate:    %.1f%%                                                  ║\n" $(awk "BEGIN {printf \"%.1f\", ($PASSED/$TOTAL)*100}")
    echo "╚══════════════════════════════════════════════════════════════════╝"
    
    if [ $FAILED -eq 0 ]; then
        echo ""
        echo -e "\033[1;32m✓ ALL TESTS PASSED!\033[0m"
        exit 0
    else
        echo ""
        echo -e "\033[1;31m✗ SOME TESTS FAILED - Check report for details\033[0m"
        exit 1
    fi
}

main "$@"

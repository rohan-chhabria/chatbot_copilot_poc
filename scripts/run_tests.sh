#!/bin/bash
# Local test runner — Run all test layers before push
# Usage: ./scripts/run_tests.sh [unit|integration|contract|all]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[TEST]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check Redis
check_redis() {
    if ! redis-cli ping > /dev/null 2>&1; then
        warn "Redis not running. Starting via Docker..."
        docker run -d --name copilot-test-redis -p 6379:6379 redis:7-alpine || true
        sleep 2
    fi
}

# Unit tests
run_unit() {
    log "Running unit tests..."
    export SESSION_BACKEND=memory
    export LTM_BACKEND=noop
    pytest tests/unit/ -v --cov=src --cov-report=term-missing
}

# Integration tests
run_integration() {
    log "Running integration tests..."
    check_redis
    export SESSION_BACKEND=redis
    export LTM_BACKEND=noop
    pytest tests/integration/ -v
}

# Contract tests
run_contract() {
    log "Running contract tests..."
    check_redis
    
    # Start server in background
    export SESSION_BACKEND=redis
    export LTM_BACKEND=noop
    uvicorn src.api.handler:app --host 0.0.0.0 --port 8000 &
    SERVER_PID=$!
    sleep 5
    
    # Health check
    if ! curl -sf http://localhost:8000/health > /dev/null; then
        error "Server failed to start"
        kill $SERVER_PID 2>/dev/null || true
        exit 1
    fi
    
    # Run Newman
    if command -v newman &> /dev/null; then
        newman run tests/contract/postman_collection.json \
            --environment tests/contract/env-local.json \
            --reporters cli
    else
        warn "Newman not installed. Run: npm install -g newman"
    fi
    
    # Cleanup
    kill $SERVER_PID 2>/dev/null || true
}

# All tests
run_all() {
    log "Running ALL test layers..."
    run_unit
    run_integration
    run_contract
    log "All tests passed!"
}

# Lint only
run_lint() {
    log "Running linters..."
    ruff check src/ tests/
    ruff format src/ tests/ --check
}

# Main
case "${1:-all}" in
    unit)
        run_unit
        ;;
    integration)
        run_integration
        ;;
    contract)
        run_contract
        ;;
    lint)
        run_lint
        ;;
    all)
        run_lint
        run_all
        ;;
    *)
        echo "Usage: $0 [unit|integration|contract|lint|all]"
        exit 1
        ;;
esac

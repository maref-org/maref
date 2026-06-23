#!/usr/bin/env bash
#
# Verify MAREF Sidecar binary deployment.
#
# Usage:
#   bash packaging/verify-sidecar.sh
#
# Steps:
#   1. Check binary exists
#   2. Run --help
#   3. Start server in background
#   4. Hit GET /api/health (with retry)
#   5. Hit POST /api/mcp (initialize)
#   6. Stop server
#   7. Report
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BINARY="$PROJECT_ROOT/dist/maref-sidecar"
PORT=8999
BASE_URL="http://127.0.0.1:$PORT"
PASS=0
FAIL=0
SERVER_PID=""

cleanup() {
    if [ -n "${SERVER_PID:-}" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        SERVER_PID=""
    fi
}
trap cleanup EXIT

pass() { PASS=$((PASS + 1)); echo "  [PASS] $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  [FAIL] $1"; }

echo "=============================================="
echo "  MAREF Sidecar Binary Verification"
echo "=============================================="
echo ""

# Step 1: Check binary exists
echo "--- Step 1: Binary exists ---"
if [ -f "$BINARY" ]; then
    SIZE=$(du -h "$BINARY" | cut -f1)
    pass "Binary found: $BINARY ($SIZE)"
else
    fail "Binary not found at $BINARY (run packaging/build-sidecar.sh first)"
    echo ""
    echo "Results: $PASS passed, $FAIL failed"
    exit 1
fi
echo ""

# Step 2: --help
echo "--- Step 2: --help ---"
if "$BINARY" --help 2>&1 | grep -q "usage:"; then
    pass "--help works"
else
    fail "--help failed"
fi
echo ""

# Step 3: Start server
echo "--- Step 3: Start server ---"
"$BINARY" --port "$PORT" --host "127.0.0.1" >/tmp/maref-sidecar-test.log 2>&1 &
SERVER_PID=$!
echo "    PID: $SERVER_PID"

# Wait for process to appear
sleep 2

if kill -0 "$SERVER_PID" 2>/dev/null; then
    pass "Server process started (PID $SERVER_PID)"
else
    fail "Server process failed to start"
    cat /tmp/maref-sidecar-test.log 2>/dev/null || true
    echo ""
    echo "Results: $PASS passed, $FAIL failed"
    exit 1
fi
echo ""

# Step 4: GET /api/health (with retry)
echo "--- Step 4: GET /api/health ---"
HEALTH=""
for i in 1 2 3 4 5; do
    sleep 1
    HEALTH=$(curl -s --max-time 3 "$BASE_URL/api/health" 2>/dev/null || echo "")
    if echo "$HEALTH" | grep -q "healthy"; then
        break
    fi
    echo "    Retry $i/5..."
done

if echo "$HEALTH" | grep -q "healthy"; then
    pass "/api/health returned healthy"
else
    fail "/api/health failed after 5 retries (got: $HEALTH)"
fi
echo ""

# Step 5: POST /api/mcp (initialize)
echo "--- Step 5: POST /api/mcp (initialize) ---"
MCP_RESP=$(curl -s --max-time 5 -X POST "$BASE_URL/api/mcp" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}' 2>/dev/null || echo "")
if echo "$MCP_RESP" | grep -q "jsonrpc"; then
    pass "/api/mcp initialize succeeded"
else
    fail "/api/mcp initialize failed (got: $MCP_RESP)"
fi
echo ""

# Step 6: Stop server
echo "--- Step 6: Stop server ---"
if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    SERVER_PID=""
fi
if ! kill -0 "${SERVER_PID:-}" 2>/dev/null; then
    pass "Server stopped"
else
    fail "Server still running"
fi
echo ""

# Results
echo "=============================================="
echo "  Results: $PASS passed, $FAIL failed"
echo "=============================================="

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Server log:"
    cat /tmp/maref-sidecar-test.log 2>/dev/null || true
    exit 1
fi

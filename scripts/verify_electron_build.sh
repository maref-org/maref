#!/usr/bin/env bash
# MAREF Electron Build Verification
# Validates build configuration security settings before packaging.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
WARNINGS=0
FAILED=0

check_pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; PASSED=$((PASSED + 1)); }
check_warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; WARNINGS=$((WARNINGS + 1)); }
check_fail() { echo -e "  ${RED}[FAIL]${NC} $1"; FAILED=$((FAILED + 1)); }

echo "=== MAREF Electron Build Verification ==="
echo ""

# Check hardenedRuntime
if grep -q '"hardenedRuntime": true' gui/package.json; then
    check_pass "hardenedRuntime is enabled"
else
    check_fail "hardenedRuntime is NOT enabled - macOS Gatekeeper will reject"
fi

# Check no unsafe executable memory
if grep -q 'allow-unsigned-executable-memory' gui/package.json; then
    check_fail "allow-unsigned-executable-memory found in package.json"
else
    check_pass "No allow-unsigned-executable-memory in package.json"
fi

if grep -q 'allow-unsigned-executable-memory' gui/electron/entitlements.mac.plist; then
    check_fail "allow-unsigned-executable-memory found in entitlements"
else
    check_pass "No allow-unsigned-executable-memory in entitlements"
fi

# Check no disabled library validation
if grep -q 'disable-library-validation' gui/package.json; then
    check_fail "disable-library-validation found in package.json"
else
    check_pass "No disable-library-validation in package.json"
fi

if grep -q 'disable-library-validation' gui/electron/entitlements.mac.plist; then
    check_fail "disable-library-validation found in entitlements"
else
    check_pass "No disable-library-validation in entitlements"
fi

# Check no disabled executable page protection
if grep -q 'disable-executable-page-protection' gui/package.json; then
    check_fail "disable-executable-page-protection found in package.json"
else
    check_pass "No disable-executable-page-protection in package.json"
fi

# Check asar is enabled
if grep -q '"asar": true' gui/package.json; then
    check_pass "asar packaging enabled"
else
    check_warn "asar packaging not explicitly enabled"
fi

# Check entitlements exist
if [ -f "gui/electron/entitlements.mac.plist" ]; then
    check_pass "entitlements.mac.plist exists"
else
    check_fail "entitlements.mac.plist missing"
fi

# Check .env files not present in build
if compgen -G "**/.env" > /dev/null 2>&1; then
    check_fail ".env files detected - API keys may leak into build"
else
    check_pass "No .env files detected"
fi

# Check code signing
echo ""
echo "--- Code Signing Status (informational) ---"
if [ -n "${APPLE_DEVELOPER_ID:-}" ]; then
    echo "  Apple Developer ID: configured"
else
    check_warn "Apple Developer ID not set - notarization will fail (expected for dev)"
fi

if [ -n "${CSC_LINK:-}" ]; then
    echo "  Windows code signing: configured"
else
    check_warn "Windows code signing not configured (expected for dev)"
fi

echo ""
echo "=== Results ==="
echo -e "  ${GREEN}Passed:  ${PASSED}${NC}"
echo -e "  ${YELLOW}Warnings: ${WARNINGS}${NC}"
echo -e "  ${RED}Failed:  ${FAILED}${NC}"

if [ "$FAILED" -gt 0 ]; then
    echo ""
    echo -e "${RED}BUILD VERIFICATION FAILED - ${FAILED} security issues must be resolved${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Build configuration passes security verification${NC}"

# Print build commands
echo ""
echo "Build commands:"
echo "  pnpm electron:build:mac    # macOS DMG + ZIP (arm64 + x64)"
echo "  pnpm electron:build:win    # Windows NSIS installer (x64)"
echo "  pnpm electron:build:linux  # Linux AppImage + deb (x64)"
echo "  pnpm electron:build        # All platforms"
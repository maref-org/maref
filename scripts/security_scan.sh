#!/bin/bash
#
# MAREF Security Scan Script
# Runs Bandit, pip-audit, and Safety checks
#
set -euo pipefail

echo "=========================================="
echo "  MAREF Security Scan"
echo "=========================================="
echo ""

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

EXIT_CODE=0

# ── Bandit: Static analysis for Python code ──
echo "Running Bandit static analysis..."
if command -v bandit &> /dev/null; then
    bandit -r src/ -f json -o /tmp/bandit-report.json || true
    bandit -r src/ -f txt -ll || EXIT_CODE=$?
else
    echo "⚠ bandit not found. Install: pip install bandit"
fi
echo ""

# ── pip-audit: Check installed packages for known vulnerabilities ──
echo "Running pip-audit..."
if command -v pip-audit &> /dev/null; then
    pip-audit --format json --output /tmp/pip-audit-report.json || EXIT_CODE=$?
    pip-audit || true
else
    echo "⚠ pip-audit not found. Install: pip install pip-audit"
fi
echo ""

# ── Safety: Check dependencies for known vulnerabilities ──
echo "Running Safety check..."
if command -v safety &> /dev/null; then
    safety check --json --output /tmp/safety-report.json || true
    safety check || EXIT_CODE=$?
else
    echo "⚠ safety not found. Install: pip install safety"
fi
echo ""

# ── Summary ──
echo "=========================================="
echo "  Security Scan Summary"
echo "=========================================="

if [[ -f /tmp/bandit-report.json ]]; then
    ISSUES=$(python3 -c "import json; data=json.load(open('/tmp/bandit-report.json')); print(data.get('metrics', {}).get('_totals', {}).get('SEVERITY.UNDEFINED', 0))" 2>/dev/null || echo "N/A")
    echo "  Bandit issues: ${ISSUES}"
fi

if [[ -f /tmp/pip-audit-report.json ]]; then
    VULNS=$(python3 -c "import json; data=json.load(open('/tmp/pip-audit-report.json')); print(len(data.get('dependencies', [])))" 2>/dev/null || echo "N/A")
    echo "  pip-audit vulnerable deps: ${VULNS}"
fi

echo ""
if [[ ${EXIT_CODE} -ne 0 ]]; then
    echo "✗ Security scan found issues (exit code: ${EXIT_CODE})"
else
    echo "✓ Security scan passed"
fi

exit ${EXIT_CODE}

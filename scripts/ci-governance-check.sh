#!/bin/bash
# ci-governance-check.sh — CI governance policy validation
#
# Validates governance setup in CI environments where GaaS HTTP is unavailable.
# Checks: hook presence, policy file validity, constitutional compliance.
# Exits 0 if all checks pass, 1 otherwise.

set -e
echo "🔍 CI Governance Check — $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

VIOLATIONS=0

# Check 1: Hook files exist
echo "--- Hook presence ---"
for hook in .git/hooks/pre-push .git/hooks/pre-commit; do
    if [ -f "$hook" ]; then
        echo "  ✅ $hook present"
    else
        echo "  ⚠️  $hook missing (non-fatal in CI)"
    fi
done

# Check 2: hook-gaas-client.py exists
if [ -f "scripts/hook-gaas-client.py" ]; then
    echo "  ✅ scripts/hook-gaas-client.py present"
else
    echo "  ❌ scripts/hook-gaas-client.py missing"
    VIOLATIONS=$((VIOLATIONS + 1))
fi

# Check 3: .gaas_api_key not tracked (gitignored)
if [ -f ".gitignore" ]; then
    if grep -q "gaas_api_key" .gitignore 2>/dev/null; then
        echo "  ✅ .gaas_api_key in .gitignore"
    else
        echo "  ⚠️  .gaas_api_key NOT in .gitignore"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
fi

# Check 4: governance_router.py has git policies
if [ -f "src/maref/gaas/governance_router.py" ]; then
    if grep -q "git.push" src/maref/gaas/governance_router.py 2>/dev/null; then
        echo "  ✅ governance_router.py has git.push policy"
    else
        echo "  ❌ governance_router.py missing git.push policy"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
    if grep -q "git.commit" src/maref/gaas/governance_router.py 2>/dev/null; then
        echo "  ✅ governance_router.py has git.commit policy"
    else
        echo "  ❌ governance_router.py missing git.commit policy"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
else
    echo "  ⚠️  governance_router.py not found (maybe GaaS not deployed)"
fi

# Check 5: GaaS sidecar bridge exists (if sidecar directory present)
if [ -d "src/sidecar" ]; then
    if [ -f "src/sidecar/gaas_router.py" ]; then
        echo "  ✅ GaaS sidecar bridge present"
    else
        echo "  ⚠️  GaaS sidecar bridge missing (sidecar dir exists)"
    fi
fi

# Check 6: CLAUDE.md contains constitutional requirements (if file exists)
if [ -f "CLAUDE.md" ]; then
    PATTERNS="Athena 系统宪法\|安全红线\|宪法优先"
    MATCHES=0
    for pattern in $(echo "$PATTERNS" | tr '|' ' '); do
        if grep -q "$pattern" CLAUDE.md 2>/dev/null; then
            MATCHES=$((MATCHES + 1))
        fi
    done
    if [ "$MATCHES" -eq 3 ]; then
        echo "  ✅ CLAUDE.md constitutional compliance"
    else
        echo "  ⚠️  CLAUDE.md missing $((3 - MATCHES)) constitutional patterns"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
fi

echo ""
if [ "$VIOLATIONS" -gt 0 ]; then
    echo "❌ CI Governance Check: FAILED ($VIOLATIONS violations)"
    exit 1
fi
echo "✅ CI Governance Check: PASSED"

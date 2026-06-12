#!/bin/bash
# ci-governance-check.sh — CI governance policy validation for MAREF open-source
#
# Validates governance setup in CI environments.
# Checks: hook presence, policy file validity, CLAUDE.md compliance.

set -e
echo "🔍 CI Governance Check — MAREF open-source — $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

VIOLATIONS=0

# Check 1: Hook files exist
echo "--- Hook presence ---"
for hook in .git/hooks/pre-push; do
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
if [ -f ".gitignore" ] && grep -q "gaas_api_key" .gitignore 2>/dev/null; then
    echo "  ✅ .gaas_api_key in .gitignore"
fi

# Check 4: governance_router.py has git policies
if [ -f "src/maref/gaas/governance_router.py" ]; then
    has_git_push=false
    has_git_commit=false
    grep -q "git.push" src/maref/gaas/governance_router.py && has_git_push=true
    grep -q "git.commit" src/maref/gaas/governance_router.py && has_git_commit=true
    if [ "$has_git_push" = true ]; then
        echo "  ✅ governance_router.py has git.push policy"
    else
        echo "  ❌ governance_router.py missing git.push policy"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
    if [ "$has_git_commit" = true ]; then
        echo "  ✅ governance_router.py has git.commit policy"
    else
        echo "  ❌ governance_router.py missing git.commit policy"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
fi

# Check 5: GaaS sidecar bridge
if [ -f "src/sidecar/gaas_router.py" ]; then
    echo "  ✅ GaaS sidecar bridge present"
fi

# Check 6: MCP security policy config exists
if [ -f "configs/mcp_security_policy.json" ]; then
    echo "  ✅ MCP security policy config present"
fi

# Check 7: Audit logger module exists
if [ -f "src/maref/integration/audit_logger.py" ]; then
    echo "  ✅ audit_logger.py present"
fi

# Check 8: CLAUDE.md compliance
if [ -f "CLAUDE.md" ]; then
    required="Athena 系统宪法|安全红线|MAREF 自治理|宪法优先"
    matches=0
    for pattern in $(echo "$required" | tr '|' ' '); do
        grep -q "$pattern" CLAUDE.md 2>/dev/null && matches=$((matches + 1))
    done
    if [ "$matches" -eq 4 ]; then
        echo "  ✅ CLAUDE.md full compliance (4/4)"
    else
        echo "  ⚠️  CLAUDE.md $matches/4 constitutional patterns"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
fi

echo ""
if [ "$VIOLATIONS" -gt 0 ]; then
    echo "❌ CI Governance Check: FAILED ($VIOLATIONS violations)"
    exit 1
fi
echo "✅ CI Governance Check: PASSED"

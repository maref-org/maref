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

# Check 6b: Constitution file present (upper-law chain integrity)
# docs/CONSTITUTION.md is the constitutional anchor cited by AGENTS.md, CLAUDE.md,
# docs/oss-execution-norm-v1.0.md and docs/release-gate.md. Its absence breaks the
# upper-law chain — the exact vacuum that previously let the SkillOS handbook in.
echo "--- Constitution upper-law anchor ---"
if [ -f "docs/CONSTITUTION.md" ]; then
    echo "  ✅ docs/CONSTITUTION.md present"
else
    echo "  ❌ docs/CONSTITUTION.md missing — upper-law chain broken (Constitution Art. 1)"
    VIOLATIONS=$((VIOLATIONS + 1))
fi
if [ -f "docs/release-gate.md" ]; then
    echo "  ✅ docs/release-gate.md present (MAREF self-owned gate)"
else
    echo "  ⚠️  docs/release-gate.md missing (risk: external-handbook fallback)"
    VIOLATIONS=$((VIOLATIONS + 1))
fi

# Check 7: Upper-law citation whitelist (Constitution Art. 11 — cross-repo governance)
# Anywhere a line declares a governance basis ("审计依据"/"上位法"/"门禁依据"/"发布依据"),
# it must NOT cite external project handbooks (SkillOS / ENG-*-HANDBOOK etc.) as authority.
# External handbooks may only appear as descriptive "参考资料"/"取代" references (allowed).
echo "--- Upper-law citation whitelist (Constitution Art. 11) ---"
UPPER_LAW_BASES='审计依据|上位法|门禁依据|发布依据|审计标准|验收依据'
EXTERNAL_HANDBOOKS='SKILLOS-|产品级发布全量验收标准与评审流程手册|Release Acceptance Handbook|ENG-RELEASE-HANDBOOK|SkillOS-RELEASE'
POLLUTED=""
# Defensive-context markers: when present, the external-handbook mention is
# descriptive (defining the refusal / replacement / reference policy) rather
# than an authoritative citation. Such lines are exempted.
DEFENSIVE_MARKERS='无 .*SKILLOS|污染|回潮|取代|拒绝|外部项目手册|参考资料|不可作为依据|不得作为|External handbooks may only|External-handbook|external-handbook|作为 MAREF 审计|External handbooks'
while IFS= read -r file; do
    [ -z "$file" ] && continue
    # Lines that (a) declare a governance basis AND (b) mention an external
    # handbook, but (c) are NOT in a defensive context, are pollution.
    while IFS= read -r line; do
        echo "  ❌ $file: external-handbook cited as governance basis -> $line"
        POLLUTED=1
    done < <(grep -nE "$UPPER_LAW_BASES" "$file" 2>/dev/null \
              | grep -E "$EXTERNAL_HANDBOOKS" \
              | grep -vE "$DEFENSIVE_MARKERS")
done < <(find docs -type f -name '*.md' 2>/dev/null; ls *.md 2>/dev/null)
if [ -n "$POLLUTED" ]; then
    VIOLATIONS=$((VIOLATIONS + 1))
else
    echo "  ✅ No external-handbook pollution in governance-basis citations"
fi

echo ""
if [ "$VIOLATIONS" -gt 0 ]; then
    echo "❌ CI Governance Check: FAILED ($VIOLATIONS violations)"
    exit 1
fi
echo "✅ CI Governance Check: PASSED"

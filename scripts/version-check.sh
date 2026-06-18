#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# MAREF Version Consistency Checker
# ──────────────────────────────────────────────────────────
# Ensures version strings are consistent across all config files.
# Usage: bash scripts/version-check.sh [--fix]

set -euo pipefail

GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"

# Collect all expected versions from authoritative source (pyproject.toml)
EXPECTED_VERSION=$(python3 -c "import tomllib; f=open('$GIT_ROOT/pyproject.toml','rb'); d=tomllib.load(f); print(d['project']['version'])" 2>/dev/null || echo "unknown")

echo "=== MAREF Version Consistency Check ==="
echo "Expected version: $EXPECTED_VERSION"
echo ""

ERRORS=0

check_file() {
    local file="$1"
    local pattern="$2"
    local desc="$3"
    local version

    if [ ! -f "$file" ]; then
        echo "  [MISSING] $desc — file not found at $file"
        ERRORS=$((ERRORS + 1))
        return
    fi

    version=$(grep -E "$pattern" "$file" | grep -Eo '["\x27]?[0-9]+\.[0-9]+\.[0-9]+[-a-zA-Z0-9]*' | head -1 | sed 's/["\x27]//g' || echo "")
    if [ -z "$version" ]; then
        echo "  [SKIP] $desc — no version pattern found"
        return
    fi

    if [ "$version" = "$EXPECTED_VERSION" ]; then
        echo "  [OK]   $desc ($version)"
    else
        echo "  [FAIL] $desc — expected $EXPECTED_VERSION, got $version"
        ERRORS=$((ERRORS + 1))
    fi
}

check_file "$GIT_ROOT/pyproject.toml" '^version\s*=' 'pyproject.toml'
check_file "$GIT_ROOT/Dockerfile" 'org\.opencontainers\.image\.version' 'Dockerfile LABEL'
check_file "$GIT_ROOT/src/maref/__init__.py" '__version__' 'maref/__init__.py'
check_file "$GIT_ROOT/src/maref/agent_card_config.py" 'AGENT_VERSION' 'agent_card_config.py'
check_file "$GIT_ROOT/gui/package.json" '"version"' 'gui/package.json'
check_file "$GIT_ROOT/STATE.yaml" 'current_release' 'STATE.yaml'
check_file "$GIT_ROOT/CHANGELOG.md" '^## \[' 'CHANGELOG.md (latest)'

echo ""
if [ $ERRORS -eq 0 ]; then
    echo "All version strings consistent."
else
    echo "$ERRORS file(s) have version mismatches."
    if [ "${1:-}" = "--fix" ]; then
        echo "Auto-fix not yet implemented. Fix manually."
    fi
    exit 1
fi

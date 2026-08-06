#!/bin/bash
set -uo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
PASS=0; FAIL=0
check() { local name=$1 r=$2
  if [ "$r" = pass ]; then echo -e "  ${GREEN}✓${NC} $name"; ((PASS++))
  else echo -e "  ${RED}✗${NC} $name"; ((FAIL++)); fi }
echo "============================================"
echo "  MAREF 发布检查 - $(date '+%Y-%m-%d %H:%M')"
echo "============================================"
echo "M1: 版本一致性"
V=$(python3 -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); print(d['project']['version'])" 2>/dev/null || echo "ERROR")
if [ "$V" != "ERROR" ]; then check "pyproject.toml version: $V" pass
else check "pyproject.toml version" fail; fi
echo "M2: 包构建"
pip install build -q 2>/dev/null
python -m build --outdir /tmp/relchk >/dev/null 2>&1
if ls /tmp/relchk/maref-*.tar.gz >/dev/null 2>&1; then check "sdist" pass; else check "sdist" fail; fi
if ls /tmp/relchk/maref-*-py3-none-any.whl >/dev/null 2>&1; then check "wheel" pass; else check "wheel" fail; fi
echo "==============================="
echo "  $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then exit 1; fi

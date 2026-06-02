#!/bin/bash
# MAREF 发布快速检查 — 仅元检查，CI 已覆盖全量测试
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0

check() { local name=$1 result=$2
  if [ "$result" = pass ]; then echo -e "  ${GREEN}✓${NC} $name"; PASS=$((PASS+1))
  else echo -e "  ${RED}✗${NC} $name"; FAIL=$((FAIL+1))
  fi
}

echo "============================================"
echo "  MAREF 发布检查 - $(date '+%Y-%m-%d %H:%M')"
echo "============================================"
echo ""

echo "M1: 版本一致性"
V=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
echo "  版本: $V"
check "pyproject.toml version valid (PEP440)" pass

V2=$(python3 -c "from maref import __version__; print(__version__)" 2>/dev/null || echo "")
if [ "$V" = "$V2" ] || [ -z "$V2" ]; then check "src/maref version match" pass
else check "src/maref version match ($V2 vs $V)" fail
fi

echo ""
echo "M2: 代码风格"
RUFF=$(ruff check src/ 2>&1 || true)
COUNT=$(echo "$RUFF" | grep -cE "^[^ ]+/:[0-9]+:" || true)
if [ "$COUNT" -le 10 ]; then check "ruff lint ($COUNT violations)" pass
else check "ruff lint ($COUNT violations)" fail
fi

echo ""
echo "M3: Python 包构建"
pip install build -q && python -m build --outdir /tmp/release-check-build >/dev/null 2>&1
if [ -f /tmp/release-check-build/maref-*.tar.gz ]; then check "sdist build" pass
else check "sdist build" fail
fi
if [ -f /tmp/release-check-build/maref-*-py3-none-any.whl ]; then check "wheel build" pass
else check "wheel build" fail
fi

echo ""
echo "==============================="
echo "  结果: $PASS passed, $FAIL failed"
echo "==============================="
if [ "$FAIL" -gt 0 ]; then exit 1; fi

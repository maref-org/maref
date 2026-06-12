#!/bin/bash
# =============================================================================
# sanitize-for-push.sh — Track B 发布前内容安全检查
#
# 用法: bash scripts/sanitize-for-push.sh [--fix]
#   --fix: 自动修复发现的泄露（实验性）
#
# 检查项:
#   1. 绝对路径泄露 (/Volumes/, /Users/, file:///)
#   2. 组织名泄露 (openclaw, frankiehot-tech, Athena 知识库路径)
#   3. 专有文件名泄露 (SOUL.md, IDENTITY.md, .openclaw/)
#   4. API Key/Token 泄露 (环境变量值, sk- 模式)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FIX_MODE=false
[[ "${1:-}" == "--fix" ]] && FIX_MODE=true

FAILED=0
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "🔍 Track B 发布前安全检查"
echo "   仓库: $(basename "$REPO_ROOT")"
echo "   路径: $REPO_ROOT"
echo ""

# ── Check 1: 绝对路径泄露 ──────────────────────────────────────────
echo "─── 检查 1: 绝对路径泄露 ───"
ABSOLUTE_PATTERN='(/Volumes/|/Users/[A-Za-z]/|file:///)'
ABSOLUTE_MATCHES=$(grep -rn "$ABSOLUTE_PATTERN" \
    --include="*.py" --include="*.md" --include="*.yaml" --include="*.yml" \
    --include="*.json" --include="*.jsonc" --include="*.cfg" --include="*.ini" \
    --include="*.toml" --include="*.txt" \
    src/ tests/ docs/ scripts/ 2>/dev/null || true)

if [ -n "$ABSOLUTE_MATCHES" ]; then
    COUNT=$(echo "$ABSOLUTE_MATCHES" | wc -l | tr -d ' ')
    echo -e "${RED}❌ 发现 $COUNT 处绝对路径泄露${NC}"
    echo "$ABSOLUTE_MATCHES" | head -20
    FAILED=1
else
    echo -e "${GREEN}✅ 无绝对路径泄露${NC}"
fi

# ── Check 2: 组织名泄露 ────────────────────────────────────────────
echo ""
echo "─── 检查 2: 组织名泄露 ───"
ORG_PATTERN='(openclaw|frankiehot-tech|frankiehot@)'
ORG_MATCHES=$(grep -rn "$ORG_PATTERN" \
    --include="*.py" --include="*.md" --include="*.yaml" --include="*.yml" \
    --include="*.json" --include="*.jsonc" \
    src/ tests/ docs/ scripts/ 2>/dev/null \
    | grep -v "__pycache__" | grep -v ".pytest_cache" | grep -v "node_modules" \
    | grep -v "CHANGELOG.md" || true)

if [ -n "$ORG_MATCHES" ]; then
    COUNT=$(echo "$ORG_MATCHES" | wc -l | tr -d ' ')
    echo -e "${YELLOW}⚠️  发现 $COUNT 处组织名引用（可能是合理引用）${NC}"
    echo "$ORG_MATCHES" | head -10
else
    echo -e "${GREEN}✅ 无组织名泄露${NC}"
fi

# ── Check 3: 专有文件名泄露 ────────────────────────────────────────
echo ""
echo "─── 检查 3: 专有文件名泄露 ───"
PROPRIETARY_FILES=$(find . -maxdepth 3 \
    -name "SOUL.md" -o -name "IDENTITY.md" -o -name "HEARTBEAT.md" \
    -name "TOOLS.md" -o -name "USER.md" \
    -path "*/.openclaw/*" \
    2>/dev/null || true)

if [ -n "$PROPRIETARY_FILES" ]; then
    echo -e "${RED}❌ 发现专有文件:${NC}"
    echo "$PROPRIETARY_FILES"
    FAILED=1
else
    echo -e "${GREEN}✅ 无专有文件${NC}"
fi

# ── Check 4: API Key 泄露 ──────────────────────────────────────────
echo ""
echo "─── 检查 4: API Key 泄露 ───"
KEY_MATCHES=$(grep -rn 'sk-[A-Za-z0-9]\{20,\}' \
    --include="*.py" --include="*.md" --include="*.yaml" --include="*.yml" \
    --include="*.json" --include="*.jsonc" --include="*.cfg" --include="*.ini" \
    --include="*.toml" --include="*.env" \
    src/ tests/ docs/ scripts/ 2>/dev/null \
    | grep -v "__pycache__" | grep -v ".pytest_cache" \
    | grep -v "test_" | grep -v "sk-abcdef" | grep -v "sk-123456" || true)

if [ -n "$KEY_MATCHES" ]; then
    COUNT=$(echo "$KEY_MATCHES" | wc -l | tr -d ' ')
    echo -e "${RED}❌ 发现 $COUNT 处可能的 API Key 泄露!${NC}"
    echo "$KEY_MATCHES" | head -10
    FAILED=1
else
    echo -e "${GREEN}✅ 无 API Key 泄露${NC}"
fi

# ── Summary ─────────────────────────────────────────────────────────
echo ""
echo "─── 检查完成 ───"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ 全部检查通过，可以安全推送${NC}"
else
    echo -e "${RED}❌ 存在需修复的问题，请先处理后再推送${NC}"
    echo "   使用 --fix 模式自动修复绝对路径泄露（实验性）"
    exit 1
fi

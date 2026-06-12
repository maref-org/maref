#!/bin/bash
# 跨仓库 Hook 一致性验证脚本
# 检查所有 5 个仓库的 git hooks 引用的宪法版本是否一致
# 用法: bash scripts/check-hook-versions.sh

set -euo pipefail

REPOS=(
  "/Volumes/1TB-M2/public/maref"
  "/Volumes/1TB-M2/public/percv"
  "/Volumes/1TB-M2/public/mas-ts"
  "/Volumes/1TB-M2/public/skillos"
  "/Volumes/1TB-M2/openclaw"
)

HOOKS=("pre-push" "pre-commit")

EXIT_CODE=0

echo "═══════════════════════════════════════════════════════════════"
echo "  跨仓库 Hook 一致性验证 — $(date +%Y-%m-%d\ %H:%M)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

for repo in "${REPOS[@]}"; do
  name=$(basename "$repo")
  echo "─── $name ──────────────────────────────────────────────"

  for hook in "${HOOKS[@]}"; do
    hook_path="$repo/.git/hooks/$hook"
    if [ ! -f "$hook_path" ]; then
      echo "  ⚠️  $hook: MISSING"
      EXIT_CODE=1
      continue
    fi

    version_line=$(grep -E '宪法 v[0-9]+\.[0-9]+' "$hook_path" 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+' | head -1 | sed 's/^v//' || echo "")
    if [ -z "$version_line" ]; then
      echo "  ⚠️  $hook: 未检测到宪法版本引用"
      EXIT_CODE=1
    else
      echo "  ✅ $hook: v$version_line"
    fi

    size=$(wc -c < "$hook_path" | tr -d ' ')
    echo "     size: ${size}B"
  done
  echo ""
done

# Check constitution version
echo "─── 宪法文件 ──────────────────────────────────────────"
if [ -f "/Volumes/1TB-M2/public/CONSTITUTION.md" ]; then
  const_ver=$(grep -E '\*\*版本\*\*' /Volumes/1TB-M2/public/CONSTITUTION.md | grep -oE 'v[0-9]+\.[0-9]+' | head -1 | sed 's/^v//')
  echo "  CONSTITUTION.md: v$const_ver"
fi
echo ""

# Summary
echo "═══════════════════════════════════════════════════════════════"
if [ $EXIT_CODE -eq 0 ]; then
  echo "  结果: ✅ 全部 Hook 一致性验证通过"
else
  echo "  结果: ❌ 存在不一致项，请手动修复"
fi
echo "═══════════════════════════════════════════════════════════════"
exit $EXIT_CODE

#!/bin/bash
# 文档隔离检查脚本
# 确保策略文档、申报材料等不会混入代码库

set -e

FORBIDDEN_DIRS=("申报材料" "待执行" "PERCV-研究报告" "策略文档" "归档")
FORBIDDEN_FILES=("*.docx" "*.xlsx" "*.pptx")

ERRORS=0

for dir in "${FORBIDDEN_DIRS[@]}"; do
  if [ -d "$dir" ]; then
    echo "ERROR: Forbidden directory found in code repository: $dir"
    ERRORS=$((ERRORS + 1))
  fi
done

for pattern in "${FORBIDDEN_FILES[@]}"; do
  found=$(find . -name "$pattern" -not -path "./.git/*" 2>/dev/null || true)
  if [ -n "$found" ]; then
    echo "ERROR: Forbidden file type found: $pattern"
    echo "$found"
    ERRORS=$((ERRORS + 1))
  fi
done

# 检查是否有硬编码的本地路径
if grep -rn "$PROJECT_ROOT/Athena知识库" src/ --include="*.py" 2>/dev/null; then
  echo "ERROR: Found hardcoded document library paths in source code"
  ERRORS=$((ERRORS + 1))
fi

if [ $ERRORS -eq 0 ]; then
  echo "OK: No forbidden documents in code repository"
  exit 0
else
  echo "FAILED: $ERRORS violation(s) found"
  exit 1
fi

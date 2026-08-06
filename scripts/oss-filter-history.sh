#!/bin/bash
# ============================================================
# oss-filter-history.sh — 一次性公开仓历史清理（git-filter-repo）
# ------------------------------------------------------------
# 目的: 剔除公开仓历史中的闭源深水区/敏感路径（§13.5 步骤 3）。
#       仅在【正式对外宣传/融资/大范围分发前】执行一次。
# 警告: 改写全部 commit hash，invalidate 所有 fork/PR/CI badge。
#       必须在【临时克隆】上运行，勿在工作仓直接执行。
#
# 用法（在临时克隆内，如 /tmp/maref-filter）:
#   bash /path/to/maref/scripts/oss-filter-history.sh [--dry-run]
#   --dry-run  只打印计划路径，不实际改写
#
# 前置:
#   pip install git-filter-repo
# 后置（确认干净后）:
#   git push origin --force --all && git push origin --force --tags
# ============================================================
set -uo pipefail

LIST="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/oss-exclude-list.txt}"
DRY=0
[ "${2:-}" = "--dry-run" ] && DRY=1

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'

if [ "$DRY" -eq 0 ] && ! command -v git-filter-repo >/dev/null 2>&1; then
  echo -e "${RED}[filter] 未安装 git-filter-repo，请先: pip install git-filter-repo${NC}" >&2
  exit 2
fi
if [ ! -f "$LIST" ]; then
  echo -e "${RED}[filter] 排除清单不存在: $LIST${NC}" >&2
  exit 2
fi

# 从清单构建 filter-repo 参数（精确路径用 --path，含通配符用 --path-glob）
ARGS=()
PATH_CNT=0; GLOB_CNT=0
while IFS= read -r line; do
  line="${line%%#*}"
  line="$(echo "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [ -z "$line" ] && continue
  if [[ "$line" == *[\*\?\[\]]* ]]; then
    ARGS+=(--path-glob "$line"); GLOB_CNT=$((GLOB_CNT + 1))
  else
    ARGS+=(--path "$line"); PATH_CNT=$((PATH_CNT + 1))
  fi
done < "$LIST"

echo "============================================"
echo "  MAREF 公开仓历史清理（filter-repo）"
echo "  精确路径: $PATH_CNT 个 | glob 路径: $GLOB_CNT 个"
echo "  模式: $([ "$DRY" -eq 1 ] && echo DRY-RUN || echo EXECUTE)"
echo "============================================"

if [ "$DRY" -eq 1 ]; then
  echo "将执行的 filter-repo 参数："
  printf '  %s\n' "${ARGS[@]}"
  exit 0
fi

if [ -n "$(git remote -v)" ]; then
  echo -e "${YELLOW}[filter] 当前目录有 remote —— 请在【临时克隆】运行（无 remote 或已移除 origin）${NC}"
  read -r -p "继续? [y/N] " ans; [ "$ans" = "y" ] || exit 1
fi

echo "[1/2] 执行 git-filter-repo --invert-paths ..."
git filter-repo --force --invert-paths "${ARGS[@]}" || exit 1

echo "[2/2] 验证历史已剔除深水区（逐条清单断言）..."
LEFT=0
while IFS= read -r pat; do
  pat="${pat%%#*}"
  pat="$(echo "$pat" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [ -z "$pat" ] && continue
  CNT="$(git log --all --oneline -- ":(glob)${pat}" 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${CNT:-0}" -gt 0 ]; then
    echo -e "  ${RED}✗ 历史残留 ${CNT} 条: ${pat}${NC}"
    LEFT=$((LEFT + CNT))
  fi
done < "$LIST"
if [ "$LEFT" -eq 0 ]; then
  echo -e "  ${GREEN}✓ 全部排除路径历史残留为 0${NC}"
else
  echo -e "${RED}[filter] 仍有 ${LEFT} 条历史残留，检查排除清单后重跑。${NC}" >&2
  exit 1
fi

echo "============================================"
echo -e "${GREEN}  清理完成。确认干净后推送：${NC}"
echo "  git push origin --force --all && git push origin --force --tags"
echo "============================================"

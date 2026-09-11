#!/bin/bash
# ============================================================
# oss-publish.sh — MAREF 闭源分支裁剪 → 公开发布分支
# ------------------------------------------------------------
# 用法:
#   scripts/oss-publish.sh [SOURCE] [TARGET] [--dry-run]
#     SOURCE  源分支（含内部/敏感文件的完整分支），默认 HEAD
#     TARGET  生成的目标公开分支名，默认 oss-release
#     --dry-run 仅统计将被裁剪的污染文件，不改写任何分支
#
# 策略: 快照裁剪（Snapshot Purge）
#   - 从 SOURCE 复制到 TARGET（保留完整历史）
#   - 在 TARGET 顶端追加一个"清除污染" commit，删除命中
#     oss-exclude-list.txt 的所有路径（.missions/、data/、
#     coverage 副本 *.cover、闭源实现、营销文档、model_registry 等）
#   - 不重写历史（与 MAREF 治理决策一致，避免 filter-branch 的
#     性能/安全风险与 fork 基线破坏），只保证公开分支 tree 干净
#
# 安全:
#   - SOURCE 分支永远不被修改（只基于其创建 TARGET）
#   - --dry-run 只读，零副作用
#   - TARGET 顶端 commit 有明确标识，可追溯
# ============================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXCLUDE_LIST="${OSS_EXCLUDE_LIST:-$ROOT/scripts/oss-exclude-list.txt}"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'

SOURCE="${1:-HEAD}"
TARGET="${2:-oss-release}"
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
  esac
done

if [ ! -f "$EXCLUDE_LIST" ]; then
  echo -e "${RED}[oss-publish] 缺少排除清单: $EXCLUDE_LIST${NC}" >&2
  exit 2
fi

# ---- 解析排除清单为 PATTERNS 数组（与 oss-check.sh 同逻辑） ----
PATTERNS=()
while IFS= read -r line; do
  line="${line%%#*}"
  line="$(echo "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [ -z "$line" ] && continue
  PATTERNS+=("$line")
  case "$line" in
    *[\*\?\[\]]*|*/) ;;
    *) PATTERNS+=("**/${line}") ;;
  esac
done < "$EXCLUDE_LIST"

# ---- 收集 SOURCE 全 tree 中命中排除清单的路径 ----
FILES="$(git -C "$ROOT" -c core.quotePath=false ls-tree -r --name-only "$SOURCE" 2>/dev/null)"
if [ $? -ne 0 ]; then
  echo -e "${RED}[oss-publish] 无法解析源分支: $SOURCE${NC}" >&2
  exit 2
fi

POLLUTED=()
while IFS= read -r f; do
  [ -z "$f" ] && continue
  for pat in "${PATTERNS[@]}"; do
    if [[ "$f" == $pat ]]; then
      POLLUTED+=("$f")
      break
    fi
  done
done <<< "$FILES"

COUNT="${#POLLUTED[@]}"
if [ "$COUNT" -eq 0 ]; then
  echo -e "${GREEN}[oss-publish] 源分支($SOURCE) 无污染文件，可直接作为公开分支${NC}"
  echo -e "${GREEN}[oss-publish] 提示: 推送前建议再跑 $ROOT/scripts/oss-check.sh $TARGET 终检${NC}"
  exit 0
fi

echo -e "${YELLOW}[oss-publish] 源分支($SOURCE) 发现 $COUNT 个污染文件，将被裁剪:${NC}"
printf '  ✗ %s\n' "${POLLUTED[@]:0:20}"
[ "$COUNT" -gt 20 ] && echo "  ... (共 $COUNT 个，省略余下 $((COUNT - 20)) 个)"

# ---- dry-run: 到此为止 ----
if [ "$DRY_RUN" -eq 1 ]; then
  echo -e "${YELLOW}[oss-publish] [dry-run] 未改写任何分支。若确认，运行: scripts/oss-publish.sh $SOURCE $TARGET${NC}"
  exit 0
fi

# ---- 实际裁剪：基于 SOURCE 创建 TARGET 并追加清除 commit ----
START_BRANCH="$(git -C "$ROOT" branch --show-current 2>/dev/null || echo detached)"
git -C "$ROOT" branch -D "$TARGET" >/dev/null 2>&1 || true

# 用 worktree 隔离，避免污染当前工作区；结束后清理
WORKTREE="$ROOT/.oss-publish-worktree"
rm -rf "$WORKTREE"
git -C "$ROOT" worktree add -q -B "$TARGET" "$WORKTREE" "$SOURCE"

(
  cd "$WORKTREE" || exit 1
  # 删除所有命中路径（仅 stage 删除）
  git rm -r -q --cached --ignore-unmatch "${POLLUTED[@]}" >/dev/null 2>&1
  git commit -q -m "chore(oss): 裁剪污染路径（$COUNT 个）— oss-publish.sh 生成公开分支

源分支: $SOURCE
裁剪项: 命中 scripts/oss-exclude-list.txt 的闭源/内部/敏感路径
包括: .missions/ data/ coverage 副本(*.cover) 闭源实现 营销文档 等"
)

# ---- 把裁剪后的分支 ref 拿回主仓库，清理 worktree ----
git -C "$ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || rm -rf "$WORKTREE"
rm -rf "$WORKTREE"

# ---- 终检（用绝对路径） ----
CHECK_SCRIPT="$ROOT/scripts/oss-check.sh"
if bash "$CHECK_SCRIPT" "$TARGET" >/dev/null 2>&1; then
  echo -e "${GREEN}[oss-publish] 裁剪完成: $TARGET 已通过 oss-check 终检${NC}"
  echo -e "${GREEN}[oss-publish] 可推送: git push origin $TARGET${NC}"
else
  echo -e "${RED}[oss-publish] 裁剪后 $TARGET 仍含污染，请检查排除清单${NC}" >&2
  exit 1
fi

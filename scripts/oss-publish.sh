#!/bin/bash
# ============================================================
# oss-publish.sh — MAREF 开源发布（裁剪闭源深水区 → oss-release 分支）
# ------------------------------------------------------------
# 用法:
#   scripts/oss-publish.sh [-s <src_branch|commit>] [-t <tag>] [--push] [--dry-run]
#   -s   源分支/commit（默认当前 HEAD）
#   -t   标签名（默认 <版本>-oss，从 pyproject.toml 读取）
#   --push    推送到 origin（oss-release 分支 + tag）
#   --dry-run 只打印计划，不实际改动
# 流程:
#   1) 校验工作区干净
#   2) 基于 -s 重建 oss-release 分支
#   3) 按 scripts/oss-exclude-list.txt 从 index 移除闭源/敏感路径
#   4) 提交 "chore(oss): exclude closed-source layers"
#   5) oss-check.sh 复核 tree 已干净
#   6) （可选）打 tag / 推送 origin
# 注意:
#   - 仅裁剪当前快照；历史中的深水区残留需一次性 filter-repo 清理（见 §13.5）。
#   - 公开分支(main/oss-release)有 pre-push 门禁双保险。
#   - 所有变量引用统一使用 ${VAR} 大括号（macOS bash 3.2 多字节解析 bug）。
# ============================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXCLUDE_LIST="${ROOT}/scripts/oss-exclude-list.txt"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'

SRC=""
TAG=""
PUSH=0
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    -s) SRC="$2"; shift 2 ;;
    -t) TAG="$2"; shift 2 ;;
    --push) PUSH=1; shift ;;
    --dry-run) DRY=1; shift ;;
    *) echo -e "${RED}未知参数: $1${NC}" >&2; exit 2 ;;
  esac
done

cd "${ROOT}" || exit 2

START_BRANCH="$(git branch --show-current 2>/dev/null || echo '')"

# 失败/退出时恢复原分支（孤儿重建会切换 HEAD，任何中途退出都必须切回）
restore_start_branch() {
  if [ -n "${START_BRANCH:-}" ] && [ "${START_BRANCH}" != "$(git branch --show-current 2>/dev/null)" ]; then
    git checkout -q -f "${START_BRANCH}" 2>/dev/null
  fi
}
trap restore_start_branch EXIT

# 1) 工作区干净校验（除非 dry-run）
if [ "${DRY}" -eq 0 ]; then
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo -e "${RED}[oss-publish] 工作区有未提交改动，先提交或 stash：${NC}" >&2
    git status --short | head -20 >&2
    exit 1
  fi
fi

SRC="${SRC:-HEAD}"
SRC_SHA="$(git rev-parse --verify "${SRC}^{commit}")" || { echo -e "${RED}[oss-publish] 无法解析源 ${SRC}${NC}" >&2; exit 1; }
VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])" 2>/dev/null || echo "dev")"
TAG="${TAG:-${VERSION}-oss}"
DEST_BRANCH="oss-release"

echo "============================================"
echo "  MAREF 开源发布 - $(date '+%Y-%m-%d %H:%M')"
echo "============================================"
echo "  源:        ${SRC}"
echo "  目标分支:  ${DEST_BRANCH}"
echo "  标签:      ${TAG}"
echo "  模式:      $([ "${DRY}" -eq 1 ] && echo DRY-RUN || echo EXECUTE)"
echo "  排除清单:  ${EXCLUDE_LIST}"
echo "--------------------------------------------"

# 2) 预检源 tree 是否命中排除路径
echo "[1/5] 预检源 tree(${SRC}) 深水区命中情况 ..."
if git -C "${ROOT}" ls-tree -r --name-only "${SRC}" 2>/dev/null | grep -q .; then
  "${ROOT}/scripts/oss-check.sh" "${SRC}" >/dev/null 2>&1 || {
    echo -e "${YELLOW}  源 tree 含排除路径（属预期，发布时将裁剪）${NC}"
  }
fi

if [ "${DRY}" -eq 1 ]; then
  echo -e "${GREEN}[DRY-RUN] 将执行：orphan 重建 ${DEST_BRANCH}（无深水区历史），按清单裁剪，提交并$([ "${PUSH}" -eq 1 ] && echo "推送 ${DEST_BRANCH} + tag ${TAG}" || echo "保留本地")${NC}"
  echo -e "${YELLOW}[DRY-RUN] 以下路径将从公开分支移除（示例）：${NC}"
  git ls-tree -r --name-only "${SRC}" 2>/dev/null | while IFS= read -r f; do
    while IFS= read -r line; do
      line="${line%%#*}"; line="$(echo "${line}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
      [ -z "${line}" ] && continue
      if [[ "${f}" == ${line} ]]; then echo "    - ${f}"; break; fi
    done < "${EXCLUDE_LIST}"
  done | head -30
  exit 0
fi

# 3) 重建 oss-release 分支（orphan 单根提交：不继承全仓历史，杜绝深水区历史回流）
echo "[2/5] 基于 ${SRC} (${SRC_SHA:0:8}) 重建 ${DEST_BRANCH}（orphan 单根提交）..."
git checkout -q "${SRC_SHA}" || exit 1
git branch -D "${DEST_BRANCH}" 2>/dev/null || true
git checkout -q --orphan "${DEST_BRANCH}" || { echo -e "${RED}[oss-publish] orphan checkout 失败${NC}" >&2; exit 1; }
git read-tree "${SRC_SHA}" || { echo -e "${RED}[oss-publish] read-tree ${SRC_SHA} 失败${NC}" >&2; exit 1; }

# 4) 从 index 移除排除路径（批量 git rm，保留工作区文件）
echo "[3/5] 从 index 移除闭源/敏感路径 ..."
PATTERNS=()
while IFS= read -r line; do
  line="${line%%#*}"; line="$(echo "${line}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [ -z "${line}" ] && continue
  PATTERNS+=("${line}")
  # 与 oss-check.sh 保持同一模式补丁：无通配符条目补 "**/" 前缀，防嵌套裸文件名（src/x/.env）漏裁
  case "${line}" in
    *[\*\?\[\]]*|*/) ;;                                        # 含通配符或目录尾斜杠：保持原样
    *) PATTERNS+=("**/${line}") ;;                             # 无通配符：补任意层级匹配
  esac
done < "${EXCLUDE_LIST}"

MATCHED=()
while IFS= read -r f; do
  [ -z "${f}" ] && continue
  for pat in "${PATTERNS[@]}"; do
    if [[ "${f}" == ${pat} ]]; then MATCHED+=("${f}"); break; fi
  done
done < <(git ls-files)

if [ "${#MATCHED[@]}" -gt 0 ]; then
  git rm --cached --quiet --ignore-unmatch -- "${MATCHED[@]}"
  echo -e "  ${GREEN}✓${NC} 从 index 移除 ${#MATCHED[@]} 个闭源/敏感路径"
else
  echo -e "${YELLOW}  无已跟踪的排除路径（tree 已干净或全部命中 .gitignore）${NC}"
fi

# 若没有已跟踪的排除路径，可能已裁剪或全部命中 gitignore
if git diff --cached --quiet; then
  echo -e "${YELLOW}  无新增排除变更（tree 已干净或全部命中 .gitignore）${NC}"
else
  git commit -q --no-verify -m "chore(oss): exclude closed-source layers ($(date '+%Y-%m-%d %H:%M'))"
  echo -e "  ${GREEN}✓${NC} 提交裁剪变更"
fi

# 5) 复核
echo "[4/5] 复核 ${DEST_BRANCH} tree 已干净 ..."
if ! "${ROOT}/scripts/oss-check.sh" "${DEST_BRANCH}"; then
  echo -e "${RED}[oss-publish] 裁剪后仍有深水区路径，中止。请检查排除清单。${NC}" >&2
  exit 1
fi

# 6) 打 tag + 推送
if [ "${PUSH}" -eq 1 ]; then
  echo "[5/5] 打标签并推送 origin ..."
  git tag -f -a "${TAG}" -m "MAREF OSS release ${TAG} (closed-source excluded)" "${DEST_BRANCH}"
  if ! git push -q --force-with-lease origin "${DEST_BRANCH}:${DEST_BRANCH}"; then
    echo -e "${RED}✗ 推送 ${DEST_BRANCH} 失败${NC}" >&2; exit 1
  fi
  if ! git push -q --force origin "refs/tags/${TAG}:refs/tags/${TAG}"; then
    echo -e "${RED}✗ 推送 tag ${TAG} 失败${NC}" >&2; exit 1
  fi
  echo -e "${GREEN}✓ 已推送: origin/${DEST_BRANCH} + tag ${TAG}${NC}"
  echo -e "${YELLOW}  注意: 本地 dev/main 分支仍为全仓（含闭源），请勿直接 git push 到公开 remote。${NC}"
else
  echo "[5/5] 完成（未推送）。可用以下命令发布："
  echo -e "  ${GREEN}git push origin ${DEST_BRANCH}:${DEST_BRANCH}${NC}"
  echo -e "  ${GREEN}git push origin refs/tags/${TAG}:refs/tags/${TAG}${NC}"
fi

echo "============================================"
echo "  OSS 发布完成: ${DEST_BRANCH} @ ${TAG}"
echo "============================================"

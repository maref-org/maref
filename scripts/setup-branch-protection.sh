#!/bin/bash
# ============================================================
# setup-branch-protection.sh — 远程分支保护一键设置（gh CLI）
# ------------------------------------------------------------
# 前置: gh auth login（已认证，且有 admin 权限）
# 设置:
#   main        — require PR(≥1 approve) + status checks + 禁 force push
#   oss-release — 禁 force push / 禁删除（仅 maintainer 合并）
# 用法: bash scripts/setup-branch-protection.sh
# ============================================================
set -uo pipefail
REPO="${1:-maref-org/maref}"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'

command -v gh >/dev/null 2>&1 || { echo -e "${RED}未安装 gh CLI${NC}" >&2; exit 2; }
gh auth status >/dev/null 2>&1 || { echo -e "${RED}请先 gh auth login${NC}" >&2; exit 1; }

set_protection() {
  local branch="$1"
  local pr_review="$2"     # JSON 或 null
  local allow_force="$3"   # true/false（oss-release 需允许 force push 以重建发布产物）
  echo -e "${GREEN}[protect] 设置 $branch ...${NC}"
  local body
  body="$(python3 -c 'import json,sys
pr = json.loads(sys.argv[1])
force = json.loads(sys.argv[2])
print(json.dumps({
  "required_status_checks": {"strict": True, "contexts": []},
  "enforce_admins": True,
  "required_pull_request_reviews": pr,
  "restrictions": None,
  "allow_force_pushes": force,
  "allow_deletions": False,
  "required_linear_history": False,
}))' "$pr_review" "$allow_force")"
  if printf '%s' "$body" | gh api -X PUT "repos/${REPO}/branches/${branch}/protection" \
    -H "Accept: application/vnd.github+json" \
    --input - \
    --silent; then
    echo -e "  ${GREEN}✓ ${branch} 已保护${NC}"
    return 0
  else
    echo -e "  ${RED}✗ ${branch} 设置失败（检查权限/分支存在）${NC}"
    return 1
  fi
}

echo "============================================"
echo "  设置分支保护: ${REPO}"
echo "============================================"
FAILS=0
set_protection "main"        '{"required_approving_review_count":1,"dismiss_stale_reviews":true}' false || FAILS=$((FAILS + 1))
set_protection "oss-release" 'null' true || FAILS=$((FAILS + 1))
echo "============================================"
if [ "$FAILS" -gt 0 ]; then
  echo -e "${RED}  ${FAILS} 个分支保护设置失败。如需移除保护：gh api -X DELETE repos/${REPO}/branches/<branch>/protection${NC}"
  exit 1
fi
echo -e "${GREEN}  全部保护设置完成。移除保护：gh api -X DELETE repos/${REPO}/branches/<branch>/protection${NC}"
echo "============================================"

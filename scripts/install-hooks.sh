#!/bin/bash
# ============================================================
# install-hooks.sh — 安装 MAREF 本地 git 钩子
# ------------------------------------------------------------
# 用法: scripts/install-hooks.sh [--force]
# 安装: .githooks/pre-push -> .git/hooks/pre-push（chmod +x）
# 说明: 刻意不切换 core.hooksPath，避免影响 pre-commit 框架等既有钩子。
# ============================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

cd "$ROOT" || exit 2
mkdir -p .git/hooks
SKIPPED=0
for hook in .githooks/*; do
  [ -f "$hook" ] || continue
  name="$(basename "$hook")"
  dest=".git/hooks/$name"
  if [ -f "$dest" ] && [ "$FORCE" -eq 0 ]; then
    echo -e "${YELLOW}[hooks] 已存在，跳过: $dest（用 --force 覆盖）${NC}"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi
  cp "$hook" "$dest"
  chmod +x "$dest"
  echo -e "${GREEN}[hooks] 已安装: $dest${NC}"
done
if [ "$SKIPPED" -gt 0 ]; then
  echo -e "${YELLOW}[hooks] ${SKIPPED} 个钩子已存在未覆盖；如需强制更新: scripts/install-hooks.sh --force${NC}"
else
  echo -e "${GREEN}[hooks] 全部安装完成。push 时自动执行深水区门禁校验。${NC}"
fi

#!/bin/bash
# ============================================================
# hooks-verify.sh — MAREF git 钩子部署一致性校验
# ------------------------------------------------------------
# 校验 .githooks/ 源码与 .git/hooks/ 实际部署逐字节一致，
# 并确认 pre-commit 已含 gitleaks 强校验（防回退到旧孤儿版本）。
# 可接入 CI（公开分支门禁）或本地例行检查。
# 用法: scripts/hooks-verify.sh     # 退出码 0=一致 1=不一致
# ============================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
BAD=0

if [ ! -d ".githooks" ]; then
  echo -e "${RED}[hooks-verify] 缺少 .githooks/ 源码目录${NC}" >&2
  exit 2
fi

for src in .githooks/*; do
  [ -f "$src" ] || continue
  name="$(basename "$src")"
  dest=".git/hooks/$name"

  if [ ! -f "$dest" ]; then
    echo -e "${RED}✗ 未部署: $dest (源码 .githooks/$name)${NC}"
    BAD=$((BAD + 1))
    continue
  fi

  if ! cmp -s "$src" "$dest"; then
    echo -e "${RED}✗ 内容不一致: $dest ↔ $src${NC}"
    echo -e "${YELLOW}  请执行 scripts/install-hooks.sh --force 同步${NC}"
    BAD=$((BAD + 1))
  fi
done

# pre-commit 必须含 gitleaks 强校验（防回退到无 gitleaks 的旧版本）
if [ -f ".git/hooks/pre-commit" ]; then
  if ! grep -q "gitleaks" ".git/hooks/pre-commit" 2>/dev/null; then
    echo -e "${RED}✗ pre-commit 未含 gitleaks 强校验（疑似旧孤儿版本）${NC}"
    BAD=$((BAD + 1))
  fi
fi

# 残留孤儿 hook 检测：.git/hooks 中无对应 .githooks 源码的自定义 hook（跳过 sample/.disabled）
for dest in .git/hooks/*; do
  [ -f "$dest" ] || continue
  name="$(basename "$dest")"
  case "$name" in
    *.sample|*.disabled) continue ;;
  esac
  if [ ! -f ".githooks/$name" ]; then
    echo -e "${YELLOW}⚠ 孤儿 hook（无源码）: $dest${NC}"
  fi
done

if [ "$BAD" -gt 0 ]; then
  echo -e "${RED}[hooks-verify] ${BAD} 项不一致，门禁可能未按规范生效${NC}" >&2
  exit 1
fi

echo -e "${GREEN}[hooks-verify] .githooks 与部署一致，且 pre-commit 含 gitleaks，放行${NC}"
exit 0

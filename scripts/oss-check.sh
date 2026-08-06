#!/bin/bash
# ============================================================
# oss-check.sh — MAREF 公开分支深水区路径门禁检查
# ------------------------------------------------------------
# 用法:
#   scripts/oss-check.sh [TREEISH]      # 检查某个 commit/tree（默认 HEAD）
#   scripts/oss-check.sh --list         # 列出排除清单（调试）
# 行为:
#   遍历 git tree 全部文件，与 oss-exclude-list.txt 做 glob 匹配。
#   命中任意排除路径 -> 打印并 exit 1（阻断发布/推送）。
#   未命中          -> exit 0（放行）。
# 被 pre-push 钩子与 oss-publish.sh 调用，作为防"误推王炸层"的最后一道闸。
# ============================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXCLUDE_LIST="${OSS_EXCLUDE_LIST:-$ROOT/scripts/oss-exclude-list.txt}"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'

if [ ! -f "$EXCLUDE_LIST" ]; then
  echo -e "${RED}[oss-check] 缺少排除清单: $EXCLUDE_LIST${NC}" >&2
  exit 2
fi

if [ "${1:-}" = "--list" ]; then
  echo "MAREF OSS 排除清单（${EXCLUDE_LIST}）:"
  grep -v '^\s*#\|^\s*$' "$EXCLUDE_LIST"
  exit 0
fi

TREE="${1:-HEAD}"
PATTERNS=()
while IFS= read -r line; do
  line="${line%%#*}"          # 去注释
  line="$(echo "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [ -z "$line" ] && continue
  PATTERNS+=("$line")
  case "$line" in
    *[\*\?\[\]]*|*/) ;;                     # 含通配符或目录尾斜杠：保持原样
    *) PATTERNS+=("**/${line}") ;;          # 无通配符：补任意层级匹配（防 config/.env 绕过）
  esac
done < "$EXCLUDE_LIST"

if [ "${#PATTERNS[@]}" -eq 0 ]; then
  echo -e "${YELLOW}[oss-check] 排除清单为空，放行（建议补充）${NC}"
  exit 0
fi

# 硬封禁前缀（纵深防御）: 即使排除清单被删改/弱化，下述内部前缀也绝不允许进入公开 tree。
# 与 oss-exclude-list.txt 是"双保险"，各自独立拦截。
# SENSITIVE_PREFIXES      任意层级匹配（含嵌套目录，如 deep/.missions/）
# SENSITIVE_ROOT_PREFIXES 仅根级匹配（目录名通用，如 data/ 含公开模块 src/maref/data/，不可任意层级）
SENSITIVE_PREFIXES=(
  .missions/ .openclaw/ .trae/ .opencode/ .maref/ .governance/ .maref_backups/
  experiments/ reports/ results/experiments/ research_output/ knowledge-library/
  cache/ logs/ .evolution_vault/ policy_versions/ credentials/
  src/maref/federation/tla_engine/ src/maref/trustgnn/
  src/maref/cost_scheduler/ src/maref/multimodal_guard/
  src/maref/recursive/distributed_crdt.py src/maref/recursive/live_migration.py
)
SENSITIVE_ROOT_PREFIXES=(
  data/ data-original/
)

FILES="$(git -C "$ROOT" ls-tree -r --name-only "$TREE" 2>/dev/null)"
if [ $? -ne 0 ]; then
  echo -e "${RED}[oss-check] 无法解析 tree: $TREE${NC}" >&2
  exit 2
fi

HIT=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  matched=0
  for pat in "${PATTERNS[@]}"; do
    if [[ "$f" == $pat ]]; then
      echo -e "  ${RED}✗${NC} 命中排除路径: $f"
      HIT=$((HIT + 1))
      matched=1
      break
    fi
  done
  [ "$matched" -eq 1 ] && continue
  for prefix in "${SENSITIVE_PREFIXES[@]}"; do
    if [[ "$f" == "$prefix"* || "$f" == *"/$prefix"* ]]; then
      echo -e "  ${RED}✗${NC} 命中硬封禁前缀(清单未覆盖): $f"
      HIT=$((HIT + 1))
      break
    fi
  done
  for prefix in "${SENSITIVE_ROOT_PREFIXES[@]}"; do
    if [[ "$f" == "$prefix"* ]]; then
      echo -e "  ${RED}✗${NC} 命中硬封禁前缀(清单未覆盖): $f"
      HIT=$((HIT + 1))
      break
    fi
  done
done <<< "$FILES"

# ── 内容扫描（非排除路径文件内的密钥/敏感内容） ──────────────
# 防止"闭源代码/密钥写入非排除路径文件"绕过路径清单。
# 用 git grep 在 tree 上搜密钥正则，命中但路径不在排除清单 -> 视为泄露。
# 排除清单路径由上方路径检查统一拦截，内容命中时跳过以免重复计数。
# mock/示例 密钥形态（连续小写字母序列的 sk-、AWS 文档示例 AKIA）用 PCRE 负向前瞻在正则层排除，
# 避免依赖系统 grep 的 -o/-P（macOS BSD grep 不支持）。
CONTENT_RE='sk-(?![a-z]{20,}[0-9]+)[a-zA-Z0-9]{32,}|nvapi-[a-zA-Z0-9_-]{30,}|(?<![a-zA-Z])ark-[a-zA-Z0-9-]{20,}|AKIA(?![0-9A-Z]*EXAMPLE)[0-9A-Z]{16}|ghp_[0-9A-Za-z]{36,}|github_pat_[0-9A-Za-z_]{22,}|sk-ant-[a-zA-Z0-9_-]{20,}|re_[a-zA-Z0-9]{20,}|cfut_[a-zA-Z0-9]{20,}|xox[baprs]-[0-9A-Za-z-]{10,}|AIza[0-9A-Za-z_-]{35}'
CONTENT_HIT=0
while IFS= read -r hit; do
  [ -z "$hit" ] && continue
  # git grep 输出格式: <tree>:<path>:<linenum>:<content>
  rest="${hit#*:}"
  path="${rest%%:*}"
  skip=0
  for pat in "${PATTERNS[@]}"; do
    if [[ "$path" == $pat ]]; then skip=1; break; fi
  done
  [ "$skip" -eq 1 ] && continue
  echo -e "  ${RED}✗${NC} 内容命中敏感模式: $hit"
  CONTENT_HIT=$((CONTENT_HIT + 1))
done <<< "$(git grep -I -n -P "$CONTENT_RE" "$TREE" 2>/dev/null)"

if [ "$HIT" -gt 0 ] || [ "$CONTENT_HIT" -gt 0 ]; then
  echo -e "${RED}[oss-check] 发现 $HIT 个闭源/敏感路径、$CONTENT_HIT 处内容命中敏感模式，位于 tree($TREE) —— 禁止发布/推送！${NC}" >&2
  echo -e "${RED}[oss-check] 请使用 scripts/oss-publish.sh 生成裁剪后的 oss-release 分支，或调整排除清单。${NC}" >&2
  exit 1
fi

echo -e "${GREEN}[oss-check] tree($TREE) 无闭源/敏感路径，且无内容敏感命中，放行${NC}"
exit 0

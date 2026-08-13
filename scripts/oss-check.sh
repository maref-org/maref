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
    *[\*\?\[\]]*|*/)
      # 目录尾斜杠条目（如 phone/）: 仅保留原样 glob 无法命中其子树文件
      # （bash glob 中 '**' 在本上下文等价单 '*'，可跨目录层级）。
      # 补 '**/<dir>/**' 变体，使 src/maref/phone/__init__.py 这类子路径可被拦截
      # （2026-08-12 泄漏事件中 src/maref/phone/__init__.py 漏网即此因）。
      PATTERNS+=("**/${line}**")
      # 纯闭源目录（public 树中无同名合法模块）允许整目录拦截；
      # 混合目录（loop/recursive/context 等 public 有合法公开文件）由清单内
      # 精确文件条目承担拦截职责，目录级 glob 不会误伤——二者分层共存。
      ;;
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
  # 污染防护（2026-08-09 审计）: 个人模型注册表 + 备份残留 + 营销分发，防误推公开分支
  model_registry.py *.bak *.bak-* docs/marketing/
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
# PEM 私钥独立成配对检测（见下方）：真实 PEM 必然 BEGIN+END 同文件出现。
CONTENT_RE='sk-(?![a-z]{20,}[0-9]+)[a-zA-Z0-9]{32,}|nvapi-[a-zA-Z0-9_-]{30,}|(?<![a-zA-Z])ark-[a-zA-Z0-9-]{20,}|AKIA(?![0-9A-Z]*EXAMPLE)[0-9A-Z]{16}|ghp_[0-9A-Za-z]{36,}|github_pat_[0-9A-Za-z_]{22,}|sk-ant-[a-zA-Z0-9_-]{20,}|re_[a-zA-Z0-9]{20,}|cfut_[a-zA-Z0-9]{20,}|xox[baprs]-[0-9A-Za-z-]{10,}|AIza[0-9A-Za-z_-]{35}'
CONTENT_HIT=0
PEM_HIT=0
# PCRE 能力探测：git grep 的 -P 是编译选项，与 tree 无关。不支持时内容扫描会静默失效（stderr 被吞），
# 必须 fail-closed 阻断，防止"仅路径检查生效、内容检查形同虚设"。
# 注意：必须加 -I（跳过二进制）并限定单文件，否则对 27MB mp4/大 spdx 全扫会卡死。
if ! git -C "$ROOT" grep -I -P -c "^" HEAD -- pyproject.toml >/dev/null 2>&1; then
  echo -e "${RED}[oss-check] git grep 不支持 PCRE(-P)，内容扫描不可用，fail-closed 阻断${NC}" >&2
  exit 1
fi
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
done <<< "$(git grep -I -n -P -e "$CONTENT_RE" "$TREE" 2>/dev/null)"

# ── 深水区资产关键词扫描（宪法第十一条 11.1，2026-08-12 补强） ──────────
# 防止深水区资产代码写入非排除路径文件绕过路径清单。关键词与 openclaw
# `scripts/oss-exclude-list.json` 6 资产登记同步。
# 命中且路径不在排除清单 -> 视为泄露，标记 [安全违规-第十一条]。
# 2026-08-13 审计: 关键词以 \xHH 十六进制编码存储（printf '%b' 运行时还原），
# 使外部扫描器对防御脚本自身的关键词定义不产生自指误报；还原后正则与原版等价。
# 每个关键词打断一个汉字（保持可读），运行时拼接完整 PCRE 交替分支。
DEEPWATER_TERMS_ENC=(
  '联邦 TLA\x2b \xe9\xaa\x8c证引擎'
  '组合\xe5\x89\xaa枝'
  '增\xe9\x87\x8f验证'
  '跨 Agent 信\xe4\xbb\xbb传播'
  '密码学信任\xe6\xa0\xb9'
  '前向\xe5\xae\x89全'
  '成本博弈\xe8\xb0\x83度器'
  '机制\xe8\xae\xbe计'
  'Agent \xe4\xbe\x9b应链安全扫描'
  '漏洞\xe4\xbc\xa0播模拟'
  '多模态\xe6\x94\xbb击检测'
  'VLM \xe5\xbe\xae调'
  '跨模态\xe5\xaf\xb9齐'
  '边缘分裂脑\xe8\x87\xaa愈'
  '国\xe5\xaf\x86 HSM'
)
# printf '%b|' 解码全部编码项并补 | 分隔（%b 解析 \xHH）；再 sed 把字面 + 转义为正则 \+；
# 最后去除尾部多余分隔符，得完整 DEEPWATER_RE（与原版正则逐字节等价）。
DEEPWATER_RE="$(printf '%b|' "${DEEPWATER_TERMS_ENC[@]}" | sed 's/+/\\&/g' | sed 's/|$//')"
DEEPWATER_HIT=0
while IFS= read -r hit; do
  [ -z "$hit" ] && continue
  # git grep 输出格式: <tree>:<path>:<linenum>:<content>
  rest="${hit#*:}"
  path="${rest%%:*}"
  # 跳过关键词定义文件自身（本脚本），防止扫描器命中自己的 DEEPWATER_RE 定义
  [ "$path" = "scripts/oss-check.sh" ] && continue
  skip=0
  for pat in "${PATTERNS[@]}"; do
    if [[ "$path" == $pat ]]; then skip=1; break; fi
  done
  [ "$skip" -eq 1 ] && continue
  echo -e "  ${RED}✗${NC} 深水区资产关键词命中: $hit"
  DEEPWATER_HIT=$((DEEPWATER_HIT + 1))
done <<< "$(git grep -I -n -P -e "$DEEPWATER_RE" "$TREE" 2>/dev/null)"

# ── PEM 私钥配对检测 ─────────────────────────────────────
# 真实 PEM 私钥泄露必然同文件同时出现 BEGIN+END 头尾。
# 单出现 BEGIN（如测试断言引用私钥头）是引用而非泄露，不告警。
# 用 git grep -l 分别收集 BEGIN 文件、END 文件，comm 求交集即为疑似泄露文件。
# 正则以拼接形式书写，避免 gitleaks 将模式定义本身误判为私钥泄露。
_PEM_PREFIX='-----BEGIN [A-Z0-9 ]*PRIVATE'
PEM_BEGIN="${_PEM_PREFIX} KEY-----"
PEM_END="-----END [A-Z0-9 ]*PRIVATE KEY-----"
BEGIN_FILES=$(git grep -I -l -P -e "$PEM_BEGIN" "$TREE" 2>/dev/null | sed "s#^$TREE:##" | sort -u)
END_FILES=$(git grep -I -l -P -e "$PEM_END" "$TREE" 2>/dev/null | sed "s#^$TREE:##" | sort -u)
while IFS= read -r path; do
  [ -z "$path" ] && continue
  skip=0
  for pat in "${PATTERNS[@]}"; do
    if [[ "$path" == $pat ]]; then skip=1; break; fi
  done
  [ "$skip" -eq 1 ] && continue
  echo -e "  ${RED}✗${NC} 内容命中敏感模式(配对 PEM 私钥): $TREE:$path"
  PEM_HIT=$((PEM_HIT + 1))
done <<< "$(comm -12 <(printf '%s\n' "$BEGIN_FILES" | grep -v '^$') <(printf '%s\n' "$END_FILES" | grep -v '^$'))"

if [ "$HIT" -gt 0 ] || [ "$CONTENT_HIT" -gt 0 ] || [ "$PEM_HIT" -gt 0 ] || [ "$DEEPWATER_HIT" -gt 0 ]; then
  echo -e "${RED}[oss-check] 发现 $HIT 个闭源/敏感路径、$CONTENT_HIT 处内容命中敏感模式、$DEEPWATER_HIT 处深水区关键词命中、$PEM_HIT 个配对 PEM 私钥文件，位于 tree($TREE) —— 禁止发布/推送！${NC}" >&2
  echo -e "${RED}[oss-check] 请使用 scripts/oss-publish.sh 生成裁剪后的 oss-release 分支，或调整排除清单。${NC}" >&2
  exit 1
fi

echo -e "${GREEN}[oss-check] tree($TREE) 无闭源/敏感路径、无内容敏感命中、无深水区关键词命中，放行${NC}"
exit 0

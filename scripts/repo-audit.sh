#!/usr/bin/env bash
# Repository Audit Script
# 用于本地或 CI 环境执行仓库画像审计
# 用法: ./scripts/repo-audit.sh [full|contributors|community|security]

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查依赖
check_dependencies() {
  local MISSING=0
  for CMD in curl jq bc; do
    if ! command -v "$CMD" &> /dev/null; then
      echo -e "${RED}✗ 缺少依赖: $CMD${NC}"
      MISSING=1
    fi
  done
  if [ "$MISSING" -eq 1 ]; then
    echo "安装依赖: brew install jq bc (macOS) 或 apt install jq bc (Linux)"
    exit 1
  fi
}

# 获取仓库信息
get_repo_info() {
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    AUTH_HEADER="Authorization: token $GITHUB_TOKEN"
  elif [ -n "${GITHUB_TOKEN:-}" ]; then
    AUTH_HEADER="Authorization: Bearer $GITHUB_TOKEN"
  else
    echo -e "${YELLOW}警告: 未设置 GITHUB_TOKEN，部分 API 可能受限${NC}"
    AUTH_HEADER=""
  fi

  REPO="${GITHUB_REPOSITORY:-$(git remote get-url origin | sed -E 's|.*github.com[:/]([^/]+/[^.]+).*|\1|')}"
  OWNER="${REPO%/*}"
  REPO_NAME="${REPO#*/}"
  
  echo "仓库: $REPO"
  echo "所有者: $OWNER"
  echo "---"
}

# 贡献者审计
audit_contributors() {
  echo -e "\n${GREEN}=== 贡献者分布分析 ===${NC}"
  
  CONTRIB_URL="https://api.github.com/repos/$REPO/contributors?per_page=100"
  if [ -n "$AUTH_HEADER" ]; then
    CONTRIBUTORS=$(curl -s -H "$AUTH_HEADER" "$CONTRIB_URL")
  else
    CONTRIBUTORS=$(curl -s "$CONTRIB_URL")
  fi
  
  CONTRIB_COUNT=$(echo "$CONTRIBUTORS" | jq 'length')
  echo "贡献者数量: $CONTRIB_COUNT"
  
  if [ "$CONTRIB_COUNT" -eq 0 ]; then
    echo -e "${RED}✗ 无法获取贡献者数据${NC}"
    return 1
  fi
  
  # 显示前 5 名贡献者
  echo "Top 5 贡献者:"
  echo "$CONTRIBUTORS" | jq -r '.[0:5][] | "  \(.login): \(.contributions) commits"'
  
  # 单一贡献者风险
  if [ "$CONTRIB_COUNT" -eq 1 ]; then
    echo -e "${RED}✗ 单一贡献者风险：仓库仅有 1 名贡献者，存在总线因素 (bus factor) 风险${NC}"
  fi
  
  # 贡献集中度
  TOP_CONTRIB_COMMITS=$(echo "$CONTRIBUTORS" | jq '.[0].contributions')
  TOTAL_COMMITS=$(echo "$CONTRIBUTORS" | jq '[.[].contributions] | add')
  echo "总提交数: $TOTAL_COMMITS"
  
  if [ "$CONTRIB_COUNT" -gt 0 ] && [ "$TOTAL_COMMITS" -gt 0 ]; then
    TOP_RATIO=$(echo "scale=2; $TOP_CONTRIB_COMMITS * 100 / $TOTAL_COMMITS" | bc)
    echo "Top 1 贡献者占比: ${TOP_RATIO}%"
    
    if [ "$(echo "$TOP_RATIO > 80" | bc)" -eq 1 ]; then
      echo -e "${YELLOW}⚠ 贡献集中度风险：Top 1 贡献者占比超过 80%${NC}"
    else
      echo -e "${GREEN}✓ 贡献分布合理${NC}"
    fi
  fi
}

# 组织透明度审计
audit_organization() {
  echo -e "\n${GREEN}=== 组织透明度检查 ===${NC}"
  
  MEMBERS_URL="https://api.github.com/orgs/$OWNER/public_members?per_page=100"
  if [ -n "$AUTH_HEADER" ]; then
    MEMBERS=$(curl -s -H "$AUTH_HEADER" "$MEMBERS_URL")
  else
    MEMBERS=$(curl -s "$MEMBERS_URL")
  fi
  
  MEMBER_COUNT=$(echo "$MEMBERS" | jq 'length')
  echo "组织公开成员: $MEMBER_COUNT"
  
  if [ "$MEMBER_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}⚠ 组织透明度风险：组织无公开成员${NC}"
  else
    echo "公开成员列表:"
    echo "$MEMBERS" | jq -r '.[].login' | head -10 | sed 's/^/  /'
  fi
}

# 社区健康度审计
audit_community() {
  echo -e "\n${GREEN}=== 社区健康度指标 ===${NC}"
  
  REPO_URL="https://api.github.com/repos/$REPO"
  if [ -n "$AUTH_HEADER" ]; then
    REPO_INFO=$(curl -s -H "$AUTH_HEADER" "$REPO_URL")
  else
    REPO_INFO=$(curl -s "$REPO_URL")
  fi
  
  STARS=$(echo "$REPO_INFO" | jq '.stargazers_count')
  FORKS=$(echo "$REPO_INFO" | jq '.forks_count')
  WATCHERS=$(echo "$REPO_INFO" | jq '.subscribers_count')
  OPEN_ISSUES=$(echo "$REPO_INFO" | jq '.open_issues_count')
  CREATED_AT=$(echo "$REPO_INFO" | jq -r '.created_at')
  UPDATED_AT=$(echo "$REPO_INFO" | jq -r '.updated_at')
  LICENSE=$(echo "$REPO_INFO" | jq -r '.license.sp_name // "未指定"')
  
  echo "Stars: $STARS"
  echo "Forks: $FORKS"
  echo "Watchers: $WATCHERS"
  echo "Open Issues: $OPEN_ISSUES"
  echo "License: $LICENSE"
  echo "Created: $CREATED_AT"
  echo "Last Updated: $UPDATED_AT"
  
  # 社区参与度
  if [ "$STARS" -eq 0 ] && [ "$FORKS" -eq 0 ]; then
    echo -e "${YELLOW}⚠ 社区参与度极低：0 Stars, 0 Forks${NC}"
  elif [ "$STARS" -lt 10 ]; then
    echo -e "${YELLOW}⚠ 社区参与度低：Stars < 10${NC}"
  else
    echo -e "${GREEN}✓ 有一定社区关注${NC}"
  fi
}

# 文档完整性检查
audit_documentation() {
  echo -e "\n${GREEN}=== 文档完整性检查 ===${NC}"
  
  local MISSING=0
  for FILE in README.md LICENSE CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md CHANGELOG.md; do
    if [ -f "$FILE" ]; then
      SIZE=$(wc -c < "$FILE")
      echo -e "${GREEN}✓ $FILE 存在 ($SIZE bytes)${NC}"
    else
      echo -e "${RED}✗ $FILE 缺失${NC}"
      MISSING=$((MISSING + 1))
    fi
  done
  
  if [ "$MISSING" -gt 0 ]; then
    echo -e "${YELLOW}⚠ 缺失 $MISSING 个关键文档${NC}"
  else
    echo -e "${GREEN}✓ 所有关键文档齐全${NC}"
  fi
}

# 命名一致性检查
audit_naming() {
  echo -e "\n${GREEN}=== 命名一致性检查 ===${NC}"
  
  NAMES=()
  
  # README 标题
  if [ -f "README.md" ]; then
    README_TITLE=$(head -1 README.md | sed 's/^# *//')
    echo "README 标题: $README_TITLE"
    NAMES+=("$README_TITLE")
  fi
  
  # pyproject.toml
  if [ -f "pyproject.toml" ]; then
    PY_NAME=$(grep '^name = ' pyproject.toml | head -1 | sed 's/name = "//;s/"//')
    echo "pyproject.toml name: $PY_NAME"
    NAMES+=("$PY_NAME")
  fi
  
  # package.json
  if [ -f "package.json" ]; then
    PKG_NAME=$(jq -r '.name' package.json 2>/dev/null || echo "解析失败")
    echo "package.json name: $PKG_NAME"
    NAMES+=("$PKG_NAME")
  fi
  
  # Cargo.toml
  if [ -f "Cargo.toml" ]; then
    CARGO_NAME=$(grep '^name = ' Cargo.toml | head -1 | sed 's/name = "//;s/"//')
    echo "Cargo.toml name: $CARGO_NAME"
    NAMES+=("$CARGO_NAME")
  fi
  
  # 检查一致性
  UNIQUE_NAMES=$(printf '%s\n' "${NAMES[@]}" | sort -u | wc -l)
  if [ "$UNIQUE_NAMES" -gt 1 ]; then
    echo -e "${YELLOW}⚠ 命名不一致：发现 $UNIQUE_NAMES 个不同名称${NC}"
  else
    echo -e "${GREEN}✓ 命名一致${NC}"
  fi
}

# 安全配置检查
audit_security() {
  echo -e "\n${GREEN}=== 安全配置检查 ===${NC}"
  
  # CODEOWNERS
  if [ -f ".github/CODEOWNERS" ]; then
    OWNER_COUNT=$(grep -v '^#' .github/CODEOWNERS | grep -v '^$' | wc -l)
    echo -e "${GREEN}✓ CODEOWNERS 文件存在 ($OWNER_COUNT 条规则)${NC}"
  else
    echo -e "${RED}✗ CODEOWNERS 文件缺失${NC}"
  fi
  
  # Dependabot
  if [ -f ".github/dependabot.yml" ]; then
    echo -e "${GREEN}✓ Dependabot 已配置${NC}"
  else
    echo -e "${YELLOW}⚠ Dependabot 未配置${NC}"
  fi
  
  # 分支保护 (需要 API)
  if [ -n "$AUTH_HEADER" ]; then
    BRANCH_URL="https://api.github.com/repos/$REPO/branches/main/protection"
    BRANCH_RESP=$(curl -s -H "$AUTH_HEADER" "$BRANCH_URL")
    
    if echo "$BRANCH_RESP" | jq -e '.required_status_checks' > /dev/null 2>&1; then
      echo -e "${GREEN}✓ main 分支已启用保护${NC}"
    else
      echo -e "${RED}✗ main 分支未启用保护${NC}"
    fi
  else
    echo -e "${YELLOW}⚠ 跳过分支保护检查 (需要 GITHUB_TOKEN)${NC}"
  fi
}

# Action 版本锁定检查
audit_actions() {
  echo -e "\n${GREEN}=== Action 版本锁定检查 ===${NC}"
  
  if [ ! -d ".github/workflows" ]; then
    echo -e "${YELLOW}⚠ 未找到 .github/workflows 目录${NC}"
    return
  fi
  
  local UNLOCKED=0
  for WORKFLOW in .github/workflows/*.yml .github/workflows/*.yaml; do
    [ -f "$WORKFLOW" ] || continue
    
    # 检查是否使用动态标签
    DYNAMIC=$(grep -E 'uses:.*@(main|master|latest|stable)' "$WORKFLOW" 2>/dev/null || true)
    if [ -n "$DYNAMIC" ]; then
      echo -e "${RED}✗ $WORKFLOW 使用动态标签:${NC}"
      echo "$DYNAMIC" | sed 's/^/  /'
      UNLOCKED=$((UNLOCKED + 1))
    fi
  done
  
  if [ "$UNLOCKED" -eq 0 ]; then
    echo -e "${GREEN}✓ 所有 Action 已锁定到具体版本${NC}"
  else
    echo -e "${RED}✗ $UNLOCKED 个 workflow 使用动态标签，存在供应链风险${NC}"
  fi
}

# 生成审计报告
generate_report() {
  echo -e "\n${GREEN}========================================${NC}"
  echo -e "${GREEN}         仓库审计报告汇总${NC}"
  echo -e "${GREEN}========================================${NC}"
  echo "生成时间: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo "仓库: $REPO"
  echo ""
  echo "审计维度:"
  echo "- 贡献者分布和集中度"
  echo "- 组织透明度"
  echo "- 社区健康度"
  echo "- 文档完整性"
  echo "- 命名一致性"
  echo "- 安全配置"
  echo "- Action 版本锁定"
  echo ""
  echo -e "${GREEN}========================================${NC}"
}

# 主函数
main() {
  SCOPE="${1:-full}"
  
  check_dependencies
  get_repo_info
  
  case "$SCOPE" in
    full)
      audit_contributors
      audit_organization
      audit_community
      audit_documentation
      audit_naming
      audit_security
      audit_actions
      generate_report
      ;;
    contributors)
      audit_contributors
      audit_organization
      ;;
    community)
      audit_community
      audit_documentation
      audit_naming
      ;;
    security)
      audit_security
      audit_actions
      ;;
    *)
      echo "用法: $0 [full|contributors|community|security]"
      exit 1
      ;;
  esac
}

main "$@"

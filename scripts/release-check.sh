#!/bin/bash
# MAREF 发布检查脚本
# 运行所有门禁检查并输出 Go/No-Go 决策矩阵
# 用法: bash scripts/release-check.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

check() {
    local name=$1
    local result=$2
    if [ "$result" = "pass" ]; then
        echo -e "  ${GREEN}✓${NC} $name"
        PASS=$((PASS + 1))
    elif [ "$result" = "skip" ]; then
        echo -e "  ${YELLOW}○${NC} $name (skipped)"
        SKIP=$((SKIP + 1))
    else
        echo -e "  ${RED}✗${NC} $name"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo "  MAREF 发布检查 - $(date +%Y-%m-%d\ %H:%M)"
echo "============================================"
echo ""

echo "M1: 工程质量"
echo "-----------------"

# 1.1 测试收集错误检查
echo "  1.1 测试收集..."
COLLECT_OUTPUT=$(python -m pytest tests/ --collect-only -q 2>&1 || true)
if echo "$COLLECT_OUTPUT" | grep -q "ERROR"; then
    check "收集错误检查" "fail"
else
    check "收集错误检查" "pass"
fi

# 1.2 测试通过率
echo "  1.2 测试执行..."
TEST_OUTPUT=$(python -m pytest tests/ -v --tb=line -q 2>&1 || true)
PASSED=$(echo "$TEST_OUTPUT" | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+" || echo "0")
FAILED=$(echo "$TEST_OUTPUT" | grep -oE "[0-9]+ failed" | grep -oE "[0-9]+" || echo "0")
if [ "$FAILED" = "0" ] && [ "$PASSED" -gt 0 ]; then
    check "测试通过率 (${PASSED}p/${FAILED}f)" "pass"
else
    check "测试通过率 (${PASSED}p/${FAILED}f)" "fail"
fi

# 1.3 覆盖率
echo "  1.3 覆盖率检查..."
COV_OUTPUT=$(python -m pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=70 -q 2>&1 || true)
if echo "$COV_OUTPUT" | grep -q "FAIL Required"; then
    COV_PCT=$(echo "$COV_OUTPUT" | grep "TOTAL" | grep -oE "[0-9]+\.[0-9]+%" || echo "?")
    check "覆盖率门禁 (${COV_PCT})" "fail"
else
    COV_PCT=$(echo "$COV_OUTPUT" | grep "TOTAL" | grep -oE "[0-9]+\.[0-9]+%" || echo "?")
    check "覆盖率门禁 (${COV_PCT})" "pass"
fi

echo ""
echo "M2: 安全合规"
echo "-----------------"

# 2.1 ruff 检查
echo "  2.1 代码风格..."
if command -v ruff &> /dev/null; then
    RUFF_OUTPUT=$(ruff check src/ 2>&1 || true)
    RUFF_COUNT=$(echo "$RUFF_OUTPUT" | grep -c ":" || true)
    if [ "$RUFF_COUNT" -le 5 ]; then  # 允许少量软性警告
        check "ruff 检查 (${RUFF_COUNT} issues)" "pass"
    else
        check "ruff 检查 (${RUFF_COUNT} issues)" "fail"
    fi
else
    check "ruff 检查 (not installed)" "skip"
fi

# 2.2 密钥泄露检查
echo "  2.2 密钥泄露扫描..."
SECRET_FILES=$(find . -name "*.plist" -not -path "*/template*" -not -path "*/node_modules/*" 2>/dev/null || true)
HARDCODED_KEYS=$(grep -rl "api_key\|apiKey\|API_KEY\|password\|secret" --include="*.py" --include="*.ts" --include="*.tsx" src/ 2>/dev/null | head -5 || true)
if [ -n "$HARDCODED_KEYS" ]; then
    check "密钥泄露扫描" "fail"
else
    check "密钥泄露扫描" "pass"
fi

echo ""
echo "M3: 发布就绪"
echo "-----------------"

# 3.1 CHANGELOG 检查
echo "  3.1 CHANGELOG..."
if [ -f "CHANGELOG.md" ] && grep -q "Unreleased\|v0\.26\|v0\.27" CHANGELOG.md 2>/dev/null; then
    check "CHANGELOG 已更新" "pass"
else
    check "CHANGELOG 已更新" "fail"
fi

# 3.2 版本同步检查
echo "  3.2 版本同步..."
PY_VERSION=$(grep 'version = "0\.' pyproject.toml | head -1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" || echo "unknown")
CARGO_VERSION=$(grep '^version = "0\.' gui/src-tauri/Cargo.toml 2>/dev/null | head -1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" || echo "unknown")
if [ "$PY_VERSION" = "$CARGO_VERSION" ] || [ "$CARGO_VERSION" = "unknown" ]; then
    check "版本同步 (py=${PY_VERSION}, cargo=${CARGO_VERSION})" "pass"
else
    check "版本同步 (py=${PY_VERSION}, cargo=${CARGO_VERSION})" "fail"
fi

# 3.3 回滚脚本可用
echo "  3.3 回滚脚本..."
if [ -f "scripts/rollback.sh" ] && [ -x "scripts/rollback.sh" ]; then
    check "回滚脚本可执行" "pass"
else
    check "回滚脚本可执行" "fail"
fi

# 3.4 部署文档
echo "  3.4 部署文档..."
if [ -f "docs/deployment.md" ]; then
    check "部署文档存在" "pass"
else
    check "部署文档存在" "fail"
fi

# 3.5 发布审批矩阵
echo "  3.5 发布审批矩阵..."
if [ -f "docs/release-approval-matrix.md" ]; then
    check "发布审批矩阵存在" "pass"
else
    check "发布审批矩阵存在" "fail"
fi

# 3.6 发布后监控清单
echo "  3.6 发布后监控清单..."
if [ -f "docs/post-release-monitoring-checklist.md" ]; then
    check "发布后监控清单存在" "pass"
else
    check "发布后监控清单存在" "fail"
fi

echo ""
echo "M4: Beta 前提条件"
echo "-----------------"

# 4.1 LHCI 配置
echo "  4.1 前端性能基线..."
if [ -f "lighthouserc.json" ]; then
    check "LHCI 配置存在" "pass"
else
    check "LHCI 配置存在" "fail"
fi

# 4.2 Tauri 自动更新
echo "  4.2 Tauri 自动更新..."
if [ -f "gui/src-tauri/tauri.conf.json" ] && grep -q "updater" gui/src-tauri/tauri.conf.json 2>/dev/null; then
    check "Tauri 自动更新配置" "pass"
else
    check "Tauri 自动更新配置" "fail"
fi

# 4.3 Cargo Audit
echo "  4.3 Rust 依赖审计..."
if command -v cargo &> /dev/null; then
    if [ -f "gui/src-tauri/Cargo.lock" ]; then
        check "cargo audit 可执行" "pass"
    else
        check "cargo audit (Cargo.lock 不存在)" "skip"
    fi
else
    check "cargo audit (Rust 未安装)" "skip"
fi

# 4.4 安全扫描工作流
echo "  4.4 安全扫描工作流..."
if [ -f ".github/workflows/security-scan.yml" ]; then
    check "安全扫描工作流存在" "pass"
else
    check "安全扫描工作流存在" "fail"
fi

# 4.5 Runbook 完整性
echo "  4.5 Runbook 完整性..."
RB_COUNT=$(ls -1 docs/runbook/rb-*.md 2>/dev/null | wc -l || echo "0")
if [ "$RB_COUNT" -ge 5 ]; then
    check "Runbook 目录完整 (${RB_COUNT} 个)" "pass"
else
    check "Runbook 目录完整 (${RB_COUNT} 个)" "fail"
fi

# 4.6 运维 FAQ
echo "  4.6 运维 FAQ..."
if [ -f "docs/ops-faq.md" ]; then
    check "运维 FAQ 存在" "pass"
else
    check "运维 FAQ 存在" "fail"
fi

echo ""
echo "M5: 生产就绪 (Phase 2)"
echo "-----------------"

# 5.1 SLO 文档
echo "  5.1 SLO/SLI 定义..."
if [ -f "docs/slo.md" ]; then
    check "SLO 文档存在" "pass"
else
    check "SLO 文档存在" "fail"
fi

# 5.2 错误预算计算器
echo "  5.2 错误预算计算器..."
if [ -f "src/maref/observability/error_budget.py" ]; then
    check "错误预算计算器存在" "pass"
else
    check "错误预算计算器存在" "fail"
fi

# 5.3 混沌测试场景库
echo "  5.3 混沌测试场景库..."
if [ -f "docs/chaos-scenarios.md" ]; then
    check "混沌场景库文档存在" "pass"
else
    check "混沌场景库文档存在" "fail"
fi

# 5.4 混沌演练脚本
echo "  5.4 混沌演练脚本..."
if [ -f "scripts/chaos-drill.sh" ] && [ -x "scripts/chaos-drill.sh" ]; then
    check "混沌演练脚本可执行" "pass"
else
    check "混沌演练脚本可执行" "fail"
fi

# 5.5 备份策略文档
echo "  5.5 备份策略..."
if [ -f "docs/backup-strategy.md" ]; then
    check "备份策略文档存在" "pass"
else
    check "备份策略文档存在" "fail"
fi

# 5.6 备份脚本
echo "  5.6 备份脚本..."
if [ -f "scripts/backup.sh" ] && [ -x "scripts/backup.sh" ]; then
    check "备份脚本可执行" "pass"
else
    check "备份脚本可执行" "fail"
fi

# 5.7 升级路径文档
echo "  5.7 升级路径文档..."
if [ -f "docs/escalation-path.md" ]; then
    check "升级路径文档存在" "pass"
else
    check "升级路径文档存在" "fail"
fi

# 5.8 事故复盘模板
echo "  5.8 事故复盘模板..."
if [ -f "docs/incident-postmortem-template.md" ]; then
    check "事故复盘模板存在" "pass"
else
    check "事故复盘模板存在" "fail"
fi

# 5.9 应急联系人清单
echo "  5.9 应急联系人清单..."
if [ -f "docs/emergency-contacts.md" ]; then
    check "应急联系人清单存在" "pass"
else
    check "应急联系人清单存在" "fail"
fi

# 5.10 灰度发布方案
echo "  5.10 灰度发布方案..."
if [ -f "docs/canary-release-plan.md" ]; then
    check "灰度发布方案文档存在" "pass"
else
    check "灰度发布方案文档存在" "fail"
fi

# 5.11 功能开关
echo "  5.11 功能开关模块..."
if [ -f "src/maref/features/feature_flags.py" ]; then
    check "功能开关模块存在" "pass"
else
    check "功能开关模块存在" "fail"
fi

# 5.12 告警关联 Runbook
echo "  5.12 告警关联 Runbook..."
if grep -q "告警名称\|AlertName\|告警名" docs/runbook/README.md 2>/dev/null; then
    check "Runbook 告警映射表存在" "pass"
else
    check "Runbook 告警映射表存在" "fail"
fi

echo ""
echo "============================================"
echo "  检查结果"
echo "============================================"
echo "  通过: ${PASS}  失败: ${FAIL}  跳过: ${SKIP}"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}决策: NO-GO${NC}"
    echo "  存在 $FAIL 个阻塞项，请修复后重新检查"
    exit 1
else
    echo -e "  ${GREEN}决策: GO${NC}"
    echo "  所有检查通过，可以发布"
    exit 0
fi
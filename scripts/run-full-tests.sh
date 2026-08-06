#!/bin/bash
# Full MAREF test suite runner
# 在新会话中执行: bash scripts/run-full-tests.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
LOGFILE="$REPO_DIR/.missions/v0.25.0-security-enhancement/full-test-report.txt"

echo "============================================"
echo " MAREF 全量测试套件"
echo " 时间: $TIMESTAMP"
echo " 仓库: $REPO_DIR"
echo "============================================"
echo ""

# ── Python 虚拟环境 ──
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# ── 运行测试 ──
echo "▶ 运行全量测试 (pytest)..."
echo ""

python3 -m pytest tests/ -v --tb=short --no-cov 2>&1 | tee "$LOGFILE"
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 全量测试通过"
else
    echo "❌ 全量测试失败 (exit code: $EXIT_CODE)"
    echo "   详情: $LOGFILE"
fi

echo ""
echo "按 Enter 键关闭此窗口..."
read -r
exit $EXIT_CODE

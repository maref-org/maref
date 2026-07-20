#!/usr/bin/env bash
# MAREF 治理补强 - 一键部署启动脚本
# 启动修复版 sidecar，展示 IDE 配置状态

SIDECAR_PORT=${1:-8010}
MAREF_DIR="$PROJECT_ROOT"

echo "=============================="
echo " MAREF 治理补强 - 一键部署"
echo "=============================="

# 1. 验证环境
echo ""
echo "[1/3] 验证环境..."

# Python
PYTHON_VERSION=$(python3 --version 2>&1)
echo "  ✅ Python: $PYTHON_VERSION"

# 依赖
python3 -c "import aiohttp; import fastapi; import uvicorn; import typer" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "  ✅ 依赖: aiohttp, fastapi, uvicorn, typer"
else
    echo "  ⚠️  部分依赖缺失，安装中..."
    cd "$MAREF_DIR" && pip install -e . --break-system-packages 2>/dev/null
fi

# 2. 检查配置
echo ""
echo "[2/3] 检查 IDE 配置..."

# Trae
if [ -f ~/.trae/mcp_config.json ]; then
    AGENT_ID=$(python3 -c "import json; print(json.load(open('$HOME/.trae/mcp_config.json'))['mcpServers']['maref-governance']['env']['MAREF_AGENT_ID'])")
    echo "  ✅ Trae:    ~/.trae/mcp_config.json (agent: $AGENT_ID)"
else
    echo "  ❌ Trae: 未配置"
fi

# Cursor
if [ -f ~/.cursor/mcp_config.json ]; then
    AGENT_ID=$(python3 -c "import json; print(json.load(open('$HOME/.cursor/mcp_config.json'))['mcpServers']['maref-governance']['env']['MAREF_AGENT_ID'])")
    echo "  ✅ Cursor:  ~/.cursor/mcp_config.json (agent: $AGENT_ID)"
else
    echo "  ❌ Cursor: 未配置"
fi

# OpenCode
if [ -f "$MAREF_DIR/opencode.json" ]; then
    AGENT_ID=$(python3 -c "import json; print(json.load(open('$MAREF_DIR/opencode.json'))['mcpServers']['maref-governance']['env']['MAREF_AGENT_ID'])")
    echo "  ✅ OpenCode: $MAREF_DIR/opencode.json (agent: $AGENT_ID)"
else
    echo "  ❌ OpenCode: 未配置"
fi

# 3. 启动 sidecar
echo ""
echo "[3/3] 启动修复版 sidecar..."

cd "$MAREF_DIR"

# 检查旧进程
OLD_PID=$(lsof -ti:$SIDECAR_PORT 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    echo "  ⚠️  端口 $SIDECAR_PORT 已被占用 (PID: $OLD_PID)"
    kill $OLD_PID 2>/dev/null
    sleep 2
    echo "  ✅ 旧进程已清理"
fi

# 后台启动
nohup python3 scripts/maref_lite_fixed.py serve --port $SIDECAR_PORT > /tmp/maref_sidecar.log 2>&1 &
SIDECAR_PID=$!
sleep 4

# 验证
curl -s http://127.0.0.1:$SIDECAR_PORT/api/health > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "  ✅ Sidecar 已启动 (PID: $SIDECAR_PID, 端口: $SIDECAR_PORT)"
else
    echo "  ❌ Sidecar 启动失败"
    cat /tmp/maref_sidecar.log
    exit 1
fi

# 完成
echo ""
echo "=============================="
echo "  MAREF 治理补强已就绪"
echo "=============================="
echo ""
echo "📊 端点地址:"
echo "   健康检查:  http://127.0.0.1:$SIDECAR_PORT/api/health"
echo "   治理状态:  http://127.0.0.1:$SIDECAR_PORT/api/v1/governance/state"
echo "   GaaS 治理: http://127.0.0.1:$SIDECAR_PORT/api/v1/gaas/govern"
echo "   合规检查:  http://127.0.0.1:$SIDECAR_PORT/api/compliance/check-action"
echo ""
echo "🔧 MCP Guard 审计日志: ~/.maref_mcp_guard_audit.log"
echo ""
echo "🚀 重启 IDE 使配置生效:"
echo "   1. Trae:    完全退出并重启"
echo "   2. Cursor:  完全退出并重启"
echo "   3. OpenCode:在 $MAREF_DIR 中重启"
echo ""
echo "📝 验证命令:"
echo "   实时日志:   tail -f ~/.maref_mcp_guard_audit.log"
echo "   测试端点:   curl -X POST http://127.0.0.1:$SIDECAR_PORT/api/v1/gaas/govern"
echo "              -H 'X-API-Key: default-key' -d '{...}'"
echo ""
echo "   停止命令:   kill $SIDECAR_PID"
echo "=============================="
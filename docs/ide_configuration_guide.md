# IDE 配置指南 - MAREF MCP Guard

## 前置条件

1. **修复版 sidecar 已启动**
   ```bash
   cd /Volumes/1TB-M2/public/maref
   python3 scripts/maref_lite_fixed.py serve --port 8010
   ```

2. **验证 sidecar 运行**
   ```bash
   curl http://127.0.0.1:8010/api/health
   # 应返回: {"status": "healthy", ...}
   ```

## Trae 配置

### 1. 复制配置文件

```bash
cp /Volumes/1TB-M2/public/maref/scripts/trae_mcp_config.json ~/.trae/mcp_config.json
```

### 2. 验证配置

配置文件内容 (`~/.trae/mcp_config.json`):
```json
{
  "mcpServers": {
    "maref-governance": {
      "command": "python3",
      "args": [
        "/Volumes/1TB-M2/public/maref/scripts/simple_mcp_guard.py"
      ],
      "env": {
        "MAREF_AGENT_ID": "trae-cn",
        "MAREF_SIDECAR_URL": "http://127.0.0.1:8010",
        "MAREF_API_KEY": "default-key",
        "MAREF_TENANT_ID": "default"
      }
    }
  }
}
```

### 3. 重启 Trae

完全退出 Trae 并重新启动，MCP Guard 将自动加载。

### 4. 验证集成

在 Trae 中执行以下操作测试治理拦截：
1. 尝试写入文件: `Write /tmp/test.txt`
2. 尝试读取文件: `Read /tmp/test.txt`
3. 尝试执行命令: `Bash ls -la`

预期结果：
- ✅ 每次工具调用前显示治理检查结果
- ✅ 审计日志记录在 `~/.maref_mcp_guard_audit.log`

## OpenCode 配置

### 1. 配置文件位置

OpenCode 会自动发现项目根目录的 `opencode.json`。

文件已创建在：`/Volumes/1TB-M2/public/maref/opencode.json`

### 2. 验证配置

配置文件内容 (`/Volumes/1TB-M2/public/maref/opencode.json`):
```json
{
  "mcpServers": {
    "maref-governance": {
      "command": "python3",
      "args": [
        "scripts/simple_mcp_guard.py"
      ],
      "env": {
        "MAREF_AGENT_ID": "opencode",
        "MAREF_SIDECAR_URL": "http://127.0.0.1:8010",
        "MAREF_API_KEY": "default-key",
        "MAREF_TENANT_ID": "default"
      }
    }
  }
}
```

### 3. 重启 OpenCode

在项目目录 (`/Volumes/1TB-M2/public/maref`) 中重启 OpenCode。

### 4. 验证集成

在 OpenCode 中执行工具调用，验证治理拦截。

## Cursor 配置

### 1. 创建配置目录

```bash
mkdir -p ~/.cursor
```

### 2. 复制配置文件

```bash
cp /Volumes/1TB-M2/public/maref/scripts/trae_mcp_config.json ~/.cursor/mcp_config.json
```

### 3. 修改配置

编辑 `~/.cursor/mcp_config.json`，将 `MAREF_AGENT_ID` 改为 `cursor`:
```json
{
  "mcpServers": {
    "maref-governance": {
      "env": {
        "MAREF_AGENT_ID": "cursor"
      }
    }
  }
}
```

### 4. 重启 Cursor

完全退出 Cursor 并重新启动。

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MAREF_AGENT_ID` | 代理标识 | `unknown-agent` |
| `MAREF_SIDECAR_URL` | sidecar URL | `http://127.0.0.1:8010` |
| `MAREF_API_KEY` | API 密钥 | `default-key` |
| `MAREF_TENANT_ID` | 租户 ID | `default` |

## 故障排除

### 问题 1: MCP Guard 未加载

**症状**: 工具调用未显示治理检查

**解决**:
1. 检查配置文件路径是否正确
2. 验证配置文件 JSON 格式
3. 重启 IDE
4. 查看 IDE 的 MCP 日志

### 问题 2: 治理检查失败

**症状**: 所有工具调用都失败

**解决**:
1. 检查 sidecar 是否运行: `curl http://127.0.0.1:8010/api/health`
2. 检查 API key 是否正确: `default-key`
3. 检查网络连接
4. 查看审计日志: `cat ~/.maref_mcp_guard_audit.log`

### 问题 3: sidecar 端口冲突

**症状**: sidecar 启动失败

**解决**:
1. 更换端口: `python3 scripts/maref_lite_fixed.py serve --port 8011`
2. 更新 IDE 配置中的 `MAREF_SIDECAR_URL`
3. 检查是否有其他进程占用端口

### 问题 4: 权限拒绝

**症状**: 文件写入被拒绝

**解决**:
1. 检查文件路径是否在允许范围内
2. 检查 MAREF 治理策略配置
3. 查看治理决策原因

## 监控和验证

### 检查审计日志

```bash
# 实时查看审计日志
tail -f ~/.maref_mcp_guard_audit.log

# 统计治理检查次数
wc -l ~/.maref_mcp_guard_audit.log

# 查看最近的治理决策
tail -5 ~/.maref_mcp_guard_audit.log | python3 -m json.tool
```

### 测试治理端点

```bash
# 测试 GaaS 端点
curl -X POST http://127.0.0.1:8010/api/v1/gaas/govern \
  -H "Content-Type: application/json" \
  -H "X-API-Key: default-key" \
  -d '{
    "tenant_id": "default",
    "actor_id": "trae-cn",
    "action": "write_file",
    "tool": "Write",
    "file_path": "/tmp/test.txt"
  }'
```

### 检查 sidecar 状态

```bash
# 健康检查
curl http://127.0.0.1:8010/api/health

# 治理状态
curl http://127.0.0.1:8010/api/v1/governance/state

# 代理列表
curl http://127.0.0.1:8010/api/agents
```

## 性能优化

### 1. 启用缓存

在环境变量中启用治理决策缓存:
```bash
export MAREF_CACHE_ENABLED=true
export MAREF_CACHE_TTL=300
```

### 2. 异步审计

确保审计日志异步写入，不影响工具调用性能。

### 3. 连接池

使用 HTTP 连接池减少连接开销。

## 高级配置

### 自定义治理规则

编辑治理策略文件（如支持）:
```json
{
  "rules": [
    {
      "pattern": "/etc/*",
      "action": "deny",
      "reason": "System directory access not allowed"
    },
    {
      "pattern": "*.pem",
      "action": "require_hitl",
      "reason": "Cryptographic key requires approval"
    }
  ]
}
```

### HITL 集成

配置人工审批流程:
1. 设置 HITL 端点: `http://127.0.0.1:8010/api/v1/hitl/request`
2. 配置审批超时: `MAREF_HITL_TIMEOUT=300`
3. 设置通知渠道

## 更新和维护

### 更新 MCP Guard

```bash
cd /Volumes/1TB-M2/public/maref
git pull
pip install -e . --break-system-packages
```

### 重启服务

```bash
# 停止 sidecar
pkill -f "maref_lite_fixed"

# 重新启动
python3 scripts/maref_lite_fixed.py serve --port 8010

# 重启 IDE
```

## 支持

如有问题，请检查:
1. 审计日志: `~/.maref_mcp_guard_audit.log`
2. sidecar 日志: `/tmp/maref_sidecar.log`
3. 项目文档: `/Volumes/1TB-M2/public/maref/docs/`

---

**配置完成日期**: 2026-06-29
**版本**: MAREF v0.35.0b0
**MCP Guard 版本**: 1.0.0
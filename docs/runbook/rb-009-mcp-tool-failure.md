# RB-009: MCP 工具调用失败

## 告警信息

- **告警名**: `MarefMCPToolFailure`
- **严重级别**: P1（单工具失败）/ P0（全部工具失败）
- **触发条件**: MCP 工具调用返回错误或超时

## 影响范围

- opencode Agent 无法调用 Sidecar 提供的 MCP 工具
- 浏览器自动化、文件操作、系统命令等依赖 MCP 的功能不可用
- Agent 治理循环可能中断

## 诊断步骤

1. 检查 `maref health` CLI 是否正常响应
   ```bash
   maref health
   ```

2. 检查 opencode.json 中 MCP 连接配置
   ```bash
   cat .opencode/opencode.json | grep -A 10 mcpServers
   ```

3. 验证状态机未进入 HALT 状态
   ```bash
   curl -s http://localhost:8080/api/v1/state | jq .fsm.state
   ```

4. 检查 Sidecar MCP 日志
   ```bash
   maref logs --tail 100 | grep -i "mcp\|tool"
   ```

## 处置方案

| 场景 | 操作 | 预计恢复时间 |
|------|------|-------------|
| 配置缺失或错误 | 检查 opencode.json 中 stdio 连接路径，确保指向正确 | 1-2 分钟 |
| 状态机 HALT | 执行 `maref fsm resume` 恢复 | 1 分钟 |
| Sidecar 进程异常 | 执行 `maref restart` 重启 Sidecar | 1-2 分钟 |
| 工具超时 | 检查工具执行耗时，调整 MCP 超时配置 | 5 分钟 |

## 验证

```bash
maref health && curl -s http://localhost:8080/api/v1/state | jq .fsm.state
```

## 升级路径

- 单工具失败持续 > 30 分钟：通知 Sidecar 维护团队
- 全部工具失败：检查 Sidecar 进程和系统资源，按 P0 升级至 SRE
- MCP 协议兼容性问题：记录版本信息并提交 Issue

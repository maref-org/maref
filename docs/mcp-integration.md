# MAREF MCP Integration

MAREF 作为 MCP (Model Context Protocol) 服务器运行。

## 端点
- `POST /api/mcp` — JSON-RPC 2.0 MCP 端点
- `GET /api/mcp/.well-known` — 服务发现

## 工具
| 工具 | 描述 | 参数 |
|------|------|------|
| governance_check | 检查操作是否符合治理策略 | action, agent_id, context |
| audit_query | 查询审计日志 | time_range, filters |
| trust_score | 查询 Agent 信任评分 | agent_id |

## 与 Anthropic MCP 的兼容性
已验证兼容 Anthropic Claude Desktop、VS Code 扩展等 MCP 客户端。

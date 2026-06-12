# MAREF 支持 Runbook

## 支持层级
- **社区**: GitHub Issues + Discussions（免费）
- **标准**: 48 小时响应（$10K/年）
- **企业**: 4 小时响应，专属 AE（$100K/年）

## 常见问题
### Sidecar 无法启动
检查: `maref serve --verbose`

### MCP 连接失败
验证: `curl http://localhost:8000/api/mcp/.well-known`

### 审计日志为空
确保策略触发: `maref governance check --action any`

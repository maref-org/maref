# MAREF Error Code Mapping

## Error Response Format
All API errors return:
```json
{
  "error": {
    "code": "ERR_XXX",
    "message": "Human-readable description",
    "details": {}
  }
}
```

## Error Code Table

| Code | HTTP Status | Category | Frontend Display |
|------|-------------|----------|-----------------|
| ERR_AUTH_001 | 401 | Authentication | "身份验证失败，请重新连接" |
| ERR_AUTH_002 | 403 | Authorization | "无权限执行此操作" |
| ERR_GOV_001 | 400 | Governance | "治理规则拒绝此操作" |
| ERR_GOV_002 | 429 | Rate Limit | "操作过于频繁，请稍后再试" |
| ERR_GOV_003 | 503 | Circuit Breaker | "系统暂时不可用，熔断保护中" |
| ERR_AGENT_001 | 400 | Agent | "Agent 操作参数无效" |
| ERR_AGENT_002 | 404 | Agent | "Agent 不存在或已离线" |
| ERR_AGENT_003 | 500 | Agent | "Agent 执行异常" |
| ERR_DESKTOP_001 | 400 | Desktop | "桌面操作参数无效" |
| ERR_DESKTOP_002 | 403 | Desktop | "桌面操作被安全门拦截" |
| ERR_DESKTOP_003 | 500 | Desktop | "桌面操作执行失败" |
| ERR_MCP_001 | 400 | MCP | "MCP 请求参数无效" |
| ERR_MCP_002 | 404 | MCP | "MCP 工具/资源不存在" |
| ERR_MCP_003 | 500 | MCP | "MCP 执行错误" |
| ERR_SYS_001 | 500 | System | "内部系统错误" |
| ERR_SYS_002 | 503 | System | "服务暂不可用" |

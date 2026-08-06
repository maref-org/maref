---
sidebar_position: 13
title: 错误代码
description: MAREF 错误代码、HTTP 状态码和故障排除指南的完整参考
---

# 错误代码

## 错误响应格式
所有 API 错误返回：
```json
{
  "error": {
    "code": "ERR_XXX",
    "message": "Human-readable description",
    "details": {}
  }
}
```

## 错误代码表

| 代码 | HTTP 状态码 | 分类 | 描述 |
|------|-------------|------|------|
| ERR_AUTH_001 | 401 | 身份验证 | 身份验证失败，请重新连接 |
| ERR_AUTH_002 | 403 | 授权 | 无权限执行此操作 |
| ERR_GOV_001 | 400 | 治理 | 治理规则拒绝此操作 |
| ERR_GOV_002 | 429 | 频率限制 | 操作过于频繁，请稍后再试 |
| ERR_GOV_003 | 503 | 熔断保护 | 系统暂时不可用，熔断保护中 |
| ERR_AGENT_001 | 400 | Agent | Agent 操作参数无效 |
| ERR_AGENT_002 | 404 | Agent | Agent 不存在或已离线 |
| ERR_AGENT_003 | 500 | Agent | Agent 执行异常 |
| ERR_DESKTOP_001 | 400 | 桌面 | 桌面操作参数无效 |
| ERR_DESKTOP_002 | 403 | 桌面 | 桌面操作被安全门拦截 |
| ERR_DESKTOP_003 | 500 | 桌面 | 桌面操作执行失败 |
| ERR_MCP_001 | 400 | MCP | MCP 请求参数无效 |
| ERR_MCP_002 | 404 | MCP | MCP 工具/资源不存在 |
| ERR_MCP_003 | 500 | MCP | MCP 执行错误 |
| ERR_SYS_001 | 500 | 系统 | 内部系统错误 |
| ERR_SYS_002 | 503 | 系统 | 服务暂不可用 |

## 按分类排查问题

### 身份验证错误（ERR_AUTH_\*）
- 验证 API 密钥或令牌是否有效
- 如果令牌已过期，请重新认证
- 检查 Agent 身份配置

### 治理错误（ERR_GOV_\*）
- 检查治理策略规则
- 查看频率限制或熔断状态
- 等待熔断恢复期

### 桌面错误（ERR_DESKTOP_\*）
- 确认桌面环境可访问
- 检查安全门权限
- 审核桌面操作参数

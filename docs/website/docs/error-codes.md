---
sidebar_position: 13
title: Error Codes
description: Complete reference of MAREF error codes, HTTP status codes, and troubleshooting guidance
---

# Error Codes

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

| Code | HTTP Status | Category | Description |
|------|-------------|----------|-------------|
| ERR_AUTH_001 | 401 | Authentication | Authentication failed, please reconnect |
| ERR_AUTH_002 | 403 | Authorization | No permission for this operation |
| ERR_GOV_001 | 400 | Governance | Governance rule rejected this operation |
| ERR_GOV_002 | 429 | Rate Limit | Too many requests, please retry later |
| ERR_GOV_003 | 503 | Circuit Breaker | System temporarily unavailable, circuit breaker active |
| ERR_AGENT_001 | 400 | Agent | Invalid agent operation parameters |
| ERR_AGENT_002 | 404 | Agent | Agent not found or offline |
| ERR_AGENT_003 | 500 | Agent | Agent execution error |
| ERR_DESKTOP_001 | 400 | Desktop | Invalid desktop operation parameters |
| ERR_DESKTOP_002 | 403 | Desktop | Desktop operation blocked by safety gate |
| ERR_DESKTOP_003 | 500 | Desktop | Desktop operation execution failed |
| ERR_MCP_001 | 400 | MCP | Invalid MCP request parameters |
| ERR_MCP_002 | 404 | MCP | MCP tool/resource not found |
| ERR_MCP_003 | 500 | MCP | MCP execution error |
| ERR_SYS_001 | 500 | System | Internal system error |
| ERR_SYS_002 | 503 | System | Service temporarily unavailable |

## Troubleshooting by Category

### Authentication Errors (ERR_AUTH_\*)
- Verify your API key or token is valid
- Re-authenticate if token has expired
- Check agent identity configuration

### Governance Errors (ERR_GOV_\*)
- Review governance policy rules
- Check for rate limiting or circuit breaker status
- Wait for circuit breaker cooldown period

### Desktop Errors (ERR_DESKTOP_\*)
- Verify desktop environment is accessible
- Check safety gate permissions
- Review desktop operation parameters

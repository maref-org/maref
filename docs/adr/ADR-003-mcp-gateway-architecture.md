# ADR-003: MCP Gateway 架构 — 集中式代理层

**状态**: 已接受
**日期**: 2026-05-14
**决策者**: MAREF 架构组

## 背景

MAREF 需要统一的 MCP (Model Context Protocol) 网关来管理多个 Agent 对工具和资源的访问。直接让 Agent 访问 MCP Server 存在以下问题：

1. **安全盲区**：Agent 可绕过治理直接调用任意 MCP Server
2. **治理碎片**：每个 Agent 自行实现策略导致不一致
3. **审计缺口**：分散调用无法形成统一审计链
4. **故障扩散**：一个 MCP Server 故障可能导致级联失败

## 决策

**实现 MCP Gateway 作为集中式代理层，所有 MCP 调用必须经过 Gateway。Gateway 包含安全门、策略引擎、断路器和 HMAC 审计四个核心组件。**

### 架构

```
Agent
  │
  ▼
MCPClient ──► MCPGateway
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
   Security    Policy    Circuit
     Gate      Engine    Breaker
        │         │         │
        └─────────┼─────────┘
                  ▼
           HMAC Audit Log
                  │
                  ▼
           MCP Backend 1     MCP Backend 2
           (stdio/sse/http)  (stdio/sse/http)
```

### 核心组件

| 组件 | 职责 | 实现 |
|------|------|------|
| Security Gate | 输入验证、信任等级评估、Zero Trust Context 构建 | `MCPSecurityGate` |
| Policy Engine | 规则链评估（ALLOW/DENY/ASK_USER） | `MCPPolicyEngine` + `MCPPolicyRule` |
| Circuit Breaker | 故障隔离（深度、振荡、失败计数） | `CircuitBreaker` + `MCPCircuitBreakerMonitor` |
| HMAC Audit | 不可篡改审计日志 | HMAC-SHA256 签名链 |
| HITL Router | 高风险操作的人类审批 | `HITLRouter` |

### 策略规则链（优先级从高到低）

| 规则 | ID | 优先级 | 行为 |
|------|----|--------|------|
| MCP 协议信号 | mcp-rule-001 | 100 | ALLOW（自动放行） |
| 已知安全工具 | mcp-rule-002 | 90 | ALLOW |
| 危险工具 | mcp-rule-003 | 80 | ASK_USER |
| 危险参数 | mcp-rule-004 | 75 | DENY |
| 修改操作 | mcp-rule-005 | 60 | ASK_USER |
| 信任等级门 | mcp-rule-006 | 50 | 按信任等级决策 |

### YAML 策略映射

Gateway 支持通过 YAML 配置文件动态映射工具到规则：

```yaml
version: "1.0"
mappings:
  - tools: ["ping", "tools/list", "resources/list"]
    rule: "mcp-rule-001"
  - tools: ["read_file", "search_files"]
    rule: "mcp-rule-002"
  - patterns: ["write_", "delete_", "push_"]
    rule: "mcp-rule-005"
  - patterns: ["*"]
    rule: "mcp-rule-006"
```

### 调用流程

1. Agent 通过 MCPClient 发起工具调用
2. MCPClient 将请求转发给 MCPGovernance
3. CircuitBreakerMonitor 检查是否应熔断
4. CircuitBreaker 检查深度
5. PolicyEngine 按优先级评估规则
6. ASK_USER 结果被路由到 HITLRouter
7. 结果记录到 HMAC 审计日志
8. 允许的调用转发到 MCP Backend

## 后果

- **正面**：统一安全策略，消除治理碎片化
- **正面**：完整审计链，支持合规导出（JSON/Syslog）
- **正面**：断路器防止级联故障
- **正面**：YAML 策略映射支持运行时配置
- **负面**：增加一次代理跳转延迟（通常 <5ms）
- **负面**：Gateway 成为潜在单点故障
- **缓解**：Gateway 可水平扩展，Circuit Breaker 在 Gateway 级别也生效

## 实施检查项

- [x] MCPSecurityGate 实现
- [x] MCPPolicyEngine + 6 条内置规则
- [x] MCPGovernance 管线实现
- [x] CircuitBreaker + MCPCircuitBreakerMonitor
- [x] HMAC 审计签名与验证
- [x] HITL 路由集成
- [x] YAML 策略映射
- [x] MCPMappedPolicyEngine
- [x] 审计导出（JSON/Syslog）

## 替代方案

- **Agent 侧治理** — 被否决，治理策略分散，审计不完整
- **Sidecar 模式** — 被否决，每个 Agent 部署 Sidecar 增加运维成本
- **无 Gateway 直接调用** — 被否决，无法实现统一安全策略

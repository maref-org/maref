# ADR-002: A2A 网络层协议 — JSON-RPC over HTTP + SSE

**状态**: 已接受
**日期**: 2026-05-14
**决策者**: MAREF 架构组

## 背景

MAREF 需要标准化的 Agent-to-Agent (A2A) 通信协议，支持任务委派、状态同步和跨 Agent 治理审计。选择方案时需权衡：

1. **互操作性**：需与 A2A v1.0 规范兼容（Google 倡议）
2. **实时性**：支持服务器推送通知（SSE），无需轮询
3. **安全性**：支持 HMAC 签名审计链和 Agent 身份验证
4. **去中心化**：不依赖中央消息代理，Agent 直接通信

## 决策

**采用 A2A v1.0 协议，JSON-RPC over HTTP 作为请求-响应模式，SSE 作为推送通知模式，Heartbeat Registry 作为服务发现机制。**

### 协议栈

| 层 | 选择 | 理由 |
|---|------|------|
| 传输 | HTTP/1.1 + HTTPS | 通用兼容，TLS 天然支持 |
| RPC | JSON-RPC 2.0 | 轻量，无 schema 依赖，广泛支持 |
| 推送 | Server-Sent Events | 单向推送，比 WebSocket 简单 |
| 发现 | Heartbeat Registry | 去中心化，无单点故障 |
| 序列化 | JSON | 通用，与 JSON-RPC 天然匹配 |
| 身份 | Agent Card (JWT) | 自描述，支持 DID 关联 |
| 审计 | HMAC-SHA256 链 | 不可篡改审计追踪 |

### Agent Card 结构

```json
{
  "name": "agent-name",
  "description": "Agent 描述",
  "version": "0.2.0",
  "url": "http://agent:port",
  "protocolVersion": "0.2.6",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "stateTransitionHistory": true
  },
  "skills": [
    {
      "id": "skill-id",
      "name": "技能名称",
      "description": "技能描述",
      "tags": ["tag1", "tag2"],
      "examples": ["Example usage"]
    }
  ],
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["application/json"]
}
```

### A2A 端点

- `GET /api/health` — 健康检查
- `GET /a2a/.well-known/agent-card` — Agent Card 发现
- `POST /a2a/tasks/send` — 发送任务 (JSON-RPC)
- `POST /a2a/tasks/get` — 查询任务状态
- `POST /a2a/tasks/cancel` — 取消任务
- `GET /a2a/events` — SSE 事件流

### 心跳注册（Agent Discovery）

Agent 启动时向 Registry 注册心跳（TTL=60s），Registry 提供 `GET /a2a/agents` 列出所有活跃 Agent。

## 后果

- **正面**：与 A2A v1.0 规范兼容，支持标准 Agent 发现和互操作
- **正面**：SSE 推送减少轮询开销，状态同步延迟 <1s
- **正面**：去中心化设计无单点故障
- **负面**：HTTP 无内置双向流（WebSocket 更适合实时对话）
- **负面**：JSON-RPC 无内省机制（需自行实现 Schema 校验）
- **缓解**：SSE 补偿推送场景，Agent Card 提供技能内省

## 实施检查项

- [x] A2A Bridge 核心类实现
- [x] JSON-RPC 请求/响应序列化
- [x] Agent Card 构建与验证
- [x] A2A Client (HTTP 客户端)
- [x] A2A Server (FastAPI Router)
- [ ] SSE 推送到 Agent 事件流
- [ ] Heartbeat Registry 完整实现
- [ ] Agent 发现端点 (`/a2a/agents`)

## 替代方案

- **gRPC + Protocol Buffers** — 被否决，增加序列化复杂性，与 A2A v1.0 不兼容
- **WebSocket 全双工** — 被否决，维护连接成本高，A2A 主要是请求-响应加推送
- **Central Message Broker (RabbitMQ/Kafka)** — 被否决，引入单点故障和运维复杂性

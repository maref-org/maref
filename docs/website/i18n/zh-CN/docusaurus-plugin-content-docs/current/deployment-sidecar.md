---
sidebar_position: 11
title: Sidecar 部署
description: 部署 MAREF 观测 Sidecar
---

# Sidecar 部署

## 架构

MAREF Sidecar 与 Agent 进程并行运行，提供治理、可观测性和协议转换（MCP + A2A）。

```
┌─────────────┐     MCP/A2A      ┌────────────────┐      HTTP      ┌──────────────────┐
│   Agent      │ ──────────────>  │ MAREF Sidecar   │ ───────────> │ 目标系统          │
│  (LLM 任务)  │ <────────────── │ 端口 8000       │ <─────────── │ (API、数据库等)   │
└─────────────┘                  └────────────────┘               └──────────────────┘
                                         │
                                         │ /metrics
                                         ▼
                                   ┌──────────┐
                                   │ Prometheus│
                                   └──────────┘
```

## 快速开始

本地运行 Sidecar：

```bash
maref serve --port 8000 --gui
```

这将启动：
- 端口 8000 上的治理 Sidecar
- GUI 仪表盘（如果提供 `--gui`）
- `/metrics` 指标端点

## 生产配置

创建配置文件 `maref.config.yaml`：

```yaml
server:
  host: "0.0.0.0"
  port: 8000
  tls:
    enabled: true
    cert_file: "/etc/maref/certs/tls.crt"
    key_file: "/etc/maref/certs/tls.key"

audit:
  log_path: "/var/log/maref/audit.log"
  hmac_key: "${HMAC_SIGNING_KEY}"
  retention_days: 90

governance:
  safety_level: "production"
  dry_run: false
  recursion_depth: 3
```

使用生产配置运行：

```bash
maref serve --config maref.config.yaml
```

### 审计日志

Sidecar 将 HMAC 签名的审计日志写入配置路径。每条记录包含时间戳、Agent 身份、操作、目标和用于防篡改的 SHA-256 HMAC 签名。

## 端口参考

| 端口 | 服务 | 说明 |
|------|------|------|
| 8000 | Sidecar | MCP/A2A 协议端点 |
| 9090 | 指标 | Prometheus 指标（如启用） |
| 3000-3010 | GUI | 开发 GUI 服务器 |
| 9000-9010 | 测试 | SAEB 基准测试服务器 |

## Docker 运行

容器化 Sidecar 部署请参见 [Docker 部署指南](/docs/deployment-docker)。

## 监控

健康检查端点：

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

指标：

```bash
curl http://localhost:8000/metrics
```

## 故障排除

| 问题 | 检查项 |
|------|--------|
| Sidecar 启动失败 | 确认端口 8000 未被占用 |
| TLS 握手错误 | 检查证书路径和权限 |
| 审计日志未写入 | 确认 `log_path` 目录存在且可写 |

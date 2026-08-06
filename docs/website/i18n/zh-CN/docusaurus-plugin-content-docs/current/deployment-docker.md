---
sidebar_position: 9
title: Docker 部署
description: 使用 Docker 部署 MAREF
---

# Docker 部署

## 快速开始

拉取并运行预构建镜像：

```bash
docker run -d \
  --name maref \
  -p 8080:8080 \
  -p 8000:8000 \
  maref/maref:latest
```

## 从源码构建

使用仓库根目录的多阶段 Dockerfile 构建镜像：

```bash
docker build -t maref:latest .
```

Dockerfile 采用两阶段构建：
- **构建阶段**：将所有 Python 依赖安装到虚拟环境中
- **运行阶段**：将虚拟环境复制到最小的 `python:3.12-slim` 镜像中

运行构建的镜像：

```bash
docker run -d \
  --name maref \
  -p 8080:8080 \
  -p 8000:8000 \
  -v ./config:/app/config:ro \
  -v ./data:/app/data \
  -v ./logs:/app/logs \
  -e MAREF_SAFETY_LEVEL=production \
  maref:latest
```

## Docker Compose

MAREF 与 Prometheus 和 Grafana 的 Compose 示例：

```yaml
version: "3.9"

services:
  maref:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
      - "8000:8000"
    volumes:
      - ./config:/app/config:ro
      - maref_data:/app/data
      - maref_logs:/app/logs
    environment:
      - MAREF_SAFETY_LEVEL=production
      - MAREF_LOG_LEVEL=INFO
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./configs/prometheus:/etc/prometheus
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - ./configs/grafana:/etc/grafana/provisioning
      - grafana_data:/var/lib/grafana

volumes:
  maref_data:
  maref_logs:
  prometheus_data:
  grafana_data:
```

## 端口映射

| 容器端口 | 主机端口 | 服务 |
|---------|---------|------|
| 8080 | 8080 | 治理 API |
| 8000 | 8000 | Sidecar MCP/A2A |
| 9090 | 9090 | Prometheus（Compose） |
| 3000 | 3000 | Grafana（Compose） |

## 卷挂载

| 挂载路径 | 用途 |
|---------|------|
| `/app/config` | 配置文件（只读） |
| `/app/data` | MAREF 运行时数据 |
| `/app/logs` | 审计和应用日志 |
| `/app/research_output` | Agent 研究输出 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAREF_SAFETY_LEVEL` | `production` | 安全模式 |
| `MAREF_LOG_LEVEL` | `INFO` | 日志级别 |
| `MAREF_DRY_RUN` | `false` | 试运行模式 |
| `MAREF_BUFFER_SIZE` | `10000` | 事件缓冲区大小 |
| `MAREF_POLL_INTERVAL` | `1.0` | 轮询间隔（秒） |
| `MAREF_DRIFT_CHECK_INTERVAL` | `60.0` | 漂移检测间隔 |
| `MAREF_REVIEW_TIMEOUT` | `300.0` | 审核超时（秒） |

## 配置

配置参考请参见[部署指南](/docs/deployment)，编排部署请参见 [Kubernetes 部署指南](/docs/deployment-k8s)。

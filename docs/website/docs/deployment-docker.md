---
sidebar_position: 9
title: Docker Deployment
description: Deploy MAREF with Docker
---

# Docker Deployment

## Quick Start

Pull and run the pre-built image:

```bash
docker run -d \
  --name maref \
  -p 8080:8080 \
  -p 8000:8000 \
  maref/lite:latest
```

## Building from Source

Build the Docker image using the multi-stage Dockerfile at the repository root:

```bash
docker build -t maref:latest .
```

The Dockerfile uses a two-stage build:
- **Builder stage**: Installs all Python dependencies into a virtual environment
- **Runtime stage**: Copies the virtual environment into a minimal `python:3.12-slim` image

Run the built image:

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

Example `docker-compose.yml` for MAREF with Prometheus and Grafana:

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

## Port Mapping

| Container Port | Host Port | Service |
|---------------|-----------|---------|
| 8080 | 8080 | Governance API |
| 8000 | 8000 | Sidecar MCP/A2A |
| 9090 | 9090 | Prometheus (Compose) |
| 3000 | 3000 | Grafana (Compose) |

## Volume Mounts

| Mount Path | Purpose |
|------------|---------|
| `/app/config` | Configuration files (read-only) |
| `/app/data` | MAREF runtime data |
| `/app/logs` | Audit and application logs |
| `/app/research_output` | Agent research output |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAREF_SAFETY_LEVEL` | `production` | Safety mode (production/development) |
| `MAREF_LOG_LEVEL` | `INFO` | Log verbosity |
| `MAREF_DRY_RUN` | `false` | Dry-run mode for testing |
| `MAREF_BUFFER_SIZE` | `10000` | Event buffer size |
| `MAREF_POLL_INTERVAL` | `1.0` | Poll interval in seconds |
| `MAREF_DRIFT_CHECK_INTERVAL` | `60.0` | Drift detection interval |
| `MAREF_REVIEW_TIMEOUT` | `300.0` | Review timeout in seconds |

## Configuration

See the [Deployment](/docs/deployment) guide for configuration reference and the [Kubernetes Deployment](/docs/deployment-k8s) guide for orchestrated deployment.

---
sidebar_position: 8
title: 部署
description: MAREF 部署与运维指南
---

# Deployment

## Environment Requirements

- Python 3.10+
- pip 23.0+
- Git 2.30+
- Node.js 20+ (GUI)
- Docker 24.0+ (optional)

## Quick Deploy

```bash
git clone https://github.com/maref-org/maref.git
cd maref
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## GUI Deployment

```bash
cd gui
pnpm install
pnpm dev      # Development
pnpm build    # Production
```

## Docker

```bash
docker build -t maref:latest .
docker run -p 8080:8080 maref:latest
```

## Monitoring

- `GET /health` — Health status
- `GET /metrics` — Prometheus metrics
- `GET /status` — Governance status

See the [full deployment guide on GitHub](https://github.com/maref-org/maref/blob/main/docs/deployment.md) for rollback, alerting, and security recommendations.

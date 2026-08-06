---
sidebar_position: 8
title: Deployment
description: MAREF deployment and operations guide
---

# Deployment

## Environment Requirements

- Python 3.10+
- pip 23.0+
- Git 2.30+
- Node.js 20+ (GUI build)
- pnpm 10+ (GUI build)
- Rust stable (Tauri build, optional)
- Docker 24.0+ (optional)

## Quick Deploy

### 1. Clone Repository

```bash
git clone https://github.com/maref-org/maref.git
cd maref
```

### 2. Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -e ".[dev]"
```

## GUI Deployment

### Development Mode

```bash
cd gui
pnpm install
pnpm dev
```

### Production Build

```bash
cd gui
pnpm build
pnpm preview
```

### Tauri Desktop App

```bash
cd gui
pnpm tauri build
```

Build artifacts at `gui/src-tauri/target/release/bundle/`.

## Docker Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[dev]"
EXPOSE 8080
CMD ["python", "-m", "src.sidecar.server"]
```

```bash
docker build -t maref:latest .
docker run -p 8080:8080 maref:latest
```

## Configuration

Create `.env` file:

```env
MAREF_LOG_LEVEL=INFO
MAREF_BUFFER_SIZE=10000
MAREF_POLL_INTERVAL=1.0
MAREF_DRIFT_CHECK_INTERVAL=60.0
MAREF_REVIEW_TIMEOUT=300.0
MAREF_SAFETY_LEVEL=production
```

## Monitoring

Sidecar HTTP server provides:

- `GET /health` — Health status
- `GET /metrics` — Prometheus metrics
- `GET /status` — Governance status

## Rollback

### K8s Rollback

```bash
bash scripts/rollback.sh v0.25.0
kubectl rollout undo deployment/maref-desktop-agent -n maref
```

### Local Rollback

```bash
git checkout tags/v0.25.0
pip install -e ".[dev]"
pytest
```

## Alert Response

| Alert | Severity | Runbook |
|-------|----------|---------|
| `MarefSidecarDown` | P0 | RB-001 |
| `MarefGovernanceLatencyHigh` | P1 | RB-002 |
| `MarefDriftDetected` | P1 | RB-003 |
| `MarefAuditLogFailure` | P0 | RB-004 |
| `MarefMemoryGrowthAbnormal` | P1 | RB-005 |

See the [full deployment guide on GitHub](https://github.com/maref-org/maref/blob/main/docs/deployment.md) for complete details including system integration, release process, security recommendations, and troubleshooting.

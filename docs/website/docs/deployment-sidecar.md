---
sidebar_position: 11
title: Sidecar Deployment
description: Deploy the MAREF observation sidecar
---

# Sidecar Deployment

## Architecture

The MAREF sidecar runs alongside agent processes to provide governance, observability, and protocol translation (MCP + A2A).

```
┌─────────────┐     MCP/A2A      ┌────────────────┐      HTTP      ┌──────────────────┐
│   Agent      │ ──────────────>  │ MAREF Sidecar   │ ───────────> │ Target Systems    │
│  (LLM Task)  │ <────────────── │ port 8000       │ <─────────── │ (APIs, DBs, etc)  │
└─────────────┘                  └────────────────┘               └──────────────────┘
                                         │
                                         │ /metrics
                                         ▼
                                   ┌──────────┐
                                   │ Prometheus│
                                   └──────────┘
```

## Quick Start

Run the sidecar locally:

```bash
maref serve --port 8000 --gui
```

This starts:
- The governance sidecar on port 8000
- The GUI dashboard (if `--gui` is provided)
- Metrics endpoint on `/metrics`

## Production Configuration

Create a configuration file `maref.config.yaml`:

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

Run with production config:

```bash
maref serve --config maref.config.yaml
```

### Audit Logging

The sidecar writes HMAC-signed audit logs to the configured path. Each entry includes a timestamp, agent identity, action, target, and a SHA-256 HMAC signature for tamper detection.

## Port Reference

| Port | Service | Description |
|------|---------|-------------|
| 8000 | Sidecar | MCP/A2A protocol endpoint |
| 9090 | Metrics | Prometheus metrics (if enabled) |
| 3000-3010 | GUI | Development GUI servers |
| 9000-9010 | Test | SAEB benchmark servers |

## Docker Run

See the [Docker Deployment](/docs/deployment-docker) guide for containerized sidecar deployment.

## Monitoring

Health endpoint:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Metrics:

```bash
curl http://localhost:8000/metrics
```

## Troubleshooting

| Issue | Check |
|-------|-------|
| Sidecar fails to start | Verify port 8000 is not in use |
| TLS handshake errors | Check certificate paths and permissions |
| Audit log not writing | Verify `log_path` directory exists and is writable |

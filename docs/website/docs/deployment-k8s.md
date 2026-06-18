---
sidebar_position: 10
title: Kubernetes Deployment
description: Deploy MAREF on Kubernetes
---

# Kubernetes Deployment

## Prerequisites

- Kubernetes 1.24+
- kubectl configured with cluster access
- Ingress controller (nginx-ingress recommended)
- cert-manager (for TLS certificates, optional)

## Quick Start

Deploy MAREF to the `maref` namespace:

```bash
kubectl create namespace maref
kubectl apply -k k8s/production/
```

Verify the deployment:

```bash
kubectl get pods -n maref
kubectl get svc -n maref
kubectl get ingress -n maref
```

Each pod runs two containers: the governance engine and the sidecar proxy.

## Architecture

MAREF deploys as a sidecar container alongside agent workloads in the same pod. The governance engine (port 8080) handles policy enforcement, while the sidecar (port 8000) handles MCP/A2A protocol traffic.

```
┌──────────────────────────┐
│         Pod              │
│  ┌──────────────────┐    │
│  │ Governance Engine │    │  port 8080
│  │ (maref-governance)│    │
│  └──────────────────┘    │
│  ┌──────────────────┐    │
│  │   Sidecar Proxy   │    │  port 8000
│  │  (maref-sidecar)  │    │
│  └──────────────────┘    │
└──────────────────────────┘
```

## Production Manifests

All manifests are in `k8s/production/` and managed through Kustomize.

| Manifest | Description |
|----------|-------------|
| `deployment.yaml` | Deployment + Service (governance + sidecar containers) |
| `configmap.yaml` | Environment configuration |
| `secrets.yaml` | HMAC signing key and A2A credentials |
| `sealed-secret.yaml` | Encrypted secrets for GitOps workflows |
| `hpa.yaml` | HorizontalPodAutoscaler (CPU 70%, memory 80%) |
| `pdb.yaml` | PodDisruptionBudget (min 1 available) |
| `networkpolicy.yaml` | Network isolation (ingress/egress rules) |
| `ingress.yaml` | TLS ingress with path-based routing |
| `kustomization.yaml` | Kustomize entry point |

### Configuration Options

The `configmap.yaml` exposes the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAREF_CB_MAX_DEPTH` | `3` | Circuit breaker recursion limit |
| `MAREF_CB_COOLDOWN` | `30.0` | Cooldown period after breaker trip |
| `MAREF_DUAL_PRIMARY` | `4.0` | Dual-primary sync interval |
| `MAREF_FNR_TARGET` | `0.15` | False negative rate target |
| `MAREF_A2A_URL` | `http://localhost:8000` | A2A endpoint |
| `MCP_GATEWAY_ENABLED` | `true` | Enable MCP gateway |
| `A2A_DISCOVERY_ENABLED` | `true` | Enable A2A discovery |

## Monitoring

Prometheus metrics are exposed at `/metrics` on both containers. The Grafana dashboard at `configs/grafana/maref-dashboard.json` provides pre-built visualizations for:

- Request rate and latency (governance and sidecar)
- Resource usage (CPU, memory per container)
- Circuit breaker state transitions
- HPA scaling events
- Network policy drops

## Rollback

See the [Deployment](/docs/deployment) guide for rollback procedures.

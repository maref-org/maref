---
sidebar_position: 10
title: Kubernetes 部署
description: 在 Kubernetes 上部署 MAREF
---

# Kubernetes 部署

## 前置条件

- Kubernetes 1.24+
- kubectl 已配置集群访问
- Ingress 控制器（推荐 nginx-ingress）
- cert-manager（可选，用于 TLS 证书）

## 快速开始

将 MAREF 部署到 `maref` 命名空间：

```bash
kubectl create namespace maref
kubectl apply -k k8s/production/
```

验证部署：

```bash
kubectl get pods -n maref
kubectl get svc -n maref
kubectl get ingress -n maref
```

每个 Pod 运行两个容器：治理引擎和 Sidecar 代理。

## 架构

MAREF 以 Sidecar 容器形式与 Agent 工作负载部署在同一 Pod 中。治理引擎（端口 8080）负责策略执行，Sidecar（端口 8000）负责 MCP/A2A 协议流量。

```
┌──────────────────────────┐
│         Pod              │
│  ┌──────────────────┐    │
│  │  治理引擎          │    │  端口 8080
│  │ (maref-governance)│    │
│  └──────────────────┘    │
│  ┌──────────────────┐    │
│  │  Sidecar 代理     │    │  端口 8000
│  │  (maref-sidecar)  │    │
│  └──────────────────┘    │
└──────────────────────────┘
```

## 生产清单

所有清单文件位于 `k8s/production/`，通过 Kustomize 管理。

| 清单文件 | 说明 |
|----------|------|
| `deployment.yaml` | Deployment + Service（治理 + Sidecar 容器） |
| `configmap.yaml` | 环境配置 |
| `secrets.yaml` | HMAC 签名密钥和 A2A 凭证 |
| `sealed-secret.yaml` | GitOps 工作流加密密钥 |
| `hpa.yaml` | HorizontalPodAutoscaler（CPU 70%，内存 80%） |
| `pdb.yaml` | PodDisruptionBudget（最少 1 个可用） |
| `networkpolicy.yaml` | 网络隔离（入站/出站规则） |
| `ingress.yaml` | TLS Ingress，基于路径路由 |
| `kustomization.yaml` | Kustomize 入口文件 |

### 配置选项

`configmap.yaml` 暴露以下环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAREF_CB_MAX_DEPTH` | `3` | 断路器递归限制 |
| `MAREF_CB_COOLDOWN` | `30.0` | 断路器触发后的冷却时间 |
| `MAREF_DUAL_PRIMARY` | `4.0` | 双主同步间隔 |
| `MAREF_FNR_TARGET` | `0.15` | 假阴性率目标 |
| `MAREF_A2A_URL` | `http://localhost:8000` | A2A 端点 |
| `MCP_GATEWAY_ENABLED` | `true` | 启用 MCP 网关 |
| `A2A_DISCOVERY_ENABLED` | `true` | 启用 A2A 发现 |

## 监控

两个容器均在 `/metrics` 暴露 Prometheus 指标。位于 `configs/grafana/maref-dashboard.json` 的 Grafana 仪表盘提供了以下预构建可视化：

- 请求速率和延迟（治理和 Sidecar）
- 资源使用情况（每个容器的 CPU、内存）
- 断路器状态转换
- HPA 扩缩容事件
- 网络策略拦截

使用 Prometheus Operator 部署：

```bash
kubectl apply -f k8s/monitoring/
```

## 回滚

回滚步骤请参见[部署指南](/docs/deployment)。

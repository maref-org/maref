---
sidebar_position: 12
title: Reliability & SLO
description: MAREF service level objectives, error budgets, and reliability targets
---

# Reliability & SLO

MAREF defines Service Level Objectives (SLOs) to quantify reliability, performance, cost, and data quality guarantees. Each SLO includes an error budget that governs how much deviation is tolerated before corrective action is triggered.

## 1. Availability SLO

| Parameter | Value |
|-----------|-------|
| Target | 99.9% uptime (monthly) |
| Measurement | Health check endpoint (`/health`) success rate |
| Error budget | 43 minutes/month downtime |
| Burn rate alert (P2) | 5% error budget consumed in 1 hour |
| Burn rate alert (P1) | 10% error budget consumed in 1 hour |

## 2. Performance SLO (API)

| Parameter | Value |
|-----------|-------|
| Target | P99 latency < 500ms for governance decisions |
| Measurement | OpenTelemetry RED metrics |
| Exclusions | LLM inference calls (measured separately) |
| Error budget | 5% of requests may exceed 500ms |

## 3. Performance SLO (Desktop)

| Parameter | Value |
|-----------|-------|
| Target | P99 latency < 2s for screenshot-to-verify cycle |
| Measurement | DesktopAgent operation metrics |
| Error budget | 2% of operations may exceed 2s |

## 4. Cost SLO

| Parameter | Value |
|-----------|-------|
| Token consumption | < 1000 tokens per governance decision (average) |
| Monthly compute budget | $50/server (3 replicas = $150) |

## 5. Data Quality SLO

| Parameter | Value |
|-----------|-------|
| Audit log integrity | 100% of entries HMAC-verified |
| Trust score freshness | < 30s stale |

## Related

- [Code of Conduct](https://github.com/maref-org/maref/blob/main/CODE_OF_CONDUCT.md)
- [Security Policy](https://github.com/maref-org/maref/security/policy)
- [Issue Tracker](https://github.com/maref-org/maref/issues)

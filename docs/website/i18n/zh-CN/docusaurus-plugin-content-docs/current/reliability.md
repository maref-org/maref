---
sidebar_position: 12
title: 可靠性与 SLO
description: MAREF 服务等级目标、错误预算和可靠性指标
---

# 可靠性与 SLO

MAREF 定义了服务等级目标 (SLO)，用于量化可靠性、性能、成本和数据质量保证。每个 SLO 包含一个错误预算，用于控制在触发纠正措施之前允许的偏差范围。

## 1. 可用性 SLO

| 参数 | 值 |
|------|-----|
| 目标 | 99.9% 可用率（月度） |
| 度量方式 | 健康检查端点（`/health`）成功率 |
| 错误预算 | 每月最多 43 分钟宕机 |
| 消耗速率告警 (P2) | 1 小时内消耗 5% 错误预算 |
| 消耗速率告警 (P1) | 1 小时内消耗 10% 错误预算 |

## 2. 性能 SLO（API）

| 参数 | 值 |
|------|-----|
| 目标 | 治理决策 P99 延迟 < 500ms |
| 度量方式 | OpenTelemetry RED 指标 |
| 排除项 | LLM 推理调用（单独度量） |
| 错误预算 | 5% 的请求可超过 500ms |

## 3. 性能 SLO（桌面端）

| 参数 | 值 |
|------|-----|
| 目标 | 截图到验证周期 P99 延迟 < 2s |
| 度量方式 | DesktopAgent 操作指标 |
| 错误预算 | 2% 的操作可超过 2s |

## 4. 成本 SLO

| 参数 | 值 |
|------|-----|
| Token 消耗 | 每次治理决策 < 1000 tokens（平均） |
| 月度计算预算 | 每台服务器 $50（3 副本 = $150） |

## 5. 数据质量 SLO

| 参数 | 值 |
|------|-----|
| 审计日志完整性 | 100% 条目 HMAC 验证通过 |
| 信任评分时效性 | < 30s 过期 |

## 相关链接

- [行为准则](https://github.com/maref-org/maref/blob/main/CODE_OF_CONDUCT.md)
- [安全策略](https://github.com/maref-org/maref/security/policy)
- [问题追踪](https://github.com/maref-org/maref/issues)

# MAREF SLO/SLI 定义

## 1. 可用性 SLO

| 属性 | 定义 |
|------|------|
| **SLO 目标** | API 可用性 ≥ 99.5%（月度） |
| **SLI 定义** | 健康检查端点 `/health` 和核心 API 端点成功响应的比例 |
| **测量指标** | `http_requests_total` 中 `status_code < 500` 的请求数 / 总请求数 |
| **采集方式** | REDMetricsCollector 实时采集，Prometheus 拉取 |
| **时间窗口** | 滚动 30 天 (720 小时) |
| **计算公式** | `availability = successful_requests / total_requests * 100` |
| **排除条件** | 客户端错误 (4xx) 不计入不可用，仅 5xx 和连接超时计入 |

## 2. 延迟 SLO

| 属性 | 定义 |
|------|------|
| **SLO 目标** | API P99 延迟 < 500ms |
| **SLI 定义** | 核心 API 端点请求延迟的 P99 百分位值 |
| **测量指标** | `http_request_duration_ms` 直方图的 P99 值 |
| **采集方式** | REDMetricsCollector `get_duration_percentiles()` 计算 |
| **时间窗口** | 滚动 5 分钟 (快速检测) + 滚动 30 天 (月度合规) |
| **计算公式** | `p99_latency = percentile(durations, 99)` |
| **排除条件** | 健康检查 (`/health`, `/ready`) 不计入延迟测量 |

## 3. 准确率 SLO

| 属性 | 定义 |
|------|------|
| **SLO 目标** | Agent 决策准确率 ≥ 95% |
| **SLI 定义** | Agent 治理决策被验证为正确的比例 |
| **测量指标** | `agent_decisions_total` 中 `outcome="correct"` / 总决策数 |
| **采集方式** | AuditLogger + 交叉验证器 (cross_validator) 定期验证 |
| **时间窗口** | 滚动 7 天 |
| **计算公式** | `accuracy = correct_decisions / total_decisions * 100` |
| **排除条件** | 人工审批 (HITL) 覆盖的决策不计入，仅全自动决策参与计算 |

## 错误预算计算

### 通用公式

```text
Error Budget = (1 - SLO) × total_period_requests

示例 (可用性 SLO 99.5%, 月度 1,000,000 请求):
  Error Budget = (1 - 0.995) × 1,000,000 = 5,000 次错误
```

### 各 SLO 错误预算

| SLO | 月度目标请求量 (估算) | 错误预算 |
|-----|----------------------|---------|
| 可用性 99.5% | 1,000,000 | 5,000 次不可用响应 |
| 延迟 P99 < 500ms | 1,000,000 | 5,000 次超时 (P99 窗口内) |
| 准确率 ≥ 95% | 100,000 决策 | 5,000 次错误决策 |

### 消耗规则

- 每次违反 SLI 的事件消耗 1 单位错误预算
- 延迟 SLO 的消耗按 P99 窗口计算：窗口期内 P99 ≥ 500ms 计为 1 次违反
- 准确率 SLO 的消耗按单次错误决策计算

## 燃烧率告警规则

### 燃烧率定义

```text
Burn Rate = consumed_budget / (elapsed_time / period)
```

- `consumed_budget`: 时间窗口内已消耗的错误预算
- `elapsed_time`: 时间窗口长度
- `period`: SLO 时间窗口 (通常为 30 天)

### 告警级别

| 级别 | 燃烧率阈值 | 时间窗口 | 触发条件 | 响应时间 |
|------|-----------|---------|---------|---------|
| **P0 (Critical)** | ≥ 14.4x | 1 小时 | 1 小时内消耗超过 2% 月度预算 | 即时响应 (15 分钟内) |
| **P1 (Warning)** | ≥ 6x | 6 小时 | 6 小时内消耗超过 5% 月度预算 | 30 分钟内确认 |
| **P2 (Info)** | ≥ 2x | 3 天 | 3 天内消耗超过 20% 月度预算 | 下一个工作日 |

### 燃烧率计算示例

```text
月度错误预算 = 5000 (可用性 SLO)
燃烧率 14.4x:
  1 小时内消耗 = 5000 × 0.02 = 100 单位
  等效燃烧率 = 100 / (1/720) / 5000 = 14.4

燃烧率 6x:
  6 小时内消耗 = 5000 × 0.05 = 250 单位
  等效燃烧率 = 250 / (6/720) / 5000 = 6.0

燃烧率 2x:
  3 天 (72 小时) 内消耗 = 5000 × 0.20 = 1000 单位
  等效燃烧率 = 1000 / (72/720) / 5000 = 2.0
```

### 多窗口燃烧率告警

每个告警级别使用多时间窗口验证，防止误报：

| 级别 | 快速窗口 | 慢速窗口 | 判定逻辑 |
|------|---------|---------|---------|
| P0 | 1 小时 | 5 分钟 | 任一窗口超过阈值则触发 |
| P1 | 6 小时 | 30 分钟 | 两个窗口均超过阈值才触发 |
| P2 | 3 天 | 6 小时 | 两个窗口均超过阈值才触发 |

### SLI 数据源映射

| SLO | 数据源 | Prometheus 指标 | REDMetrics 方法 |
|-----|--------|----------------|-----------------|
| 可用性 | REDMetricsCollector | `http_requests_total` | `get_error_rate()` |
| 延迟 | REDMetricsCollector | `http_request_duration_ms` | `get_duration_percentiles()['p99']` |
| 准确率 | AuditLogger / CrossValidator | `agent_decisions_total` | 自定义采集 |
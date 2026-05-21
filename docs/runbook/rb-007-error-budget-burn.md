# RB-007: 错误预算燃烧过快

## 告警信息

- **告警名**: `MarefErrorBudgetBurn`
- **严重级别**: P0/P1 (按燃烧率级别)
- **触发条件**: 错误预算燃烧率超过阈值 (P0: ≥ 14.4x / P1: ≥ 6x)

## 影响范围

- SLO 违反风险增加
- 如果预算耗尽，可能触发服务降级
- 系统可靠性下降

## 诊断步骤

1. 查看当前错误预算
   ```bash
   curl -s http://localhost:8080/api/v1/error-budget/report
   ```

2. 检查燃烧率和时间窗口
   ```bash
   curl -s http://localhost:8080/metrics | grep error_budget_burn_rate
   ```

3. 检查 RED 指标找根因
   ```bash
   curl -s http://localhost:8080/metrics | grep http_requests_total
   ```

4. 查看近期错误分布
   ```bash
   curl -s http://localhost:8080/metrics | grep http_request_errors
   ```

## 处置方案

| 场景 | 操作 | 预计恢复时间 |
|------|------|-------------|
| 突发流量导致错误率上升 | 扩容 + 限流 | 2-5 分钟 |
| 代码 Bug 导致 5xx 激增 | 立即回滚 | 5-10 分钟 |
| 依赖服务故障 | 启用熔断降级 | 5-15 分钟 |
| 配置错误 | 修正配置并重启 | 2-5 分钟 |

## 升级路径

- P0 燃烧率 (≥ 14.4x)：即时响应，15 分钟内完成止血
- 预算剩余 < 20%：升级至 SRE 主管
- 预算耗尽：启动紧急服务降级流程

## 验证

```bash
# 确认错误预算消耗停止
curl -s http://localhost:8080/api/v1/error-budget/report | grep remaining_pct
# 确认燃烧率恢复
curl -s http://localhost:8080/api/v1/error-budget/report | grep burn_rate
```
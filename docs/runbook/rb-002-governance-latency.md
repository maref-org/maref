# RB-002: 治理决策延迟超标

## 告警信息

- **告警名**: `MarefGovernanceLatencyHigh`
- **严重级别**: P1
- **触发条件**: P99 治理决策延迟 > 500ms 持续 5 分钟

## 影响范围

- Agent 操作响应变慢
- 用户体验下降
- 可能触发 CircuitBreaker

## 诊断步骤

1. 检查 RED 指标
   ```bash
   curl -s http://localhost:8080/metrics | grep governance_latency
   ```

2. 检查 LLM 调用延迟
   ```bash
   curl -s http://localhost:8080/metrics | grep llm_request_duration
   ```

3. 检查并发量
   ```bash
   curl -s http://localhost:8080/metrics | grep active_agents
   ```

## 处置方案

| 场景 | 操作 |
|------|------|
| LLM 延迟高 | 检查 provider 状态，切换备用模型 |
| 并发过高 | 扩容副本数或启用限流 |
| 内存 GC 压力 | 检查内存使用，必要时重启 |

## 验证

```bash
# 检查 P99 延迟是否恢复
curl -s http://localhost:8080/metrics | grep 'governance_latency_seconds{quantile="0.99"}'
```

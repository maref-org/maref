# RB-006: API 延迟超标

## 告警信息

- **告警名**: `MarefHighLatency`
- **严重级别**: P0
- **触发条件**: API P99 延迟 > 500ms 持续 5 分钟，且错误预算燃烧率 ≥ 14.4x

## 影响范围

- 所有 Agent 操作响应变慢
- 用户体验严重下降
- 可能触发 CircuitBreaker 熔断
- 违反延迟 SLO (P99 < 500ms)

## 诊断步骤

1. 检查 RED 指标
   ```bash
   curl -s http://localhost:8080/metrics | grep http_request_duration_ms
   ```

2. 检查错误预算状态
   ```bash
   curl -s http://localhost:8080/metrics | grep error_budget
   ```

3. 检查 LLM 调用延迟
   ```bash
   curl -s http://localhost:8080/metrics | grep llm_request_duration
   ```

4. 检查并发量和资源使用
   ```bash
   kubectl top pod -n maref -l app=maref
   ```

## 处置方案

| 场景 | 操作 | 预计恢复时间 |
|------|------|-------------|
| LLM Provider 延迟高 | 切换备用模型 Provider | 1-2 分钟 |
| 突发流量导致并发过高 | 扩容副本数或启用限流 | 2-5 分钟 |
| 数据库/缓存慢查询 | 检查 DB 连接池和慢查询日志 | 5-15 分钟 |
| 代码缺陷 (死循环/阻塞) | 回滚至上一稳定版本 | 5-10 分钟 |

## 升级路径

- 首次触发：值班工程师 15 分钟内响应
- 持续超标 > 30 分钟：升级至 SRE 团队
- 持续超标 > 2 小时：升级至技术负责人，启动紧急发布流程

## 验证

```bash
# 检查 P99 延迟是否恢复
curl -s http://localhost:8080/metrics | grep 'http_request_duration_ms'
# 检查错误预算燃烧率是否恢复正常
curl -s http://localhost:8080/api/v1/error-budget/report
```
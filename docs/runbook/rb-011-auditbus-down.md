# RB-011: AuditBus 发布-订阅异常

## 告警信息

- **告警名**: `MarefAuditBusDown`
- **严重级别**: P1（部分事件丢失）/ P0（全部事件阻塞）
- **触发条件**: AuditBus 事件传播延迟 > 5s 或订阅者未收到事件

## 影响范围

- 审计事件无法实时传递至订阅者
- 治理循环依赖审计事件的触发器可能失效
- 事件可能堆积在内存缓冲区，导致 OOM

## 诊断步骤

1. 检查 AuditLogger 磁盘写入是否正常
   ```bash
   ls -la /var/log/maref/audit/ | tail -20
   tail -100 /var/log/maref/audit/audit.log | grep -i error
   ```

2. 检查订阅者注册状态
   ```bash
   curl -s http://localhost:8080/api/v1/auditbus/subscribers | jq .
   ```

3. 检查事件队列积压
   ```bash
   curl -s http://localhost:8080/api/v1/auditbus/stats | jq .queue_depth
   ```

4. 检查缓冲区内存使用
   ```bash
   curl -s http://localhost:8080/metrics | grep auditbus_buffer_bytes
   ```

## 处置方案

| 场景 | 操作 | 预计恢复时间 |
|------|------|-------------|
| 订阅者未注册 | 检查订阅者初始化顺序，确保 start() 调用在 publish() 之前 | 2-5 分钟 |
| 事件队列阻塞 | 重启 AuditBus：`maref auditbus restart` | 1 分钟 |
| 磁盘 I/O 瓶颈 | 检查磁盘负载，考虑异步批量写入 | 5-10 分钟 |
| 订阅者异常崩溃 | 隔离问题订阅者，开启熔断保护 | 5 分钟 |
| 内存缓冲区溢出 | 增大 max_buffer_size 配置或缩小事件保留窗口 | 5 分钟 |

## 验证

```bash
# 确认事件传播恢复
curl -s http://localhost:8080/api/v1/auditbus/stats | jq .events_delivered
# 检查队列深度回零
curl -s http://localhost:8080/api/v1/auditbus/stats | jq .queue_depth
```

## 升级路径

- 事件丢失导致合规差异：通知安全团队评估影响
- AuditBus 完全阻塞 > 10 分钟：通知架构团队评估发布订阅模型是否需要重构
- 事件积压导致内存告警：升级为 P0 并立即清缓冲

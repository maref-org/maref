# RB-005: 内存泄漏/增长异常

## 告警信息

- **告警名**: `MarefMemoryGrowth`
- **严重级别**: P1
- **触发条件**: 内存使用增长率 > 5%/小时 或接近 limits

## 影响范围

- 最终触发 OOMKilled
- 服务中断
- 可能的数据丢失

## 诊断步骤

1. 查看内存趋势
   ```bash
   kubectl top pod -n maref --containers
   ```

2. 检查 Python 内存分配
   ```bash
   kubectl exec -n maref <pod> -- python -c "import tracemalloc; tracemalloc.start()"
   ```

3. 分析日志中的泄漏模式
   ```bash
   kubectl logs -n maref <pod> | grep -i "memory\|leak\|gc"
   ```

## 处置方案

| 场景 | 操作 |
|------|------|
| 正常增长 | 调整 HPA 或增加 limits |
| 泄漏确认 | 重启 Pod，记录堆栈，创建 Issue |
| 突发流量 | 启用限流，扩容 |

## 验证

```bash
kubectl top pod -n maref -l app=maref
```

# RB-001: Sidecar 服务不可用

## 告警信息

- **告警名**: `MarefSidecarDown`
- **严重级别**: P0
- **触发条件**: `/health` 端点连续 3 次返回非 200 状态码

## 影响范围

- Agent 状态收集中断
- 治理决策无法执行
- 审计日志可能丢失

## 诊断步骤

1. 检查 Pod 状态
   ```bash
   kubectl get pods -n maref -l app=maref
   kubectl describe pod <pod-name> -n maref
   ```

2. 查看日志
   ```bash
   kubectl logs -n maref deployment/maref-desktop-agent --tail=200
   ```

3. 检查资源使用
   ```bash
   kubectl top pod -n maref -l app=maref
   ```

## 处置方案

| 场景 | 操作 | 预计恢复时间 |
|------|------|-------------|
| Pod 崩溃重启 | 等待自动重启或手动删除 Pod | 1-2 分钟 |
| OOMKilled | 检查内存限制，必要时扩容 | 2-5 分钟 |
| 依赖服务不可用 | 检查 Redis/DB 状态 | 5-10 分钟 |
| 代码缺陷 | 执行回滚 | 5-10 分钟 |

## 回滚命令

```bash
./scripts/rollback.sh v0.25.0
```

## 验证

```bash
curl -f http://localhost:8080/health
curl -f http://localhost:8080/ready
```

## 升级路径

- 如为已知缺陷，关联 Issue 并安排热修复
- 如为资源不足，调整 HPA 或 limits

# RB-004: 审计日志写入失败

## 告警信息

- **告警名**: `MarefAuditLogFailure`
- **严重级别**: P0
- **触发条件**: 审计日志写入失败率 > 1%

## 影响范围

- 合规性风险
- 安全事件无法追溯
- 可能违反 SOC2/ISO27001 要求

## 诊断步骤

1. 检查存储状态
   ```bash
   df -h /var/log/maref
   kubectl get pvc -n maref
   ```

2. 检查日志错误
   ```bash
   kubectl logs -n maref deployment/maref-desktop-agent | grep -i "audit\|log"
   ```

## 处置方案

| 场景 | 操作 |
|------|------|
| 磁盘满 | 清理旧日志或扩容存储 |
| 权限问题 | 检查文件权限和 SELinux |
| 网络存储故障 | 切换本地缓冲，修复 NFS |

## 验证

```bash
# 检查审计日志写入恢复
curl -s http://localhost:8080/metrics | grep audit_log_writes_total
```

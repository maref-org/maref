# RB-003: 漂移检测异常

## 告警信息

- **告警名**: `MarefDriftDetected`
- **严重级别**: P1
- **触发条件**: 漂移分数超过阈值持续 3 个周期

## 影响范围

- 模型输出质量可能下降
- 需要触发自动重训练或人工介入

## 诊断步骤

1. 查看漂移详情
   ```bash
   curl -s http://localhost:8080/metrics | grep drift_score
   ```

2. 检查输入数据分布
   ```bash
   kubectl logs -n maref deployment/maref-desktop-agent | grep "drift_detected"
   ```

## 处置方案

| 场景 | 操作 |
|------|------|
| 数据分布变化 | 更新训练数据集，触发重训练 |
| 异常输入攻击 | 启用增强过滤，检查安全日志 |
| 阈值过于敏感 | 临时调整阈值，安排调优 |

## 验证

```bash
curl -s http://localhost:8080/metrics | grep 'drift_score'
```

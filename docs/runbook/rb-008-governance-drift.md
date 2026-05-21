# RB-008: 治理漂移异常

## 告警信息

- **告警名**: `MarefGovernanceDrift`
- **严重级别**: P1
- **触发条件**: 治理漂移分数超过阈值持续 3 个检测周期

## 影响范围

- Agent 决策质量可能下降
- 治理一致性受损
- 可能需要触发模型重训练或规则调整

## 诊断步骤

1. 查看漂移详情
   ```bash
   curl -s http://localhost:8080/metrics | grep governance_drift_score
   ```

2. 检查漂移趋势和方向
   ```bash
   curl -s http://localhost:8080/api/v1/governance/drift/history
   ```

3. 对比近期治理策略变更
   ```bash
   git log --oneline --since="7 days ago" -- src/maref/governance/
   ```

## 处置方案

| 场景 | 操作 | 预计恢复时间 |
|------|------|-------------|
| 检测阈值过于敏感 | 调整漂移阈值参数 | 1 小时内 |
| 训练数据分布变化 | 更新训练数据集，触发重训练 | 1-4 小时 |
| 规则冲突 | 审计治理规则链，修复冲突 | 2-8 小时 |
| 外部输入偏移 | 检查上游数据源质量 | 1-2 小时 |

## 升级路径

- 持续漂移 > 6 小时：通知治理团队
- 持续漂移 > 24 小时：升级至架构师评估是否需要治理框架更新
- 漂移导致准确率 SLO 违反：按 P0 事件处理

## 验证

```bash
# 确认漂移分数恢复
curl -s http://localhost:8080/metrics | grep governance_drift_score
# 检查准确率 SLO 状态
curl -s http://localhost:8080/api/v1/error-budget/report
```
# Validation Contract: MAREF v0.25.0 m2 - Cross-Agent Threat Defense

## Mission Goal
构建跨Agent威胁防御体系，检测并隔离共享状态污染、消息注入、异常行为和拜占庭节点。

## Behavioral Assertions (m2 Scope)

### A4: 共享状态污染检测
- [ ] **A4.1**: 状态突变率检测
  - 共享状态单变量突变率超过阈值 (Δ > 50%) 触发告警
  - 多变量同时突变 (>3 个/秒) 触发告警
- [ ] **A4.2**: 异常模式检测
  - 未授权 Agent 修改共享状态被检测并拒绝
  - 跨 scope 数据泄漏被检测
- [ ] **A4.3**: 隔离机制
  - 污染 Agent 自动隔离，状态访问被阻断
  - 隔离后生成污染报告

### A5: 消息传递安全扫描
- [ ] **A5.1**: Prompt injection 识别
  - 5类注入向量全部覆盖 (direct_override, boundary_break, sneak_injection, output_injection, encoding_bypass)
  - 检测率 ≥ 95%
- [ ] **A5.2**: 上下文隔离
  - OBSERVATION 通道中的指令型内容被标记
  - 跨 scope 消息传递被审计
- [ ] **A5.3**: 风险评分 (0-100)
  - 低风险 (0-30): 正常消息
  - 中风险 (31-70): 可疑内容，需审计
  - 高风险 (71-100): 恶意内容，自动阻断

### A6: 行为监控 (Emergent Behavior)
- [ ] **A6.1**: 行为基线建模
  - Agent 正常行为模式被记录（操作频率、调用链长度、工具使用分布）
  - 基线更新周期 ≤ 1 小时
- [ ] **A6.2**: 异常检测
  - 偏离基线 3σ 触发异常告警
  - 多Agent协同偏离触发 emergent behavior 告警
- [ ] **A6.3**: 组合风险评估
  - 2+ Agent 同时异常时风险评分倍增
  - 自动触发 CircuitBreaker

### A7: 拜占庭隔离增强
- [ ] **A7.1**: 多维度异常判定
  - 投票不一致性 + 权重异常 + 时间模式分析
  - 误报率 < 5%
- [ ] **A7.2**: 隔离机制
  - 拜占庭节点权重归零并标记
  - 隔离节点无法参与后续共识
- [ ] **A7.3**: 恢复机制
  - 隔离节点可通过人工审查恢复
  - 恢复后权重逐步重建（冷启动）

## Verification Methods
- **单元测试**: pytest，覆盖率 ≥ 90%
- **红蓝对抗**: RedBlueEngine Blue Team 评分 ≥ 70
- **渗透测试**: 12类 AttackCategory 覆盖（复用现有渗透测试套件）
- **集成测试**: S5-S8 联合运行，验证端到端防御链

## Non-Goals (m2)
- 不实现完整的 AI 行为预测模型（仅基线 + 统计异常）
- 不涉及外部威胁情报源集成（复用现有 ThreatIntelligenceEngine）
- 不修改 m1 已完成的信任链基础设施

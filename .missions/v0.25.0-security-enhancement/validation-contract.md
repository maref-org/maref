# Validation Contract: MAREF v0.25.0 Security Enhancement (Pilot)

## Mission Goal
通过 Factory Missions 架构试点，验证独立验证层对 MAREF 安全模块的质量提升效果。
聚焦 S3（零信任网关）的增强实现，验证以下核心假设：
- **假设 H1**: 独立 Validator 能发现 Worker 自测未捕获的缺陷
- **假设 H2**: 状态外化机制能有效隔离上下文污染
- **假设 H3**: 多模型家族验证能捕获单一模型的系统性盲点

## Behavioral Assertions (Pilot Scope: S3)

### A3: 零信任网关
- [ ] **A3.1**: 每次 MCP Tool Call 独立验证 delegation chain hash
  - 无效 hash 返回 403 Forbidden，触发 SecurityEvent
  - 有效 hash 允许调用继续
- [ ] **A3.2**: 委托链深度限制集成
  - 当 delegation chain depth > max_depth (5) 时拒绝调用
  - 返回 DENY 并记录审计日志
- [ ] **A3.3**: 速率限制
  - 每 agent 每 60s 最多 100 次调用
  - 超限返回 429 Too Many Requests
- [ ] **A3.4**: 审计日志
  - 记录所有访问决策（允许/拒绝/降级）
  - 包含：timestamp, actor, action, resource, result, risk_score, chain_hash
- [ ] **A3.5**: 跨域调用增强检测
  - STRICT 策略域向 PERMISSIVE 策略域调用时 risk_score ≥ 0.6
  - 触发 BoundaryEvent + 审计日志

## Verification Methods (Pilot)
- **单元测试**: pytest，覆盖率 ≥ 90%
- **集成测试**: MCPSecurityGate + DelegationChain + TrustBoundaryManager 联合测试
- **独立验证**: Validator (不同模型家族) 黑盒测试
- **对比基线**: Worker 自测发现问题数 vs. Validator 发现问题数

## Pilot Success Criteria
1. Validator 发现 ≥ 2 个 Worker 自测未发现的问题
2. Token 消耗 < $50 (Pilot 阶段)
3. 耗时 < 3 天
4. 代码覆盖率 ≥ 90%

## Non-Goals (Pilot)
- 不实现完整的 TLA+ 形式化验证（留到 m4）
- 不实现完整的 RedBlueEngine 200轮对抗（仅预验证）
- 不涉及 A2A 协议（留到 m3）
- 不涉及合规模块（留到 m5）

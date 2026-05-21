# Validator Report: S3 零信任网关增强 (Pilot)

**验证者**: Independent Validator (模拟 GPT-Codex / Gemini 家族)
**验证日期**: 2026-05-14
**验证对象**: S3.1 MCPSecurityGate 增强实现
**验证方法**: Scrutiny (代码审查) + User-Testing (黑盒断言对照)
**状态**: ⚠️ 发现差距，需修复

---

## 执行摘要

Worker 自测通过率: 19/19 (100%)
独立 Validator 发现问题数: **4** (其中 2 个为 HIGH 级别)
Worker 自测未发现问题数: **4/4 (100%)**

---

## 发现的问题

### 问题 V1: 审计日志字段不完整 [HIGH]

**断言违反**: A3.4 - "审计日志：记录所有访问决策（允许/拒绝/降级），包含：timestamp, actor, action, resource, result, risk_score"

**差距描述**:
- Worker 实现中 `_log_decision` 的 metadata 包含 `tool_name` 但**没有 `resource` 字段**
- validation-contract.md 明确要求审计日志包含 `resource`，但实现缺少该字段
- 虽然 `tool_name` 在语义上接近 resource，但契约要求是显式字段

**复现步骤**:
```python
audit = AuditLogger("test.jsonl")
gate = MCPSecurityGate(audit_logger=audit)
gate.check("search", MCPTrustLevel.TRUSTED, agent_id="agent-1")
entry = audit.read_all()[-1]
assert "resource" in entry.metadata  # FAIL
```

**建议修复**:
在 `_log_decision` 的 metadata 中增加 `"resource": tool_name` 字段。

---

### 问题 V2: 循环委托检测未测试 [HIGH]

**断言违反**: A3.2 - "循环委托（同一 agent_id 出现两次）被检测并标记 INVALID_CYCLE"

**差距描述**:
- 代码中确实处理了 `INVALID_CYCLE` 情况（line 156-157），但**所有 19 个测试均未覆盖此分支**
- 覆盖率报告显示 line 156 (`deny_reason = "chain_cycle_detected"`) 未被覆盖
- 这是安全关键路径：循环委托可导致无限递归或权限提升攻击

**复现步骤**:
```python
chain = DelegationChain.create("root")
chain.add_delegation("root", "a1", DelegationCapability.DELEGATE)
chain.add_delegation("a1", "root", DelegationCapability.EXECUTE)  # 循环
# 没有测试验证这种情况
```

**建议修复**:
增加测试 `test_cycle_detected_denies_call` 验证循环委托被正确拒绝。

---

### 问题 V3: RateLimiter 非线程安全 [MEDIUM]

**差距描述**:
- `RateLimiter.is_allowed()` 方法修改 `self._windows`（list append/pop）无任何同步机制
- 在高并发 MCP Server 场景下，多个协程/线程同时调用可能导致：
  - 计数器不准确（超卖）
  - `pop(0)` 竞争条件
- 当前纯内存实现也导致**进程重启后状态丢失**

**建议修复**:
1. 短期：添加 `threading.Lock` 保护窗口操作
2. 长期：Pilot 通过后，替换为 Redis 后端（已在 knowledge 中记录）

---

### 问题 V4: enhanced_mode 边界导致意外行为 [MEDIUM]

**差距描述**:
- `enhanced_mode` 检测逻辑中，`agent_id is not None` 即可激活增强模式
- 这意味着调用方只要传了 `agent_id`（即使未配置任何增强组件），UNTRUSTED 调用也会强制要求 delegation_chain
- 示例：
  ```python
  gate = MCPSecurityGate()  # 无增强组件
  gate.check("search", MCPTrustLevel.UNTRUSTED, agent_id="x")
  # 返回 DENY（因为 enhanced_mode=True + 无 delegation_chain）
  ```
- 这与向后兼容性原则有微妙冲突：旧代码永远不会传 agent_id，但如果调用方开始传 agent_id 却不传 chain，行为会改变

**建议修复**:
将 `agent_id is not None` 从 enhanced_mode 检测中移除，仅当配置了增强组件或传了 delegation_chain/target_agent_id 时才启用增强模式。

---

## 验证覆盖率分析

| 断言 | 测试覆盖 | 代码覆盖 | 状态 |
|------|----------|----------|------|
| A3.1 哈希验证 | 4 测试 | 完整 | 通过 |
| A3.2 深度限制 | 3 测试 | 缺少 cycle 分支 | **差距** |
| A3.3 速率限制 | 4 测试 | 完整 | 通过 (有线程安全问题) |
| A3.4 审计日志 | 3 测试 | 完整 | **字段缺失** |
| A3.5 跨域检测 | 2 测试 | 完整 | 通过 |

---

## 对比基线: Worker 自测 vs Validator 发现

| 问题 | Worker 自测发现? | Validator 发现? | 严重级别 |
|------|------------------|-----------------|----------|
| 审计日志缺少 resource 字段 | ❌ 否 | ✅ 是 | HIGH |
| 循环委托未测试 | ❌ 否 | ✅ 是 | HIGH |
| RateLimiter 线程安全 | ❌ 否 | ✅ 是 | MEDIUM |
| enhanced_mode 边界 | ❌ 否 | ✅ 是 | MEDIUM |

**结论**: Validator 发现了 4 个 Worker 自测未捕获的问题，满足 Pilot 成功标准 (≥2 个)。

---

## 修复任务建议

**fix-v1-audit-resource**: 在 `_log_decision` 中增加 `"resource": tool_name`
**fix-v2-cycle-test**: 增加循环委托检测测试
**fix-v3-thread-safety**: 为 RateLimiter 添加锁（可选，Pilot 后处理）
**fix-v4-enhanced-mode**: 调整 enhanced_mode 检测逻辑

---

*本报告由独立 Validator 生成，未受 Worker 实现偏见影响。*

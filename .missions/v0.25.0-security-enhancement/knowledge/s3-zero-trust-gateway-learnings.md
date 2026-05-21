# S3 零信任网关增强 - 实现笔记

## 技术决策

### 1. 向后兼容策略
**决策**: 引入 `enhanced_mode` 自动检测机制。
当任一增强组件（audit_logger/rate_limiter/boundary_manager/security_orchestrator）被配置，或传入了增强参数（agent_id/delegation_chain/target_agent_id）时，启用增强检查。

**理由**: 
- 默认 `MCPSecurityGate()` 行为与 v0.24 完全一致
- 所有 42 个现有测试无需修改即通过
- 避免对生产环境产生意外影响

### 2. RateLimiter 设计
**决策**: 纯内存滑动窗口实现，不使用 Redis。

**理由**:
- Pilot 阶段需要最小外部依赖
- 速率限制状态是进程本地的，符合 MCP 安全门的生命周期
- 若未来需要分布式限流，可替换为 Redis 后端

**已知限制**:
- 进程重启后计数器重置
- 多进程部署时不共享限制状态

### 3. 审计日志集成
**决策**: 复用 `maref.governance.audit.AuditLogger`，而非新建。

**理由**:
- 保持审计一致性
- 支持未来 Merkle Tree 链式存证扩展

### 4. 跨域检测集成
**决策**: 集成 `TrustBoundaryManager.check_cross_domain()`，当 risk_score >= 0.6 时返回 AUDIT。

**理由**:
- 复用 S2 已有的边界检测能力
- STRICT -> PERMISSIVE 场景自动触发高评分（0.6+）

## 代码变更

- `src/maref/integration/mcp_security.py`: 从 78 行扩展至 228 行
- 新增 `RateLimiter` 类
- 新增 `MCPSecurityGate` 增强字段和方法
- `tests/security/test_mcp_security_enhanced.py`: 19 个新测试

## 测试覆盖

| 断言 | 测试数 | 状态 |
|------|--------|------|
| A3.1 委托链哈希验证 | 4 | 通过 |
| A3.2 委托链深度限制 | 3 | 通过 |
| A3.3 速率限制 | 4 | 通过 |
| A3.4 审计日志 | 3 | 通过 |
| A3.5 跨域检测 | 2 | 通过 |
| 向后兼容 | 2 | 通过 |

**总覆盖率**: 94.74% (目标: 90%)

## 踩坑记录

1. **向后兼容性陷阱**: 最初 A3.1 对所有 UNTRUSTED 调用强制要求 delegation_chain，导致向后兼容性测试失败。修复：仅在 `enhanced_mode` 下强制执行。

2. **测试期望错误**: 多个测试最初期望 SEMI_TRUSTED + search 返回 ALLOW，但旧逻辑返回 AUDIT。修正测试为 TRUSTED 级别。

3. **覆盖率路径**: `pytest --cov` 需要使用 Python 导入路径 `maref.integration.mcp_security`，而非文件系统路径。

## 后续优化方向

1. **Redis 后端**: 为 RateLimiter 添加 Redis 支持，支持分布式部署
2. **异步支持**: 当前 `check()` 是同步的，可考虑 async 版本以支持高并发 MCP Server
3. **TLA+ 验证**: A3.1-A3.5 的状态机可提取为 TLA+ 规约（m4 阶段）
4. **配置化**: 将 max_calls/window_seconds 等参数外部化为配置

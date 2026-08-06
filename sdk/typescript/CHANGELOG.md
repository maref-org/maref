# @maref-org/sdk changelog

## 0.2.0 (2026-07-18)

- **发布**: `@maref-org/sdk` 已发布至 npm（因 `@maref` scope 被占用改用 `@maref-org`）
- **新增**: `checkBeforeWrite()` — 写入前治理检查，sidecar 不可达时 fail-closed
- **新增**: `checkBeforeExecute()` — 执行前治理检查，sidecar 不可达时 fail-closed
- **新增**: `reportAction()` — 操作审计上报（best-effort）
- **新增**: `getPhaseGate()` — 阶段门状态查询
- **新增**: `requestHITL()` — 人工决策请求
- **新增**: `createMAREFClient()` — 便捷工厂函数
- **测试**: 28 个单元测试覆盖正常路径 + fail-closed + 错误处理
- **Meta**: 完善 package.json 的 repository/bugs/homepage 字段
- **NPM**: 令牌已存入 GitHub Secrets（NPM_TOKEN，已废弃 revoke）

## 0.1.0 (2026-07-13)

- 初始版本: 只读查询接口（getGovernanceStatus / getAgentTrustScore / listAgents / subscribeAuditLog）

## 0.1.0 (2026-07-13)

- 初始版本: 只读查询接口（getGovernanceStatus / getAgentTrustScore / listAgents / subscribeAuditLog）

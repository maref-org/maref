# MAREF ×《人工智能安全治理框架 3.0》映射矩阵

> 本文件由 `src/maref/compliance/cac/framework_3_0.py::render_markdown()` 自动生成，请勿手工编辑。
> 依据：TC260, 2026-09, 附件2 智能体风险管理框架　|　总条目：42　|　完全覆盖：40/42

## 覆盖统计

| 状态 | 数量 |
|---|---|
| 已覆盖 | 40 |
| 部分覆盖 | 2 |
| 缺失 | 0 |

| 防范措施（附件2 二） | 已覆盖 | 部分覆盖 | 缺失 |
|---|---|---|---|
| 1.风险预防前置 | 7 | 0 | 0 |
| 2.身份与权限管理 | 7 | 0 | 0 |
| 3.加强人工审批 | 5 | 0 | 0 |
| 4.供应链与工具管理 | 6 | 0 | 0 |
| 5.运行时动态管理 | 5 | 0 | 0 |
| 6.持续监测与审计 | 8 | 0 | 0 |
| 7.停用安全管理 | 2 | 2 | 0 |

## 逐条映射

### 1.风险预防前置

| 条款 | 框架要求 | MAREF 实现 | 模块 · 符号 | 状态 |
|---|---|---|---|---|
| 附件2 二.1(1) | 安全需求确认：明确应用场景、可访问资源和禁止性行为，制定安全风险台账 | 任务前置检查 + 风险授权检查（fail-closed） | `maref.governance.task_preflight.TaskPreflight` | 已覆盖 |
| 附件2 二.1(2) | 安全风险分级：按客体类别、影响程度、范围和可恢复性划分风险级别 | 动作风险分类器 + 风险阈值判定 | `maref.governance.risk_classifier.RiskAssessment` | 已覆盖 |
| 附件2 二.1(2) | 风险分级方法论（跨域对照） | EU AI Act 风险管理生命周期（识别/评估/缓解/应用） | `maref.compliance.eu_ai_act_v2.risk_management.RiskManagementSystem` | 已覆盖 |
| 附件2 二.1(2) | 风险五级显式化（低/一般/较大/重大/特别重大）+ 四维度（客体类别/影响程度/范围/可恢复性） | 框架3.0 分级适配层（现有四挡权威分级 → 五级映射 + 四维度补齐 + 处置流程绑定） | `maref.compliance.cac.risk_grading.grade_action` | 已覆盖 |
| 附件2 二.1(3) | 安全控制策略：制定动态安全控制策略与应急响应流程 | 辖区监管策略映射（动作 × 辖区 → 处置策略） | `maref.compliance.regulatory_policy_mapper.RegulatoryPolicyMapper` | 已覆盖 |
| 附件2 二.1(3) | 部署环境安全基线（安全能力摸底） | PERCV 多维安全基线扫描 | `maref.compliance.security_baseline.run_scan` | 已覆盖 |
| 附件2 二.1(4) | 安全机制确认：保留版本发布与回退记录 | 治理状态机快照/恢复 + 迁移回滚点 | `maref.governance.state_machine.GovernanceStateMachine` | 已覆盖 |

### 2.身份与权限管理

| 条款 | 框架要求 | MAREF 实现 | 模块 · 符号 | 状态 |
|---|---|---|---|---|
| 附件2 二.2(1) | 唯一身份标识：禁止智能体应用实例间共享身份标识 | Agent DID 注册表（register/resolve/revoke/deactivate） | `maref.identity.did_registry.DIDRegistry` | 已覆盖 |
| 附件2 二.2(1) | 身份鉴别：鉴别用户、智能体、工具及外部服务身份 | Agent 身份统一门面（签发/验证/撤销）+ 握手挑战 | `maref.identity.agent_identity_service.AgentIdentityService` | 已覆盖 |
| 附件2 二.2(1) | 身份鉴别握手（访问主体身份可信） | ATP 适配器身份验证与挑战生成 | `maref.security.agent_identity.ATPAdapter` | 已覆盖 |
| 附件2 二.2(1) | 国密身份证书与跨系统身份互认（鼓励采用国密算法） | SM2 身份证书（ACPs CAI）签发/验签 + SM3 公钥指纹互认 + DID 绑定；国家 CA 对接为预留接口（未联调） | `maref.identity.sm2_certificate.issue_certificate` | 已覆盖 |
| 附件2 二.2(2) | 最小权限：仅为智能体授予执行当前任务所必需的最小权限 | 信任边界管理器（check / check_no_raise，禁止越权提权） | `maref.governance.trust_boundary.TrustBoundaryManager` | 已覆盖 |
| 附件2 二.2(2) | 零信任：Agent 间消息边界与上下文隔离 | 零信任校验器 + 上下文隔离 + Agent 边界 | `maref.recursive.zero_trust.ZeroTrustValidator` | 已覆盖 |
| 附件2 二.2(3) | 凭证动态管理：任务终止或停用后立即撤销对应凭证 | 凭证管理器（轮换/撤销/过期检查）+ 密钥轮换策略 | `maref.identity.credential_manager.CredentialManager` | 已覆盖 |

### 3.加强人工审批

| 条款 | 框架要求 | MAREF 实现 | 模块 · 符号 | 状态 |
|---|---|---|---|---|
| 附件2 二.3(2) | 在关键决策节点设置强制人工审批 | 人工决策 API（请求决策/提交响应）+ 高风险操作审批引擎 | `maref.human.decision_api.HumanDecisionAPI` | 已覆盖 |
| 附件2 二.3(1)(2) | 高风险操作转交用户接管、中低风险需授权 | 审批引擎（预测 + 首次使用强制审批 + 超策略风险拦截） | `maref.opc_integration.approval.engine.ApprovalEngine` | 已覆盖（依赖闭源模块） |
| 附件2 二.3(2) | 出网/敏感动作的人工确认节点 | 出网消息门禁（HITLRequiredError）+ 底线预检 HITL 确认 | `maref.governance.governance_baseline_gate.GovernanceBaselineGate` | 已覆盖 |
| 附件2 二.3(4) | 审批系统异常/用户无响应时默认拒绝操作执行（fail-closed） | 安全门 v2（block/is_blocked，审批异常默认拒绝） | `maref.recursive.safety_gate_v2.SafetyGateV2` | 已覆盖 |
| 附件2 二.3(3) | 采用防篡改、可校验方式保存人工审批日志（审批人身份绑定） | 审批台账（链式哈希 + SM2/Ed25519 签名 + Merkle 离线证明 + 审批人身份绑定 + 高风险 fail-closed 阻断） | `maref.human.approval_ledger.ApprovalLedger` | 已覆盖 |

### 4.供应链与工具管理

| 条款 | 框架要求 | MAREF 实现 | 模块 · 符号 | 状态 |
|---|---|---|---|---|
| 附件2 二.4 | 工具/依赖元数据与版本清单 | SBOM 生成器（项目依赖清单） | `maref.supply_chain.sbom_generator.SBOMGenerator` | 已覆盖 |
| 附件2 二.4(1) | 工具调用前校验来源、版本、元数据 | 供应链信任校验器 | `maref.supply_chain.trust_verifier.SupplyChainVerifier` | 已覆盖 |
| 附件2 二.4(1) | 技能/工具清单登记与校验 | 技能注册表 + 清单校验 | `maref.marketplace.registry.SkillRegistry` | 已覆盖 |
| 附件2 二.4(1) | 不调用公开已知恶意工具、阻断越权调用 | MCP 安全门（安全裁决 + 越权拦截） | `maref.integration.mcp_security.MCPSecurityGate` | 已覆盖 |
| 附件2 二.4(3) | 工具异常检测 | 工具沙箱参数/环境校验 + 行为异常监测 | `maref.security.tool_sandbox.ToolSandbox` | 已覆盖 |
| 附件2 二.4(4) | 漏洞追踪与供应链风险持续处置 | 漏洞扫描器（SBOM 扫描 + 漏洞库） | `maref.supply_chain.vulnerability_scanner.VulnerabilityScanner` | 已覆盖 |

### 5.运行时动态管理

| 条款 | 框架要求 | MAREF 实现 | 模块 · 符号 | 状态 |
|---|---|---|---|---|
| 附件2 二.5(1) | 输入管理控制：校验来源可信度、多层检测拦截点 | 输入净化器 + 隐蔽字符/隐写检测 | `maref.security.sanitizer.Sanitizer` | 已覆盖 |
| 附件2 二.5(5) | 自主执行控制：异常循环/目标偏移时暂停、终止或转人工 | 中断协议（签发中断/向 Agent 传播）+ 质量门强制终止/隔离/限流 | `maref.human.interrupt_protocol.InterruptProtocol` | 已覆盖 |
| 附件2 二.5(5) | 治理级紧急停止 | 治理状态机 force_halt / force_stabilize | `maref.governance.state_machine.GovernanceStateMachine` | 已覆盖 |
| 附件2 二.5(5) | 运行时熔断（连续失败自动暂停） | 熔断器 + 预测性熔断（提前制动） | `maref.governance.circuit_breaker.CircuitBreaker` | 已覆盖 |
| 附件2 二.5(6) | 运行环境隔离 | WASM 沙箱执行器（资源限制 + EIVL 验证）+ 进程沙箱 | `maref.eivl.wasm_sandbox.WasmSandboxExecutor` | 已覆盖 |

### 6.持续监测与审计

| 条款 | 框架要求 | MAREF 实现 | 模块 · 符号 | 状态 |
|---|---|---|---|---|
| 附件2 二.6 | 全链路安全监测（行为可感知、可追溯、可审计） | 安全大屏 + 异常阻断编排 | `maref.monitoring.safety_dashboard.SafetyDashboard` | 已覆盖 |
| 附件2 二.6(1) | 异常阻断（实时监控 + 介入阻断） | 安全编排器（剧本化自动响应） | `maref.monitoring.security_orchestrator.SecurityOrchestrator` | 已覆盖 |
| 附件2 二.6 | 行为记录可追溯、可审计（链式防篡改） | 审计日志（chain_hash + Ed25519 签名）+ Merkle 完整性证明 | `maref.eivl.merkle_auditor.MerkleAuditor` | 已覆盖 |
| 附件2 二.6 | 跨组织审计可交叉验证 | 联邦审计日志 + 联邦 Merkle 聚合 | `maref.eivl.federated_audit_log.FederatedAuditLog` | 已覆盖 |
| 附件2 二.6(5) | 沙箱环境验证（安全属性形式证明） | 安全属性证明器 + TLA+ 不变量校验 | `maref.security.security_proofs.SecurityPropertyProver` | 已覆盖 |
| 附件2 二.6(6) | 常态化红队安全测试 | 红蓝对抗引擎 | `maref.redblue.red_blue_engine.RedBlueEngine` | 已覆盖 |
| 附件2 二.6(7) | 应急处置预案（不同等级事件处置流程） | 告警管理器（多渠道）+ 检疫/取证快照 | `maref.recursive.alert_manager.AlertManager` | 已覆盖（依赖闭源模块） |
| 附件2 二.6(8) | 重大变更安全验证（框架/工具/权限/策略变更回归） | 宪法守卫（红线变更拦截）+ 安全门自审 | `maref.evolution.constitution_guard.ConstitutionGuard` | 已覆盖 |

### 7.停用安全管理

| 条款 | 框架要求 | MAREF 实现 | 模块 · 符号 | 状态 |
|---|---|---|---|---|
| 附件2 二.7(1) | 下线全面关停（终止主程序/后台服务/配套进程） | Decommissioner 编排：Agent24 状态机置 TERMINATING + 治理级 force_halt（OS 进程/端口核验待补） | `maref.lifecycle.decommission.Decommissioner` | 部分覆盖 |
| 附件2 二.7(2) | 撤销第三方应用授权、禁用/撤销服务账号与访问权限 | DID 生命周期撤销 + 可用凭证撤销 + 身份服务吊销 | `maref.identity.did_registry.DIDRegistry` | 已覆盖 |
| 附件2 二.7(3) | 数据留存处置：按需备份或清理运行期数据 | Decommissioner 备份步（复制必要数据到归档）+ 记忆管理器 purge，逐项核验 | `maref.lifecycle.decommission.Decommissioner` | 已覆盖 |
| 附件2 二.7 | 一站式停用编排（关停核验 + 端口/网络核验 + 授权撤销 + 备份 + 残留清理） | Decommissioner 六步幂等编排（状态/停机/凭证/授权/备份/清理+核验，断点恢复）；端口/网络核验待补 | `maref.lifecycle.decommission.Decommissioner` | 部分覆盖 |

## 校验

```
python3 -m maref.compliance.cac.framework_3_0 verify
```


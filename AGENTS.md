# Agent Operating Manual: MAREF v0.30.0-GA

> **上位法**: 本文件受 [Athena 系统宪法 v1.4](/Volumes/1TB-M2/Athena知识库/OPC工作区/2-战略/战略+宪法/03-Athena系统宪法-v1.4.md) 约束。冲突时以宪法为准。
> **同步方向**: A → B 单向（宪法第二条）。本仓库是 Track B 发布源，由 openclaw/public/ 经叙事转化后同步。

## Project Overview
- **名称**: MAREF (Multi-Agent Recursive Evolution Framework)
- **版本**: v0.30.0-GA
- **定位**: Agent 治理操作系统 (Agent Governance OS)
- **技术栈**: Python 3.10+ / FastAPI / Electron / React 19+TypeScript / TLA+
- **代码风格**: PEP 8 + ruff + mypy strict mode
- **安全级别**: 最高（不可降级安全断言）
- **开源协议**: Apache-2.0

## Architecture

### 概念模型：六层治理架构
```
天极 (Heaven) → 人极 (Human) → 地极 (Earth) → 经卦 (Hexagram) → 别卦 (Trigram) → 爻变 (Mutation)
```
六层是**概念语义层**，描述 Agent 治理从顶层宪法到微观变异的降维路径。

### 运行时模型：八卦信任状态机
代码中六层概念落地为**八卦治理系统** (`recursive/eight_trigrams_governance.py:EightTrigramsGovernance`)：
```
乾(QIAN) → 坤(KUN) → 震(ZHEN) → 巽(XUN) → 坎(KAN) → 离(LI) → 艮(GEN) → 兑(DUI)
```
八卦是 Agent 的 8 种信任状态，基于 Gray Code (hamming distance=1) 进行状态转换，确保每次信任变化只改变一个维度。

**六层→八卦映射**:
| 六层 | 八卦状态 | 代码锚点 |
|------|---------|---------|
| 天极 (宪法/元规则) | 乾(QIAN) 天 — 最高信任 | `meta_agent_closure.py`, `meta_governance.py` |
| 人极 (人类审批) | 离(LI) 火 — HITL/HOTL/HATL | `human/decision_api.py`, `human/interrupt_protocol.py` |
| 地极 (安全边界) | 坤(KUN) 地 — 零信任底座 | `zero_trust.py`, `safety_gate_v2.py`, `blast_radius.py` |
| 经卦 (角色编排) | 震(ZHEN)/巽(XUN) — 动态组合 | `role_composer.py:HexagramWorkflow`, `role_lifecycle.py` |
| 别卦 (能力契约) | 坎(KAN)/艮(GEN) — 约束止行 | `capability_contracts.py`, `permission_matrix.py` |
| 爻变 (自我演化) | 兑(DUI) 泽 — 变异创新 | `self_executor.py`, `evolution_dsl.py`, `creative_generator.py` |

### 执行层：五大运行时架构

```
┌──────────────────────────────────────────────────┐
│ 元层 (Meta): meta_agent_closure, meta_governance   │
│   自引用闭环 · 安全熔断 · 宪法红线验证              │
├──────────────────────────────────────────────────┤
│ 治理层 (Governance): EightTrigrams, FourPhase,     │
│   RuleFreezeZone, ConstitutionalRedLine            │
│   信任状态机 · 四阶段违规处理 · 规则冻结            │
├──────────────────────────────────────────────────┤
│ 编排层 (Orchestration): Self-*(8), RoleComposer,   │
│   CarbonSiliconSymbiosis, SagaOrchestrator          │
│   自演进 · 角色工作流 · 碳硅共生 · 分布式事务       │
├──────────────────────────────────────────────────┤
│ 执行层 (Execution): Agent(9), Skill(4),             │
│   Federation(3), Hook(4), Swarm, DecisionMarket     │
│   多Agent调度 · 技能市场 · 联邦共识 · 钩子拦截      │
├──────────────────────────────────────────────────┤
│ 基础设施 (Infra): Audit(10), Trust(3), Safety(5),   │
│   Memory(2), Knowledge(4), Cost, TLA+              │
│   审计可观测 · 信任评分 · 安全防线 · 形式验证       │
└──────────────────────────────────────────────────┘
```

## Repository Structure

```
openclaw/
├── src/
│   ├── maref/                     # Core governance framework (40+ modules)
│   ├── maref_lite/                # CLI entry points
│   ├── sidecar/                   # Observation sidecar + MCP bridge
│   ├── drift_guard/               # Distribution shift detection
│   ├── formal/                    # TLA+ formal specifications (5 .tla files)
│   ├── skills/                    # Agent skills module
│   └── research/                  # Research module
├── external/                      # External repo integration adapters
├── gui/                           # Electron + React GUI (maref-desktop)
├── tests/                         # Test suites
├── .missions/                     # Factory Missions workspace
├── vault/                         # Knowledge vault (signals, kdps, patterns)
├── knowledge_base/                # Implementation notes
├── scripts/                       # Build and automation scripts
└── k8s/                           # Kubernetes deployment configs
```

## Module Catalog: src/maref/

### 元层 (Meta Layer) — 2 文件

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 元代理闭包 | `recursive/meta_agent_closure.py` | `MetaAgentClosure`, `AdversarialAuditor`, `CombinatorialRiskAnalyzer` | 自引用安全闭环，覆盖所有 pairwise 交互的组合风险分析，不变量证明 |
| 元治理 | `recursive/meta_governance.py` | `MetaGovernance`, `MetaCircuitBreaker`, `TimelineTracker` | 跨层熔断器，上下文分层状态追踪，安全自审计 |

### 治理层 (Governance Layer) — 10 文件

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 八卦治理 | `recursive/eight_trigrams_governance.py` | `EightTrigramsGovernance`, `TrigramsGovernance(Enum)` | 8 状态信任机 (乾→兑)，Gray Code 转换，Lyapunov 稳定性 |
| 四阶段治理 | `recursive/four_phase_governance.py` | `FourPhaseGovernance`, `GovernancePhase` | 违规处理四阶段：警告→制裁→隔离→恢复 |
| 规则冻结区 | `recursive/rule_freeze_zone.py` | `RuleFreezeZone` | 宪法红线修改阻隔，模块级写保护 |
| 零信任验证 | `recursive/zero_trust.py` | `ZeroTrustValidator`, `ConstitutionalRedLine`, `ContextIsolation` | 消息注入检测、上下文隔离、前置/后置条件验证、红线检查 |
| 安全门控 v2 | `recursive/safety_gate_v2.py` | `SafetyGateV2`, `CreativeSafetyGate` | 所有 Agent 行动的安全准入，非修复操作过滤 |
| 爆炸半径控制 | `recursive/blast_radius.py` | `BlastRadiusController`, `ThreatAssessment` | 核心模块移除检测，渐进弱化检测，变更威胁评估 |
| 权限矩阵 | `recursive/permission_matrix.py` | `PermissionMatrix`, `PermissionScope` | Agent 操作许可矩阵，作用域隔离 |
| 宪法红线 | `recursive/zero_trust.py` | `ConstitutionalRedLine` | 不可修改的治理原语 |
| HITL v2 | `recursive/hitl_v2.py` | `EscalationProposal`, `DeadlineNegotiator` | 人工升级提案，采样策略配置 |
| 元认知 | `recursive/metacognition.py` | `SelfLimitationAwareness`, `ConfidenceCalibrator`, `ContextManager` | Agent 自我能力边界感知，置信度校准，上下文隔离管理 |

### 人机协同层 (Human Layer) — 4 文件

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 决策 API | `human/decision_api.py` | `HumanDecisionAPI`, `DecisionMode`, `DecisionRequest/Response` | HITL/HOTL/HATL 三种模式的决策接口 |
| 规则引擎 | `human/rule_engine.py` | `CollaborationRuleEngine`, `CollaborationRule`, `RuleCondition` | 人机协同规则的条件-动作匹配 |
| 中断协议 | `human/interrupt_protocol.py` | `InterruptProtocol`, `InterruptSignal`, `InterruptType` | Agent 行动的人工中断和暂停机制 |
| 碳硅共生 | `recursive/carbon_silicon_symbiosis.py` | `CarbonSiliconSymbiosis`, `WorkflowStage`, `TaskAllocation` | 人机工作流：人类确认→Agent 执行→Agent 自审→人类抽检 |

### 编排层 (Orchestration Layer) — 20 文件

#### Self-* 自演进体系 (8 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 自架构 | `recursive/self_architect.py` | `SelfArchitect`, `ArchitectureProposal` | 架构快照、低覆盖率分析、瓶颈检测、重构提案 |
| 自诊断 | `recursive/self_diagnostician.py` | `SelfDiagnostician`, `DiagnosisReport` | 系统健康诊断、全维度快照 |
| 自执行 | `recursive/self_executor.py` | `SelfExecutor`, `ASTSandbox`, `AtomicDeployer` | 代码生成→AST 验证→安全检查→部署→验证→回滚 |
| 自修复 | `recursive/self_healer.py` | `SelfHealer`, `HealAction`, `HealingRecord` | 分区恢复、故障策略执行 |
| 自知 | `recursive/self_knowledge.py` | `SelfKnowledge` | 代码库/测试的结构化知识提取 |
| 自观察 | `recursive/self_observer.py` | `SelfObserver` | 代码库变更观察、测试成功率追踪 |
| 自优化 | `recursive/self_optimizer.py` | `SelfOptimizer`, `OptimizationCycle` | 变异→沙箱测试→采纳/回退，饱和检测 |
| 版本管理 | `recursive/self_version.py` | `SelfVersionManager`, `VersionPinner` | 依赖版本锁定、API 漂移检测、兼容矩阵 |

#### 角色编排 (3 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 角色编排器 | `recursive/role_composer.py` | `HexagramWorkflow`, `RoleComposer` | 六爻角色工作流组装和验证 |
| 角色生命周期 | `recursive/role_lifecycle.py` | `RoleLifecycle`, `RolePhase` | 角色 promote/deprecate/revoke 状态机 |
| 角色注册 | `recursive/role_registry.py` | `RoleRegistry`, `PluginRole` | 角色注册，按八卦原型映射能力 |

#### 规划与分解 (3 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 形式规划器 | `recursive/formal_planner.py` | `ForwardChainingPlanner`, `CostBasedPlanner` | PDDL 规划 + 成本约束 |
| 任务分解 | `recursive/task_decomposer.py` | `TaskDecomposer`, `TaskDAG` | DAG 分解 + 能力分配验证 |
| 混合分解 | `recursive/hybrid_decomposer.py` | `HybridDecomposer` | LLM 分解 + 回退规则分解 |

#### Saga 事务 + 编排性能 (2 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| Saga 编排 | `recursive/saga_orchestrator.py` | `SagaOrchestrator`, `Saga`, `CompensationDecision` | 分布式事务补偿，并行步骤执行 |
| 编排性能 | `recursive/orchestration_perf.py` | `BackpressureConfig`, `FrequencyMatcher`, `RetryPolicy` | 背压控制、自适应频率、重试策略 |

### 执行层 (Execution Layer) — 30 文件

#### 多 Agent 系统 (9 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 24 状态机 | `recursive/agent_24_state_machine.py` | `Agent24StateMachine`, `AgentStateV3`, `JointStateMachine` | 64 状态 Gray Code FSM，hamming distance=1 转换 |
| Agent 分发 | `recursive/agent_dispatcher.py` | `AgentDispatcher`, `ConcurrentOrchestrator` | 按能力匹配分发，并发编排 |
| Agent 交接 | `recursive/agent_handoff.py` | `AgentHandoffProtocol`, `HandoffRequest/Result` | Agent 间任务交接协议，交接链验证 |
| Agent 健康 | `recursive/agent_health.py` | `AgentHealthMonitor`, `AgentLoadSnapshot` | 负载比率监控，Agent 注册 |
| Agent 经济 | `recursive/agent_economy.py` | `AgentEconomy`, `AgentWallet` | Token 经济：存/取/转账/交易，全经济周期 |
| 信用评级 | `recursive/agent_credit_rating.py` | `AgentCreditRatingSystem`, `CreditRating` | 多维度评分，等级升降，同行评价 |
| Agent 市场 | `recursive/agent_marketplace.py` | `AgentMarketplace`, `CapabilityListing`, `TradeProposal` | 能力发现、挂牌、交易、争议处理 |
| 发现协商 | `recursive/agent_discovery_negotiation.py` | `AgentDiscovery`, `AgentNegotiator` | Agent 间自动发现和截止期限协商 |
| 签名卡片 | `recursive/signed_agent_cards.py` | `SignedAgentCard`, `AgentCardSigner` | Agent 身份卡片签名、验证、吊销 |

#### 技能系统 (4 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 技能模式 | `recursive/skill_schema.py` | `MarefSkill`, `HexagramTrigger`, `ContextActivation` | 技能数据结构，八卦触发条件，MCP/A2A 互操作 |
| 技能加载 | `recursive/skill_loader.py` | `SkillLoader` | 多目录加载，优先级合并，依赖解析 |
| 技能执行 | `recursive/skill_executor.py` | `SkillExecutor` | 输入/输出验证，安全执行 |
| 技能触发 | `recursive/skill_trigger.py` | `SkillTrigger` | 上下文匹配，八卦状态转换验证 |

#### 联邦与分布式 (3 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 联邦协调 | `recursive/federation.py` | `FederationCoordinator`, `FederatedTrustModel` | 跨框架 Agent 联邦，Gossip 传播，信任对比 |
| 分布式 BFT | `recursive/distributed_bft.py` | `DistributedBFT`, `BFTNode`, `ConsensusProposal` | 拜占庭容错共识：提议→投票→提交，分区恢复 |
| 分布式 CRDT | `recursive/distributed_crdt.py` | `DistributedCRDT`, `CRDTNode` | 无冲突复制数据类型，最终一致性验证 |

#### 钩子系统 (4 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 钩子链 | `recursive/hook_chain.py` | `HookChain`, `ChainReactionBreaker` | 事件链式反应检测和熔断 |
| 钩子注册 | `recursive/hook_registry.py` | `HookRegistry`, `HookExecutionStack` | 处理器注册/执行/订阅，判决流水线 |
| 钩子模板 | `recursive/hook_templates.py` | `HookTemplateLibrary` | 预定义治理钩子模板库 |
| 钩子主题 | `recursive/hook_topics.py` | `MarefTopic` | 标准治理事件主题常量 |

#### 技能市场层 (4 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 技能注册 | `marketplace/registry.py` | `SkillRegistry`, `SkillManifest`, `SkillValidationResult` | 技能发布、验证、状态管理 |
| 语义匹配 | `marketplace/semantic_matcher.py` | `SemanticMatcher`, `MatchScore` | 需求到技能的语义匹配评分 |
| 版本协商 | `marketplace/version_negotiator.py` | `VersionNegotiator`, `Compatibility(Enum)` | API 版本兼容性协商 |
| 声誉追踪 | `marketplace/reputation.py` | `ReputationTracker`, `ReputationRecord` | 技能提供方声誉评分和衰减 |

#### 其他执行层模块

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 群体智能 | `recursive/stigmergy_swarm.py` | `StigmergySwarm`, `Pheromone`, `EmergenceResult` | 信息素驱动群体协作，涌现行为检测 |
| 决策市场 | `recursive/decision_market.py` | `DecisionMarket`, `MarketConsensusResult` | 预测市场式治理决策，质押奖励分配 |
| 能力契约 | `recursive/capability_contracts.py` | `CapabilityRegistry`, `CompositeContract` | Agent 能力形式化契约，组合验证 |
| 演化 DSL | `recursive/evolution_dsl.py` | `EvolutionDSL`, `EvolutionRule`, `EvolutionDecision` | Agent 行为演化规则 DSL，安全检查和回滚 |
| 持续优化 | `recursive/continuous_optimizer.py` | `ContinuousOptimizer`, `CostBasedPlanner` | 成本驱动优化提案，趋势预测 |
| 创意生成 | `recursive/creative_generator.py` | `CreativeGenerator`, `InnovationProposal` | 代码创新提案：重构/测试/新功能 |
| 复杂度预算 | `recursive/complexity_budget.py` | `ArchitectureComplexityBudget`, `ComplexityAssessment` | 模块耦合度量，Pareto 最优边界，全局复杂度报告 |
| 跨系统适配 | `recursive/cross_system_adapter.py` | `CrossSystemAdapter`, `AdaptationProfile` | 环境检测和自动配置适配 |
| 实例克隆 | `recursive/instance_cloner.py` | `MAREFInstanceCloner`, `CloneLineage` | 知识图谱+经验池快照克隆，参数注入差异化 |
| 实时迁移 | `recursive/live_migration.py` | `LiveMigration`, `VersionCompatibilityMatrix` | 零停机版本迁移，回滚点，兼容性验证 |

### 基础设施层 (Infrastructure Layer) — 35 文件

#### 审计与可观测性 (15 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 审计模式 | `recursive/audit_schema.py` | `AuditEntry`, `AuditReport`, `AuditReader/Writer`, `CrossLayerAuditEntry` | 非计划审计调度，跨层审计条目，多范围审计 |
| 统一审计 | `recursive/unified_audit.py` | `UnifiedAuditStore`, `UnifiedAuditRecord` | JSONL 格式统一审计存储，按层/事件/轮次查询 |
| 可观测性 | `recursive/observability.py` | `StructuredLogger`, `RecursiveTracer`, `RuntimeInstrumentor` | 递归 Span 追踪，运行时调用记录，多层级注入 |
| OTEL 仪表盘 | `recursive/otel_dashboard.py` | `MetricsDashboard` | OpenTelemetry 指标仪表盘构建 |
| 覆盖率追踪 | `recursive/coverage_tracker.py` | `CoverageTracker`, `CoverageSnapshot` | 模块级覆盖率追踪，低覆盖模块识别 |
| 完整性基线 | `recursive/integrity_baseline.py` | `IntegrityBaseline`, `IntegrityRecord` | 文件完整性注册和验证，不变量检查 |
| 准入测试 | `recursive/admission_testing.py` | `AdmissionGate`, `AdmissionRunner` | 新 Agent 准入检查，准入历史追踪 |
| 仪表盘 v3 | `recursive/dashboard_v3.py` | `DashboardV3`, `ProcessReplay` | 面板管理，事件推送，进程回放 |
| 收敛仪表盘 | `recursive/convergence_dashboard.py` | `ConvergenceDashboard`, `ConvergenceSnapshot` | Agent 信任收敛曲线，多曲线对比 |
| 关联引擎 | `recursive/correlation_engine.py` | `CorrelationEngine`, `CorrelationLink` | Span↔Audit↔Experience 三维关联追踪 |
| MCP 治理 | `integration/mcp_governance.py` | 策略决策树 + 断路器 + HMAC 审计 | MCP 协议层的治理拦截 |
| 审计日志 | `integration/audit_logger.py` | `AuditLogger` | HMAC-SHA256 防篡改审计 |
| HITL 桥接 | `integration/hitl.py`, `integration/hitl_api.py` | HITL 审批流水线 | REST API + MCP 双通道人工审批 |
| A2A 桥接 | `integration/a2a_bridge.py` | Agent-to-Agent 协议 | 跨 Agent 通信 |
| 观测桥接 | `observation/otel_bridge.py` | `OTelBridge` | OpenTelemetry 观测数据桥接 |

#### 信任体系 (5 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 信任引擎 v2 | `recursive/trust_engine_v2.py` | `TrustEngineV2`, `TrustEstablishment` | 多因子信任评分、冲突仲裁、自动适应 |
| 信任校准 | `recursive/trust_v2.py` | `GoodhartDetection`, `UncertaintyQuantification`, `ConfidenceCalibrator` | Goodhart 定律检测，不确定性量化，校准曲线 |
| 可靠性矩阵 | `recursive/reliability_matrix.py` | `ReliabilityMatrix`, `DimensionScore` | 多维度可靠性评分，Pareto 前沿计算 |
| 身份信任 | `identity/trust_engine.py` | `TrustEngine`, `TrustScore` | 基于 DID 和凭证的 Agent 信任 |
| 身份注册 | `identity/did_registry.py`, `identity/credential.py` | `DIDRegistry`, `CredentialStore` | DID:MAREF 注册，W3C 可验证凭证 |

#### 安全防线 (7 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 信任边界 | `security/trust_boundary/` | `TrustBoundaryManager` | 跨域调用授权 (AGENTS.md 边界规则) |
| 安全装饰器 | `security/decorators.py` | `@security_critical` | 安全关键函数标记和审计钩子 |
| 安全证明 | `security/security_proofs.py` | Merkle 完整性证明 | 审计链完整性验证 |
| 密钥存储 | `security/keyring_store.py` | `KeyringStore` | macOS Keychain 密钥管理 |
| 消毒器 | `security/sanitizer.py` | `Sanitizer` | 输入验证 + 输出编码 |
| 红蓝对抗 | `redblue/red_blue_engine.py` | `RedBlueEngine`, `AttackExecutor` | 攻击模拟→检测→缓解→恢复→自适应 |
| 密码学 | `crypto/sm2.py`, `sm3.py`, `sm4.py`, `sm4_gcm.py`, `aia_adapter.py` | SM2/3/4-GCM + CAI 证书 | 国密全算法 + AI 身份证书 |

#### 合规引擎 (9 文件)

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 合规注册 | `compliance/registry.py` | `ComplianceRegistry`, `ComplianceEngine` | GDPR/SOC2/FedRAMP/CCPA/等保/HIPAA/PCI-DSS |
| 合规监控 | `compliance/compliance_monitor.py` | `ComplianceMonitor` | 持续合规快照、告警、趋势 |
| 数据主权 | `compliance/data_sovereignty.py` | `DataSovereigntyManager` | 五眼联盟/GDPR/中国数据安全法跨境传输 |
| EU AI Act | `compliance/eu_ai_act.py` | `EUAIComplianceEngine` | 高风险检查表、人工监督、透明文档 |
| 五眼联盟 | `compliance/five_eyes.py` | `FiveEyesMapper` | ISM/DSM/TSA/CSEC/GCSB/NZISM 控制项 |
| HIPAA | `compliance/hipaa/` | `HIPAAComplianceEngine` | PHI 分类、BAA 验证、泄露评估 |
| PCI-DSS | `compliance/pci_dss/` | `PCIComplianceEngine` | CDE 范围、SAQ 生成、ROC 摘要 |
| 报告生成 | `compliance/report_generator.py` | `ReportGenerator` | 多格式合规报告 (MD/HTML/JSON) |
| 供应链 | `supply_chain/` | 依赖扫描 | versions.json + hash 验证 |

#### 其他基础设施

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| 记忆三层 | `memory/memory_manager.py` | `WorkingMemoryStore`, `EpisodicMemoryStore`, `SemanticMemoryStore`, `MemoryManager` | 热/温/冷三层架构 + 用户隔离 + 衰减归档 |
| 记忆温控 | `recursive/memory_three_temperature.py` | `MemoryThreeTemperature`, `MemoryHealthScore` | 自动平衡、晋升/降级、健康评分 |
| 经验池 | `recursive/experience_pool.py` | `ExperiencePool`, `ExperienceEntry` | 上下文查询、相似搜索、衰减、命中率 |
| 运行时 KG | `recursive/runtime_kg.py` | `RuntimeKG`, `RuntimeKGNode`, `RuntimeKGRelation` | 代码知识图谱，热点路径/瓶颈/错误传播查询 |
| 本体漂移 | `recursive/ontology_drift.py` | `OntologyDriftDetector`, `DriftReport` | 概念漂移、指标漂移、模型漂移、模式演化检测 |
| 模式对齐 | `recursive/schema_aligner.py` | `SchemaAligner`, `SchemaRegistry` | 跨版本模式转换，前向/后向兼容 |
| 代码解析 | `recursive/code_parser.py` | `CodeParser`, `ASTValidationResult` | AST 架构提取、模块层级、未用导入检测 |
| 时间感知 | `recursive/time_awareness.py` | `TimeContext`, `DeadlineNegotiator`, `TimeoutController` | 并发时间线、截止期限协商、上下文衰减监控 |
| 成本追踪 | `recursive/cost_tracker.py` | `CostTracker`, `BudgetGuard`, `GasMeter` | Token/计算成本追踪，预算分配/消费/预测 |
| 韧性评估 | `recursive/resilience_v2.py`, `recursive/chaos_resilience.py`, `recursive/chaos_injector.py` | `ResilienceEvaluatorV2`, `ChaosInjector` | 韧性评分、降级计划、混沌注入 |
| TLA+ 验证 | `recursive/tla_replay.py` | `TLAReplayValidator`, `TLAInvariant` | 不变量验证、拜占庭容错证明 |
| 形式规约 | `formal/MAREF_Consensus.tla` 等 5 个 .tla | TLA+ 规约 | 共识、集成测试、桌面联合、Lite 模型 |

### 独立模块

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| GaaS | `gaas/` (10 文件) | `GovernanceRouter`, `CircuitBreakerPool`, `HITLService`, `BillingService`, `TenantManager` | 多租户治理即服务：ALLOW/DENY/ASK_USER/DEFER 判定流水线，FastAPI REST + API Key |
| 演化引擎 | `evolution/` (6 文件) | `RecursiveEvolutionEngine`, `AcceptanceCriteria`, `EvolutionMetrics` | 指标驱动递归演化管道：生成→评估→改进→重复 |
| EIVL | `eivl/` (3 文件) | `MerkleAuditor`, `WasmSandboxExecutor`, `EIVLVerifier` | Merkle 审计链 + WASM 沙箱隔离执行，不可篡改验证 |
| 认证 | `certification.py` | Agent 认证 | 发布前合规检查清单 |
| 代理卡片 | `agent_card_config.py` | Agent Card 配置 | Agent 能力描述的标准化格式 |

## Boundaries
- **禁止**: 修改 `.missions/v0.25.0-security-enhancement/validation-contract.md`（仅 Orchestrator 可修改）
- **禁止**: 跨特征深度导入（每个特征目录独立）
- **禁止**: 绕过 TrustBoundaryManager 进行跨域调用
- **禁止**: 在生产代码中硬编码密钥/凭证
- **端口范围**: 3000-3010（GUI 开发），8000（Sidecar），9000-9010（测试）

## Coding Conventions
- 所有 API 路由使用 `/api/v1/` 前缀
- 数据库操作必须通过标准接口，禁止裸 SQL
- 错误处理统一使用异常类，HTTP 状态码标准化
- 所有异步函数必须包裹 `try/except`
- 安全相关函数必须声明 `@security_critical` 装饰器 (定义: `security/decorators.py`)
- 所有加密操作使用 `cryptography` 或 `hashlib` 库，禁止自行实现密码学原语
- Python: ruff + mypy strict mode
- TypeScript: ESLint + TypeScript strict mode

## Handoff Discipline
每个特征完成后必须:
1. 运行完整测试套件（`pytest tests/ -v --cov`）
2. 覆盖率 ≥ 该特征的 `test_coverage_threshold`
3. 提交 Git commit，消息格式: `feat(module): description`
4. 更新 `.missions/v0.25.0-security-enhancement/features.json`
5. 在 `knowledge_base/` 留下实现笔记

## Security-Specific Rules
- 所有输入必须验证（`pydantic` + 自定义校验器）→ `security/sanitizer.py`
- 所有输出必须编码（防止 XSS/注入）→ `security/sanitizer.py`
- 凭证/密钥必须使用 macOS Keychain 或环境变量 → `security/keyring_store.py`
- 审计日志必须包含 HMAC-SHA256 签名 → `integration/audit_logger.py`
- 跨域调用必须通过 TrustBoundaryManager 授权 → `security/trust_boundary/`
- Electron: hardenedRuntime=true, asar=true, entitlements only JIT+network+files

## Testing Commands
```bash
# Python unit tests
pytest tests/ -v --cov=src/maref --cov-report=term-missing

# Security-specific tests
pytest tests/security/ -v

# Desktop tests
pytest tests/desktop/ -v

# Type checking
mypy src/

# Linting
ruff check src/

# GUI
cd gui && pnpm lint && pnpm build
```

## Build Commands
```bash
# Python package
pip install -e ".[dev]"

# Electron (GUI)
cd gui && pnpm install && pnpm electron:dev

# Build verification
bash scripts/verify_electron_build.sh

# Docker
docker build -t maref:latest .

# Kubernetes
kubectl apply -f k8s/production/
```

## Key Design Decisions
| Decision | Rationale |
|----------|-----------|
| 64-state Gray Code FSM | Hamming distance=1 transitions guarantee stability |
| Eight Trigrams Trust States | 八卦(qian→dui) 8 状态信任机，驱动所有 Agent 治理决策 |
| TLA+ formal verification | Prove correctness before implementation (5 .tla specs) |
| Factory Missions O/W/V | Eliminates self-verification blind spots |
| MCP + A2A dual protocol | Maximum ecosystem interoperability |
| Electron + React GUI | Cross-platform desktop agent workstation |
| Sidecar MCP bridge | Standardized Agent observation protocol |
| AuditLogger HMAC | Tamper-evident audit trail (ISO 27001 C.5.33) |
| Self-* Pipeline | 自架构→自诊断→自执行→自修复→自优化的闭环演进 |

## Knowledge Vault
- **路径**: `vault/`
- **格式**: YAML with frontmatter
- **Signals**: 12 market/technology signals (S-20260511-001 ~ 012)
- **KDPs**: 9 key decision points (K-20260511-001 ~ 009)
- **Patterns**: 1 competitive positioning pattern

## Mission Workspace
- **路径**: `.missions/`
- **v0.25**: Security Enhancement — 22/22 completed, 330 tests passed
- **v0.26**: GA Release — completed
- **v0.27**: Execution Layer — completed
- **v0.28**: Operational Layer: HITL & Orchestration — completed
- **v0.30**: GA Release (current) — 人机协同+记忆+技能市场+国密+白皮书

## Quick Reference
- MAREF Lite CLI: `maref-lite --help`
- PERCV CLI: `maref percv --help`
- Sidecar health: `GET /api/health`
- MCP endpoint: `POST /api/mcp`
- MCP well-known: `GET /api/mcp/.well-known`
- GaaS API: `POST /api/v1/govern`

## External Integration
| 仓库 | 版本 | 集成模式 | 适配器 |
|------|------|----------|--------|
| maref | v0.30.0-GA | import_path | `external/maref_30/adapters/` |
| mas-ts | v0.1.0 | subprocess_cli | `external/mas_ts/adapters/` |
| percv | v0.6.0 | import_path | `external/percv/adapters/` |
| skillos | AGPL-3.0 | process_isolation | `external/skillos/adapters/` (骨架) |

## Open Source Execution Norm
> **上位法**: 本文件受 [MAREF 开源执行规范 v1.0](file:///Volumes/1TB-M2/Athena知识库/执行项目/2026/003-open%20human（碳硅基共生）/018-v0.2.0-活跃/021-架构设计/MAREF递归演进框架/04-MAREF%20开源模式/开源执行文档/01-开源执行规范-v1.0.md) 约束。
> **宪法对齐**: Athena 系统宪法 v1.4 第十条（外部 Code Agent 治理）· 第十一条（跨仓库治理）
> **同步方向**: A → B 单向（宪法第二条）。本仓库是 Track B 发布源。

- 当前阶段: S0
- 执行规范: `04-MAREF 开源模式/开源执行文档/01-开源执行规范-v1.0.md`
- 执行计划: `04-MAREF 开源模式/开源执行文档/05-四流并行执行计划-v1.0.md`
- 执行日志: `04-MAREF 开源模式/开源执行文档/执行日志/`

# v0.51.0 版本迭代规划：企业价值闭环补强（Enterprise Value Closure）

> **编制**: 2026-08-04 · **版本**: v1.0
> **上位依据**: [艾瑞《中国企业级 AI Agent 发展洞察报告(2026)》分析](../research/ai-agent-enterprise-2026-ireport-analysis.md)
> **设计草案**: 本文件（由报告差距分析直接推导）
> **前置完成**: v0.50.0-dev（双协议治理 + 联邦治理 + 自我演化）
> **版本基线**: v0.50.0
> **状态**: 规划中（未开工）
> **配套 Mission**: `.missions/v0.51.0-enterprise-value/mission.json`

---

## 1. 版本主题：从"防止 Agent 做错事"到"证明 Agent 创造了多少业务价值"

艾瑞报告核心判断：2026 年竞争焦点已从模型能力转向**知识资产与业务价值**。
MAREF 治理骨架（安全门控、信任分级、循环控制、审计链）已超出多数企业需求，
但"企业价值闭环"存在四个系统性缺口。本版本聚焦飞轮两端与三重失控硬伤。

| 维度 | 现状（v0.50.0） | v0.51.0 目标 | 核心缺口 |
|------|-----------------|-------------|---------|
| 飞轮数据端 | 无企业数据接入治理 | **DataCatalog + Lineage + Schema 校验** | 无数据目录/血缘/质量抽象 |
| 飞轮价值端 | 全库无 ROI 模型 | **ValueTrackingEngine + ROI 报告** | 计量=token/成本，结果不参与结算 |
| 数据泄露失控 | 9 级分类与正则消毒割裂 | **消毒分级贯通 + 敏感数据血缘** | 无分类→脱敏→还原链路 |
| 人对 AI 失控 | rationale 自由文本无 schema | **结构化推理链（DecisionExplainer）** | 无端到端可解释产物 |
| AI 自身失控 | 仅代码正则幻觉检测 | **通用幻觉/RAG grounding 校验** | 无 grounding 忠实度评分 |

---

## 2. 交付清单（按 ROI 排序）

### P0-A 飞轮数据端：企业数据接入治理

| # | 交付物 | 技术方案 | 落点 | 优先级 |
|---|--------|---------|------|--------|
| A1 | **DataCatalog** | 企业数据源注册：`DataSource`（名称/类型/owner/分类分级/敏感标签/schema 指纹），支持登记/检索/变更通知 | 新 `src/maref/data/catalog.py` | P0 |
| A2 | **LineageTracker** | 数据血缘追踪：`LineageNode`（上游/下游/transform）有向图，`trace_downstream(data_asset)` 扩散面分析 | 新 `src/maref/data/lineage.py` | P0 |
| A3 | **SchemaValidator** | 接入 schema 校验：字段级类型/必填/枚举约束 + 变更检测（`detect_schema_drift`），对接 `recursive/schema_aligner.py` | 新 `src/maref/data/schema_validator.py` | P0 |
| A4 | **DataQualityScorer** | 数据质量评分（完整性/唯一性/时效性/一致性），入飞轮作为知识沉淀的前置门槛 | 新 `src/maref/data/quality.py` | P1 |
| A5 | **drift_guard 业务数据通道** | `DriftDetectionPipeline` 增加业务数据漂移检测（特征分布 KL/Hellinger），与模型权重漂移共用 `DriftAction` 处置语义 | 改 `src/drift_guard/pipeline.py` | P1 |

### P0-B 飞轮价值端：ROI / 业务价值度量

| # | 交付物 | 技术方案 | 落点 | 优先级 |
|---|--------|---------|------|--------|
| B1 | **ValueMetric 模型** | `ValueMetric`（业务指标：节省小时/流程缩短/错误减少/达标率），带 `baseline/current/delta`，每任务可附加 | 新 `src/maref/value/metrics.py` | P0 |
| B2 | **ValueTrackingEngine** | 业务结果追踪：任务完成 → 结果价值采集 → 按 agent/团队/组织聚合；与审计链联动（HMAC 签名） | 新 `src/maref/value/tracking.py` | P0 |
| B3 | **TaskMetric 结果质量字段** | `federation/metering.py:TaskMetric` 增加 `outcome_quality`（达标率/产出可用性评分），`ContributionScore` 结算公式纳入结果质量权重 | 改 `src/maref/federation/metering.py` | P0 |
| B4 | **ROI 报告类型** | `report_generator.py` 新增 `value_report`：成本节省/人效提升/流程缩短，面向 CEO/CFO；从运行时动态采集（非静态模板） | 改 `src/maref/compliance/report_generator.py` | P1 |
| B5 | **RaaS 结算闭环** | `federation/settlement.py` 支持按结果质量分成（result-based pricing），支撑"结果即服务" | 改 `src/maref/federation/settlement.py` | P2 |

### P0-C 数据泄露失控：消毒分级贯通 + 敏感数据血缘

| # | 交付物 | 技术方案 | 落点 | 优先级 |
|---|--------|---------|------|--------|
| C1 | **字段级分类元数据** | `DataCategory`（data_sovereignty.py）挂到 `DataSource.schema` 字段级，形成"字段→分类→消毒规则"映射 | 改 `src/maref/data/catalog.py` + `compliance/data_sovereignty.py` | P0 |
| C2 | **消毒规则贯通** | `sanitizer.py` 增加分类感知消毒：按字段分类选择规则（HEALTH→健康数据规则、FINANCIAL→金融规则），还原经授权恢复 | 改 `src/maref/security/sanitizer.py` | P0 |
| C3 | **SensitiveDataLineage** | 敏感数据跨域流动血缘：传播链/扩散面/去向下游追踪，与 `TrustBoundaryManager` 联动审计，越界触发熔断 | 新 `src/maref/data/sensitive_lineage.py` | P0 |
| C4 | **跨域数据流拦截** | `TrustBoundaryManager.check` 增加敏感数据分类级校验（C1 分类→目标域白名单） | 改 `src/maref/security/trust_boundary/` | P1 |

### P1-D 人对 AI 失控：结构化推理链解释

| # | 交付物 | 技术方案 | 落点 | 优先级 |
|---|--------|---------|------|--------|
| D1 | **DecisionExplainer** | 结构化 rationale schema：前提/推理步/置信度/备选方案/不确定性来源；强制所有决策产出（`ExplainerRequiredError`） | 新 `src/maref/governance/explainer.py` | P1 |
| D2 | **HITL 注入推理链** | `decision_api.py:DecisionContext` 增加 `explanation`，人类审批前必须可见结构化推理链 | 改 `src/maref/human/decision_api.py` | P1 |
| D3 | **置信度挂钩决策** | `metacognition.py:ConfidenceCalibrator` 输出接入 D1，支持查询"该决定为何置信度 0.83" | 改 `src/maref/recursive/metacognition.py` | P2 |

### P1-E AI 自身失控：通用幻觉 / RAG grounding 校验

| # | 交付物 | 技术方案 | 落点 | 优先级 |
|---|--------|---------|------|--------|
| E1 | **GroundingVerifier** | RAG grounding 校验：生成断言 ↔ 检索证据忠实度评分（faithfulness），输出 `GroundingScore` | 新 `src/maref/security/grounding_verifier.py` | P1 |
| E2 | **verification_bridge 第五协议** | `VerificationBridge` 增加协议 E：grounding 忠实度三角验证（断言/证据/来源） | 改 `src/maref/integration/percv/verification_bridge.py` | P1 |
| E3 | **幻觉产出回退** | `self_healer.py:HEALING_STRATEGIES` 增加"幻觉产出回退"策略（重生成/回退上一版本） | 改 `src/maref/recursive/self_healer.py` | P2 |
| E4 | **通用 LLM 文本幻觉检测** | 统一检测器：低置信 + grounding 低于阈值 + 来源不可验证 → 标记 `HALLUCINATION_SUSPECT` | 新 `src/maref/security/hallucination_detector.py` | P2 |

### P2-F 工程化落地（后续版本可选并入）

| # | 交付物 | 技术方案 | 落点 | 优先级 |
|---|--------|---------|------|--------|
| F1 | **DeploymentMaturity（L1-L3）** | 部署成熟度模型：L1 探索(POC 沙箱)/L2 局部(试点域)/L3 深度(核心链路)，由"部署范围×业务结果达成率×信任评分"三维驱动 | 新 `src/maref/value/maturity.py` | P2 |
| F2 | **ProjectStagnationMonitor** | 项目停滞预警：按月/季度窗口统计 commit/任务完成量/里程碑进度下滑，复用 `TrustEngineV2` 时间衰减思路 | 新 `src/maref/observability/stagnation_monitor.py` | P2 |
| F3 | **知识→能力自动转化管线** | 已验证真值（`TruthWriteback`）经信誉门槛 → `SkillRegistry` 注册为 standard skill | 改 `src/maref/knowledge/writeback.py` + `marketplace/registry.py` | P2 |
| F4 | **组织内层级** | `Tenant` 扩展组织树（部门→团队→项目→Agent）+ 部门级 RBAC + 部门合规视图聚合 | 改 `src/maref/gaas/tenant.py` | P2 |
| F5 | **离线/air-gap 治理** | 离线模型策略 + 公网 LLM 调用降级链（复用 `MarefSkill.degradation_chain`） | 改 `k8s/production/configmap.yaml` + `recursive/skill_schema.py` | P2 |

---

## 3. 里程碑

```
v0.51.0-M1  A1-A3(B 数据目录/血缘/schema) + B1-B2(ValueMetric/追踪) 完成
v0.51.0-M2  B3(结果质量参与结算) + C1-C3(分类贯通+敏感血缘) 完成
v0.51.0-M3  D1-D2(推理链+HITL) + E1-E2(grounding) 完成 + 端到端验收 + ruff/mypy
v0.51.0-M4  测试补齐 + 覆盖率 ≥ 门禁 + CHANGELOG + 版本 bump 0.51.0
```

## 4. 验收标准

| 维度 | 验收 |
|------|------|
| 数据接入 | 企业数据源可登记分类分级；`trace_downstream` 能返回扩散面；schema 变更触发告警 |
| 价值度量 | 任务可附加 `ValueMetric`，结算公式含 `outcome_quality`；`value_report` 输出成本节省/人效提升 |
| 数据泄露 | 字段按分类自动消毒，授权可还原；敏感数据跨域越界触发熔断 |
| 可解释性 | 每个决策产出结构化推理链；HITL 审批前展示 explanation |
| 幻觉 | 低忠实度产出标记 `HALLUCINATION_SUSPECT`；第五协议可三角验证 |

## 5. 版本纪律

- 每个 commit 前缀 `feat:`/`fix:`；安全修复不排队
- 每个 M 里程碑跑一次定向测试 + ruff/mypy strict
- 遵循 AGENTS.md：新模块过 phase gate、安全函数声明 `@security_critical`、
  输入 pydantic 校验、审计 HMAC 签名
- 完成状态回写 `docs/research/ai-agent-enterprise-2026-ireport-analysis.md` 第五节（`✅ v0.51.0`）

## 6. 风险与依赖

| 风险 | 缓解 |
|------|------|
| B3 改动结算公式影响联邦既有语义 | 默认 `outcome_quality` 权重为 0（向后兼容），按租户逐步开启 |
| C2 消毒规则贯通影响现有 sanitizer 调用方 | 新增分类感知入口，保留旧 API 兼容层 |
| A5 drift_guard 扩展面大 | 仅加业务数据通道，不改现有模型权重管线 |
| D1 强制解释引入额外 token 成本 | 提供 `EXPLAIN_MODE`（mandatory/lazy/skipped）配置 |

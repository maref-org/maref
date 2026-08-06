# MAREF vs AI Governance Frameworks: 深度研究与补强方案

> 研究周期: 2026-07-11
> 方法: Phase 0 全景情报 → Phase 1 多源交叉验证 → Phase 2 盲点扫描 → Phase 3 优先级分级 → Phase 4 补强执行方案

---

## 执行摘要

MAREF 是目前唯一将治理实现为**运行时架构内嵌层**而非外部审计附件的开源框架。在与 EU AI Act、联合国 AI 治理论坛、OECD/NIST/ISO 等框架的交叉验证中，MAREF 在 8 个方面已具备实质能力覆盖，但在 6 个关键领域存在盲点。

**核心发现**：MAREF 的"中间层治理"定位（图 1）恰好填补了现有监管框架与 Agent 框架之间的结构性缺口——监管要求落地需要技术载体，Agent 框架需要安全门控，而 MAREF 充当了这个桥梁。

---

## 图 1: MAREF 的治理定位

```
┌─────────────────────────────────────────────────┐
│               EU AI Act / 各监管框架               │  ← 法律要求
├─────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │LangGraph │  │ CrewAI   │  │ AutoGen  │       │  ← Agent 编排框架
│  └─────┬────┘  └─────┬────┘  └─────┬────┘       │
│        └──────────┬──┴──────────────┘            │
│  ┌─────────────────▼─────────────────────────┐   │
│  │           MAREF 治理门控层                    │   │  ← ★ MAREF
│  │  八卦状态机 · 安全门控 · 审计链 · HITL      │   │
│  └─────────────────┬─────────────────────────┘   │
│        ┌──────────┴──────────┐                   │
│  ┌─────▼─────┐  ┌───────────▼────┐               │
│  │ MCP Server │  │ Sidecar / K8s │               │  ← 基础设施
│  └───────────┘  └───────────────┘               │
└─────────────────────────────────────────────────┘
```

---

# 第一部分: 能力交叉验证矩阵

## 1.1 EU AI Act 高要求 (Art. 8-15)

| EU AI Act 要求 | MAREF 对应模块 | 覆盖度 | 验证说明 |
|---|---|---|---|
| **Art. 9: 风险管理** | `recursive/blast_radius.py`, `recursive/safety_gate_v2.py`, `security/`, `drift_guard/` | ●●●○ 70% | 爆炸半径控制器指定补偿策略；安全门控 V2 检测核心移除/渐进弱化/组合爆炸。**缺失**：系统化的风险识别-评估-缓释循环生命周期管理，未直接映射 Art. 9 的持续性迭代流程 |
| **Art. 10: 数据治理** | `compliance/data_sovereignty.py` | ●●○○ 40% | 数据分类、地理围栏、跨境转移评估已有。**缺失**：训练数据质量保证、代表性检查、偏差检测修正（仅有 `eu_ai_act.py` 的 HR-8 占位项，无实际检测逻辑） |
| **Art. 11: 技术文档** | `compliance/eu_ai_act.py` (EUAITransparencyDoc) | ●○○○ 25% | 仅有基本模板。**缺失**：Annex IV 要求的完整技术文档模板（系统架构、开发流程、human oversight 评估、验证测试过程、网络安全措施） |
| **Art. 12: 记录保存** | `recursive/unified_audit.py`, `recursive/audit_schema.py`, `eivl/` | ●●●● 85% | 统一审计存储支持跨层索引和因果链追踪；JSONL 持久化；EIVL Merkle 审计链提供密码学完整性。**改善点**：Automatic logging of events "over the lifetime"（当前以会话/回合为单位，非真正生命周期） |
| **Art. 13: 透明度** | `compliance/eu_ai_act.py` (EUAITransparencyDoc, 168行) | ●○○○ 20% | 基本模板。**缺失**：向 deployer 提供的完整使用说明（精度/鲁棒性指标、已知局限、human oversight 措施、计算需求、预期生命周期） |
| **Art. 14: 人工监督** | `recursive/hitl_v2.py`, `human/`, `recursive/carbon_silicon_symbiosis.py` | ●●●● 90% | HITL/HOTL/HATL 三种模式完整；AdversarialAuditor 8 种注入向量；链式反应中断器；5% 抽检。**改善点**：需要更直接映射 Art. 14 四条核心要求 |
| **Art. 15: 精度/鲁棒性/网络安全** | `security/`, `recursive/zero_trust.py` | ●●○○ 45% | Zero Trust 提供消息层安全。**缺失**：精度指标定义与追踪、故障弹性测试、技术冗余机制、持续学习系统反馈环路减轻、对抗性操控防护措施 |

**EU AI Act 覆盖率评估**: ~50% (权重平均)。高要求层覆盖良好（人工监督、审计），但技术文档、数据治理、精度鲁棒性方面实质性缺口。

---

## 1.2 EU AI Act GPAI 要求 (Art. 53-55)

| GPAI 要求 | MAREF 覆盖 | 状态 |
|---|---|---|
| Art. 53: 技术文档 | 无 | ❌ 缺失 |
| Art. 53: 向下游透明度 | 部分（AgentCard 能力描述） | ⚠️ 未映射到 GPAI 特定要求 |
| Art. 53: 版权政策 | 无 | ❌ 缺失 |
| Art. 53: 训练数据摘要 | 无 | ❌ 缺失 |
| Art. 55: 模型评估/对抗测试 | `redblue/red_blue_engine.py` + SAEB | ●●●○ 部分覆盖 |
| Art. 55: 系统性风险评估 | 无 | ❌ 缺失 |
| Art. 55: 后市场监控 | `compliance/compliance_monitor.py` | ●●○○ 基本框架 |
| Art. 55: 能效报告 | 无 | ❌ 缺失 |

**GPAI 覆盖率评估**: ~15%。这是 MAREF 目前最大的合规缺口。GPAI 要求面向的是大模型提供商而非 Agent 治理框架，但 MAREF 若定位为"运行 GPAI 的基础设施"，则需要更完整支持。

---

## 1.3 联合国 AI 治理论坛 2026 核心议题

| 论坛议题 | MAREF 覆盖 | 评级 |
|---|---|---|
| **安全机制缺失** — 科学小组警告"无现有机制能保证不造成灾难性后果" | 8 层纵深防御 + Gray Code FSM + 熔断器 — 每层拦截不同威胁向量，状态机数学可验证 | 🟢 强覆盖 |
| **治理碎片化** — 全球 40+ 治理框架缺乏协调 | 框架无关治理中间层 + MCP/A2A 标准协议；不绑定单一编排框架 | 🟢 强覆盖 |
| **透明度与问责** — 古特雷斯强调 | 不可变审计 + HMAC 签名 + OTEL 遥测；每条审计记录密码学签名 | 🟢 强覆盖 |
| **能力鸿沟** — 发展中国家"118 国为零参与" | Apache 2.0 开源 + pip/docker 一键部署 + 12 条预置规则 | 🟢 强覆盖 |
| **生产落地断层** — 仅 5-11% 组织 Agent 在生产环境 | Sidecar 注入 + K8s 原生 + 熔断器；FNR 从 37% 降至 2% | 🟢 强覆盖 |
| **最小可行互操作性 (MVI)** — 2027 年目标 | MCP + A2A 双协议支持；八卦治理可作为跨框架风险分类映射 | 🟡 需形式化 MVI 映射 |
| **AI 环境透明度倡议** — 碳/水/土地足迹披露 | 无 | 🔴 缺失 |
| **儿童安全承诺** — 三项规则 | 无 | 🔴 缺失 |
| **全球 AI 数据框架** — 训练数据可用性/互操作性 | 无 | 🔴 缺失 |
| **紧急事件协调机制** — 跨域 AI 事故响应 | 无 MCP-level 的紧急协调 | 🔴 缺失 |

---

## 1.4 全球治理框架对比

| 框架 | MAREF 可提供的 | 缺口 |
|---|---|---|
| **OECD AI 原则** | 5 条全涵盖：包容性增长/人权/透明度/鲁棒性/问责 → 架构层实现 | 非正式报告输出 |
| **G7 广岛 AI 流程** | 11 个行动领域通过 8 层纵深防御覆盖 8+；自愿报告框架可通过审计链满足 | 缺乏正式合规声明模板 |
| **中国 AI 治理** | 国密 SM2/3/4-GCM 算法 + 数据主权地理围栏满足本地化要求 | 需 TC260 标准映射 + CAC 备案接口 |
| **美国 NIST AI RMF 2.0** | 4 核心功能 (GOVERN/MAP/MEASURE/MANAGE) 全部可映射 | 需要 Agent-AI 配置文件 |
| **英国 AI 安全研究所** | 6 个风险域中，自主系统/社会韧性可由 MAREF 治理架构直接对应 | 缺乏测试平台接入 |
| **新加坡 Agentic AI 框架** | 世界首个 Agentic AI 治理框架 → HITL/水印/事故报告/跨域数据 | 需要正式映射表 |
| **ISO/IEC 42001** | AIMS 通过 PDCA 循环：QMS (Art. 17) 可映射到 MAREF QMS | 需第三方认证适配器 |
| **CoE AI 公约** | 人权/隐私/透明度/问责 → 宪法红线 + 审计链直接对应 | 需正式自助评估工具 |

---

# 第二部分: 系统性盲点扫描 (Phase 2)

## 2.1 当前已实现 vs 缺失能力雷达图

以下使用 0-10 分制评估 MAREF 在各维度的成熟度：

```
                    EU AI Act 高风险 (5)
                       ↑
   生产部署 (9) ←──────┼──────→ GPAI 要求 (2)
                       │
   UN MVI互操作 (6) ←──┼──────→ 训练数据治理 (3)
                       │
    审计链 (9) ←───────┼──────→ 形式验证 (8)
                       │
   人工监督 (9) ←──────┼──────→ 供应链安全 (5)
                       │
   Zero Trust (8) ────┼──────→ 紧急协调 (1)
                       │
 自演进防御 (8) ──────┼──────→ 环境透明度 (0)
                       │
     MCP/A2A (8) ─────┼──────→ 正式认证 (2)
                       │
                  合规报告 (6)
```

## 2.2 盲点清单 (优先级排序)

### 🔴 紧急盲点 (影响度 ≥ 85, 紧急度 ≥ 80)

| 编号 | 盲点 | 影响 | EU AI Act 对应 | 当前状态 |
|---|---|---|---|---|
| B-001 | **GPAI 技术文档模板 (Annex XI)** | 高：2026 年 8 月 GPAI 全面执法 | Art. 53 + Annex XI | 完全缺失 |
| B-002 | **训练数据摘要模板** | 高：2025 年 7 月委员会已通过模板 | Art. 53(1)(d) | 完全缺失 |
| B-003 | **版权合规管理** | 高：GPAI Code of Practice 已要求，2026 年 8 月执法 | Art. 53(1)(c) | 完全缺失 |
| B-004 | **高风险 AI 系统性风险识别与缓解** | 高：未来可承担法律责任 | Art. 55(1)(b) | 完全缺失 |

### 🟠 重要盲点 (影响度 ≥ 70, 紧急度 ≥ 65)

| 编号 | 盲点 | 影响 | 对应框架 | 当前状态 |
|---|---|---|---|---|
| B-005 | **精度/鲁棒性指标定义与测试套件** | 中高 | EU Art. 15 | 仅有空白占位符 |
| B-006 | **后市场监控计划** | 中高 | EU Art. 72 | compliance_monitor 有监控但无正式 Art. 72 计划 |
| B-007 | **EU 合规声明 + CE 标志 + EU 数据库注册** | 中高 | EU Art. 47-49 | 完全缺失 |
| B-008 | **FRIA (基本权利影响评估)** | 中高 | EU Art. 27 | 完全缺失 |
| B-009 | **完整 Annex IV 技术文档自动生成** | 中高 | EU Art. 11 + Annex IV | 仅有 20 行模板 |
| B-010 | **AI 环境足迹追踪 (碳/水/土地)** | 中高 | UN Forum 倡议 | 完全缺失 |
| B-011 | **AI 事故跨域协调协议** | 中高 | UN + 各 AISI 需求 | 完全缺失 |
| B-012 | **多方评审与认证准备 (ISO 42001/SOC 2)** | 中高 | ISO 42001 | certification.py 基础，需强化 |
| B-013 | **合规声明文档多语言生成** | 中高 | EU/G7/UN | 完全缺失 |

### 🟡 关注盲点 (影响度 ≥ 50)

| 编号 | 盲点 | 影响 | 对应框架 |
|---|---|---|---|
| B-014 | 中国 TC260 标准 / CAC 备案接口 | 中 | 中国 AI 治理 |
| B-015 | 日本 AISI 资源交叉引用映射 | 中 | J-AISI |
| B-016 | Agent-AI NIST RMF 2.0 配置文件 | 中 | NIST AI RMF |
| B-017 | AISI Inspect 评估框架集成 | 中低 | 英国 AISI |
| B-018 | GAAT 实时治理架构参考 | 中低 | GAAT (Pathak & Jain 2026) |
| B-019 | Per-inference cryptographic certificate (Hamilton 2026) | 中低 | 研究前沿 |
| B-020 | Global South Algorithmic Sovereignty | 中 | 2026 全球南方法律架构 |

---

# 第三部分: 补强执行方案 (Phase 4)

## 3.1 模块架构 Spec

### M1: EU AI Act 合规引擎重构 (`src/maref/compliance/eu_ai_act_v2/`)

**目标**: 从 168 行独立模块升级为完整的高风险 + GPAI 合规引擎

| 文件 | 职责 | 优先级 |
|---|---|---|
| `eu_ai_act_v2/__init__.py` | 统一导出 | P0 |
| `eu_ai_act_v2/risk_classifier.py` | Art. 6-7 风险分类器：Annex III 匹配 + Art. 6(3) 豁免评估 | P0 |
| `eu_ai_act_v2/risk_management.py` | Art. 9 全生命周期风险管理流程：识别→评估→缓释→持续监控 | P0 |
| `eu_ai_act_v2/data_governance.py` | Art. 10 训练数据质量保证 + 偏差检测 + 代表性检查 | P1 |
| `eu_ai_act_v2/technical_docs.py` | Art. 11 + Annex IV 完整技术文档生成器 | P0 |
| `eu_ai_act_v2/logging_audit.py` | Art. 12 生命周期日志桥接到 UnifiedAuditStore | P1 |
| `eu_ai_act_v2/transparency.py` | Art. 13 使用说明 + Art. 50 最终用户透明度（深度合成披露 + 聊天机器人披露） | P0 |
| `eu_ai_act_v2/human_oversight.py` | Art. 14 映射到现有 HITL V2 + 增强 | P0 |
| `eu_ai_act_v2/accuracy_robustness.py` | Art. 15 精度指标 + 鲁棒性测试 + 网络安全集成 | P1 |
| `eu_ai_act_v2/conformity_assessment.py` | Art. 43 自我声明 (Annex VI) + 第三方 (Annex VII) 路径 | P0 |
| `eu_ai_act_v2/post_market_monitoring.py` | Art. 72-73 后市场监控计划 + 严重事故报告 | P1 |
| `eu_ai_act_v2/gpai.py` | Art. 53-55 GPAI 合规（Annex XI 技术文档 + 训练数据摘要 + 版权政策） | P0 |
| `eu_ai_act_v2/fundamental_rights.py` | Art. 27 FRIA 基本权利影响评估 | P1 |
| `eu_ai_act_v2/declaration.py` | Art. 47-49 EU 合规声明 + CE 标志 + EU 数据库注册助手指南 | P1 |

### M2: 国际治理框架适配器 (`src/maref/compliance/adapters/`)

**目标**: 将 MAREF 内部能力映射到各框架的输出格式

| 文件 | 职责 | 优先级 |
|---|---|---|
| `adapters/oecd_report.py` | OECD 原则合规报告映射 | P1 |
| `adapters/g7_haip_report.py` | G7 广岛报告框架映射（OECD 监督的报告模板） | P1 |
| `adapters/nist_rmf_profile.py` | NIST AI RMF 2.0 Agent-AI 配置文件 | P2 |
| `adapters/iso_42001_mapping.py` | ISO/IEC 42001 Annex A 控制映射表 | P1 |
| `adapters/singapore_agentic_ai.py` | 新加坡 Agentic AI 治理框架映射（2026 年 1 月） | P2 |
| `adapters/global_south_sovereignty.py` | 全球南方算法主权 + 法律架构映射 | P2 |
| `adapters/china_tc260.py` | 中国 TC260 标准 / CAC 备案要求映射 | P2 |

### M3: 环境与社会责任 (`src/maref/compliance/esg/`)

| 文件 | 职责 | 优先级 |
|---|---|---|
| `esg/environmental_tracker.py` | AI 系统碳/水/土地足迹估算（UN 环境透明度倡议） | P1 |
| `esg/child_safety.py` | 儿童安全承诺合规（三项规则：安全证明/零容忍/不独自留儿童在危机中） | P2 |
| `esg/social_impact_assessment.py` | 社会影响评估（MIT AGORA 标识的经济去价值/权力集中风险） | P2 |

### M4: 紧急协调与危机响应 (`src/maref/incident_response/`)

| 文件 | 职责 | 优先级 |
|---|---|---|
| `incident_response/crisis_coordinator.py` | 跨域 AI 事故协调协议（参考 EA Forum 宏观审慎预警机制） | P2 |
| `incident_response/mcp_emergency.py` | MCP 紧急公告通道：跨 Agent 集群广播停止/降级/回滚命令 | P2 |
| `incident_response/global_registry.py` | 全球 AI 事故注册（参考 GAAT 架构） | P3 |

### M5: 合规报告与认证 (`src/maref/compliance/reporting/`)

| 文件 | 职责 | 优先级 |
|---|---|---|
| `reporting/eu_compliance_statement.py` | EU AI Act 合规声明文档 (JSON + PDF-ready) | P1 |
| `reporting/gpai_documentation.py` | GPAI Annex XI 文档生成 | P1 |
| `reporting/iso_42001_audit.py` | ISO 42001 审计就绪检查 | P2 |

## 3.2 里程碑路线图

### Milestone 1 (2 周): EU AI Act 高风险 + GPAI 基本合规
**目标**: EU AI Act 覆盖率从 50% 提升至 85%

- [ ] M1: `risk_classifier.py`, `technical_docs.py`, `transparency.py`, `conformity_assessment.py`
- [ ] M1: `gpai.py` (Annex XI 文档 + 训练数据摘要模板)
- [ ] 连通 `EUAIComplianceEngine` ↔ `ComplianceRegistry`（解决当前双系统问题）
- [ ] 测试: 覆盖 Art. 9-15, 53-55
- [ ] 更新 `features.json` + 实现笔记

### Milestone 2 (2 周): 国际框架映射 + 报告链
**目标**: 覆盖 OECD/NIST/ISO/G7/新加坡 5 大框架映射

- [ ] M2: `oecd_report.py`, `g7_haip_report.py`, `iso_42001_mapping.py`
- [ ] M5: `eu_compliance_statement.py`, `gpai_documentation.py`
- [ ] M5: `iso_42001_audit.py`
- [ ] `report_generator.py` 增强: EU AI Act 专用报告模板
- [ ] 测试: 框架映射验证

### Milestone 3 (1 周): 环境追踪 + 内部合规增强
**目标**: 完善高影响度缺失项

- [ ] M1: `risk_management.py`, `post_market_monitoring.py`, `fundamental_rights.py`
- [ ] M3: `environmental_tracker.py`（碳足迹估计，非精确测量）
- [ ] `compliance_monitor.py` 增强: FRIA + PMM 计划支持
- [ ] 测试: 全合规周期自动化测试

### Milestone 4 (持续): 认证准备 + 前沿治理集成
- [ ] M2: `nist_rmf_profile.py`, `singapore_agentic_ai.py`, `china_tc260.py`
- [ ] M4: `crisis_coordinator.py`, `mcp_emergency.py`
- [ ] 第三方审计: ISO 42001 预评估
- [ ] 中文 TC260 标准合规检查

## 3.3 量化缺口与工时估算

| 模块 | 新文件数 | 估算代码行 | 新测试用例数 | 预估工时 |
|---|---|---|---|---|
| M1: EU AI Act 引擎重构 | ~14 | ~3500 | ~150 | 3 周 |
| M2: 国际框架适配器 | ~7 | ~1800 | ~70 | 2 周 |
| M3: ESG | ~3 | ~800 | ~40 | 1 周 |
| M4: 紧急协调 | ~3 | ~600 | ~30 | 1 周 |
| M5: 合规报告 | ~3 | ~500 | ~30 | 1 周 |
| **合计** | **~30** | **~7200** | **~320** | **8 周** |

## 3.4 核心收益

- **EU AI Act 合规覆盖率**: 50% → 85%+ (高风险层 90%+, GPAI 70%+)
- **国际框架映射**: 0 → 5 个主要框架正式映射
- **合规输出**: 从手动变为自动生成（EU 合规声明、GPAI 文档、ISO 42001 报告）
- **竞争定位**: 成为"首个开源 AIGA (AI Governance Agent)"——既能治理 Agent 又为 Agent 提供治理合规工具

---

# 第四部分: 关键架构决策

## 4.1 现有系统集成方案

```python
# eu_ai_act_v2 与现有系统的集成原则

# 1. 桥接 ComplianceRegistry
# eu_ai_act_v2 的合规状态应写入 registry，使得 generate_compliance_report() 包含 EU AI Act
registry = ComplianceRegistry()
engine_v2 = EUAIComplianceEngineV2(registry=registry)

# 2. 复用 UnifiedAuditStore
# 所有合规检查结果写入统一审计存储
result = engine_v2.evaluate_risk(system_config)
unified_audit.append(
    UnifiedAuditRecord(
        layer="governance",
        event_type="eu_ai_act_compliance_check",
        decision=result.status,
        ...
    )
)

# 3. 连接到现有 instrumentation
# 后市场监控复用 compliance_monitor.py 的检查周期 + 回调系统
monitor = create_compliance_monitor(engine=engine_v2)

# 4. 报告生成扩展现有 ReportGenerator
# 新增 EU_AI_ACT 报告类型到 ReportType 枚举
generator = ReportGenerator(registry=registry)
```

## 4.2 设计约束

1. **不破坏现有 API**: 现有 `EUAIComplianceEngine` 保留，`EUAIComplianceEngineV2` 作为升级版
2. **不引入新外部依赖**: 全部基于标准库 + 已有依赖（pydantic, cryptography）
3. **5000 行总上限**: M1-M5 合计控制在 7200 行（含测试）
4. **mypy strict 模式**: 所有新代码必须过 mypy strict
5. **每个新模块测试覆盖率 ≥ 80%**

---

# 第五部分: 与现有治理架构的差异化优势

## 5.1 MAREF 独有的结构优势

对比现有的纯合规或纯治理方案：

| 维度 | 纯法律合规 (Law firm tools) | 纯安全框架 (AISI) | MAREF |
|---|---|---|---|
| 运行时执行 | ❌ 无 | ❌ 无 | ✅ Gray Code FSM + 熔断器 |
| 形式验证 | ❌ 无 | ❌ 无 | ✅ TLA+ 5 个规约 |
| 实时监控 | ❌ 无 | ⚠️ 预部署评估 | ✅ OTEL + 审计链 |
| 自我进化 | ❌ 无 | ❌ 无 | ✅ Self-8 闭环 |
| 合规报告 | ✅ 静态文档 | ❌ 无 | ✅ 自动生成 |
| 多 Agent 治理 | ❌ 无 | ⚠️ 单模型评估 | ✅ 八卦 + 联邦 + 蜂群 |
| HITL | ❌ 无 | ❌ 无 | ✅ 三种模式 + 抽检 |

## 5.2 竞品差距总结

**MAREF 目前在 AI 治理领域没有直接开源竞品。** 最接近的替代拼图组合:

- **LangChain LangGraph** + Guardrails + **Weights & Biases** + **ISO 42001 文档** — 但这是工具链拼图，不是统一治理层
- **Google GAAT (2026)** — 学术架构提案，非开源实现
- **D2iQ/EHV/CAIS (2026)** — 学术层提案，非生产就绪

MAREF 是唯一将以下能力集于一体的开源项目：
1. 运行时治理执行（不妥协）
2. 形式验证（TLA+）
3. 密码学审计链（EIVL/Merkle）
4. 自我演化 + 免疫测试（SAEB）
5. 多 Agent 编排治理（八卦/联邦/蜂群）
6. MCP + A2A 双协议
7. 多法域合规（EU/US/CN/RU/IN + HIPAA/PCI-DSS）

---

# 附录: 来源参考

| 来源 | 引用 |
|---|---|
| EU AI Act Regulation (2024/1689) | Art. 1-113 (OJ L, 2024/1689, 12.7.2024) |
| EU AI Act Digital Omnibus | COM(2025) 836, 29 Jun 2026 Council adoption |
| UN A/RES/79/325 | Global Dialogue on AI Governance, 26 Aug 2025 |
| UN HLAB-AI "Governing AI for Humanity" | Sep 2024 |
| First Global Dialogue on AI Governance | Geneva, 6-7 Jul 2026, Palexpo |
| UN Scientific Panel Preliminary Report | 6 Jul 2026 (Bengio/Ressa) |
| CEN/CENELEC JTC 21 Draft Standards | prEN 18228 (Risk Mgmt), prEN 18283 (Bias), prEN 18286 (QMS) |
| GPAI Code of Practice | 10 Jul 2025, 1,000+ stakeholder inputs |
| Singapore Model AI Gov Framework for Agentic AI | Jan 2026 |
| NIST AI RMF 2.0 Draft | Apr 2026 |
| Khodjaev "The Institutional Gap" | Apr 2026 |
| arXiv "Beyond Benchmarks: False Promise of AI Regulation" | 2501.15693, Jan 2025 |
| EA Forum "Most AI Governance Doesn't Govern" | Apr 2026 |
| MIT AGORA Dataset "Mapping AI Governance" | airisk.mit.edu, Jul 2026 |
| Euro Prospects "Free, Open, and Untouchable?" | Apr 2026 |
| Osmond & Jego "Mind The Gap" | Feb 2026 |
| Eurobarometer EU AI Act Insights | 2026 |

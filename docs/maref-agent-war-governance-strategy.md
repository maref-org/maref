# MAREF 在 Agent 大战中的全维度治理能力战略

> **文档状态**: 战略草案 v1.0
> **日期**: 2026-08-01
> **作者**: Frankie + Claude Code（交叉验证）
> **关联**: WAIC 2026 智能体深度盘点 / [STATE.yaml](../STATE.yaml) v14 / 宪法 v1.8
> **后续**: 可实施设计方案见 [2026-08-01-agent-war-governance-design.md](plans/2026-08-01-agent-war-governance-design.md)

---

## 1. 摘要

WAIC 2026 将智能体产业推进到"交付时代"，同时把治理从"附加功能"抬升为**竞争维度**——胜负手从"模型智商"转向"系统工程能力 + 协议话语权 + 治理信任度"。MAREF 恰好卡位在 **Agent × 治理** 的交叉点上，但现状是"单机版治理 OS"，需要完成三个跃迁：

1. **Agent 单体治理**：从"状态机治理" → "分级授权 + 可追责"
2. **多 Agent 联邦治理**：从"编排治理" → "主权联邦治理"
3. **Agent 互联网治理**：从"内网协议" → "开放互操作治理 + 可验证治理证明"

本战略以交叉验证后的真实能力为底，给出差距、路线、优先级与风险。

---

## 2. 背景：WAIC 2026 把治理变成竞争维度

本届大会三大叙事主轴为 **智能体、具身智能、AI 安全治理**。关键信号：

- **讨论重心跃迁**：从"什么是 Agent"转向"部署在哪、成本能否打平、出问题谁负责"
- **架构范式**：单体 Agent → 多 Agent 协作系统（MAS）+ 开放互操作协议
- **协议三层收敛**：MCP 负责"接工具"、A2A 负责"连智能体"、中国提出 ASL（智能体安全可信互联协议）——中西并行
- **治理信号**：薛澜委托代理问题（信息不对称 → 道德风险）、尼兹伯格决策边界（不可挽回的重大决定不应由 AI 独立作出）、Bengio 三项防护原则
- **趋势预判**：记忆原生成为标配、多 Agent 协作渗透率提升、协议治理博弈常态化、安全治理从"原则宣示"走向"强制性合规"

**对 MAREF 的含义**：治理从"合规成本"变成"差异化卖点"与"标准参与门票"。谁能在单 agent 行为可控、联邦可信协作、互联网互操作三个层面同时建立**可验证、可问责、可合规**的治理能力，谁就掌握下一代智能体基础设施的话语权。

---

## 3. 现状能力盘点（交叉验证结论）

> 交叉验证基于源码逐项核实，结论为「已实现 / 部分实现 / 仅命名」。证据表见 §7。

### 3.1 单 Agent 治理层 —— ✅ 已实现，业界领先

| 能力 | 结论 | 证据 |
|------|------|------|
| 10 状态 Gray Code 治理状态机 | 已实现，单比特转移，Hamming 距离=1 | `src/maref/governance/state_machine.py:168`, `constants.py:19` |
| TLA+ 形式化验证 | 已实现，真实规格与不变式 | `src/formal/MAREF_InternetInvariants.tla`, `MAREF_Consensus.tla` |
| 熔断器 + HALT 吸收态 | 已实现 | `governance/circuit_breaker.py` |
| 破坏性命令门 / 预算熔断 | 已实现 | `governance/destructive_gate.py:159`, `budget_breaker.py:44` |
| 三层记忆框架 | 已实现（hot/warm/cold，含衰减归档） | `src/maref/memory/memory_manager.py:117,423` |
| LoRA/ontology 双重漂移检测 | 已实现 | `src/maref/learning/`（README 声明） |

### 3.2 多 Agent 联邦治理层 —— ✅ 底子最强，但缺"治理裁判"

| 能力 | 结论 | 证据 |
|------|------|------|
| 联邦信任引擎（同侪报告 + Sybil 防护 + Byzantine 聚合） | 已实现 | `federation/trust.py:119,288` |
| 联邦共识（法定人数 + 签名投票） | 已实现 | `governance/federated_consensus.py` |
| 联邦 Merkle 审计 + 离线包含性证明 | **已实现，位于 `eivl/` 而非 `governance/`** | `src/maref/eivl/federated_merkle.py:178,275`; `tests/test_federated_merkle.py` |
| 管辖权路由 / 成员 / 政策订阅 | 已实现 | `federation/jurisdiction_router.py:271`, `membership.py`, `policy_subscriber.py` |
| 联邦结算 / 计量账本 | 已实现 | `federation/settlement.py:197`, `metering.py:103` |
| 级联熔断 | 已实现 | `federation/cascade_breaker.py:67` |
| **Agent-as-a-Judge（基于执行轨迹裁决）** | **❌ 仅命名/仿真表决** | `governance/verifier_consensus.py:89`（`bool(item)` 仿真） |

### 3.3 Agent 互联网治理层 —— ✅ 协议在，但实现分裂、身份未成网

| 能力 | 结论 | 证据 |
|------|------|------|
| A2A 网络实现 | 已实现，`A2A_PROTOCOL_VERSION="1.0"` | `src/maref/integration/a2a_server.py:16`, `a2a_types.py:9` |
| MCP 实现 | 已实现 | `src/maref/mcp/router.py:32` |
| A2A↔MCP 协议桥 | **⚠️ 两套独立实现，桥文件未被真实 A2A 层引用** | `protocols/protocol_bridge.py:173`（内存转换）vs `integration/a2a_server.py` |
| DID 身份（解析/文档/公钥） | 部分实现 | `identity/did_registry.py:17,139` |
| DID 版本化撤销 | **❌ 未实现**（`deactivated` 硬编码 False，撤销仅移除注册） | `identity/did_registry.py:178` |
| 跨组织信任桥 / 国密 | 已实现 | `governance/trust_bridge.py`, `identity/aic_adapter.py` |

---

## 4. 战略定位：从"治理 OS"到"治理互联网"

MAREF 的北极星不是"更好用的 agent 框架"，而是成为**智能体互操作时代的治理基础设施**，分三阶段：

```
阶段一（当前）  阶段二             阶段三
治理 OS    →   治理联邦          治理互联网
单系统治理      主权联邦治理        开放互操作治理
(已领先)      (巩固 + 治理裁判)    (标准参与 + 可验证治理证明)
```

每一阶段的"治理可信度"都是可证明的（形式化 + Merkle + 加密身份），这是 LangGraph/CrewAI 等编排框架无法复制的护城河。

---

## 5. 三维度能力跃迁路线

### 5.1 单 Agent 治理：从"状态机"到"分级授权 + 可追责"

WAIC 信号：委托代理问题、决策边界、不可挽回决定不应由 AI 独立作出。

| 缺口 | 建议 | 落点模块 |
|------|------|---------|
| 决策无风险分级 | **决策分级授权（Scope-Bound Authorization）**：动作按可逆性/影响面分级，不可逆类强制 HITL 或多验证者 | `governance/task_preflight.py`、`identity/credential.py` |
| 越权无记录 | 授权范围证书：agent 只能在授权上下文内行动，越界触发 E1006 类错误 | `identity/`、`governance/types.py` |
| 记忆无主权 | 记忆原生配**记忆治理**：跨会话记忆去识别、保留期、遗忘权（对齐个保法/AI Act） | `memory/memory_manager.py` |

### 5.2 多 Agent 联邦：从"编排治理"到"主权联邦治理"

WAIC 信号：AgentTeams 的 Leader-Worker 治理、AgentLoop 的 Agent-as-a-Judge。

| 缺口 | 建议 | 落点模块 |
|------|------|---------|
| **缺治理裁判（最大空白）** | 将 `verifier_consensus` 从仿真表决升级为 **Agent-as-a-Judge**：基于执行轨迹（trace）而非结果做裁决，输出可溯源审计 | `governance/verifier_consensus.py`、新增 `trace` 采集 |
| 只认平级共识 | **治理拓扑感知**：FederatedConsensus 支持 Leader-Worker 混合模式——Worker 快执行，Leader 仲裁，关键决议升级到法定人数投票 | `governance/federated_consensus.py` |
| 联邦自治性需强化 | 强化 `jurisdiction_rules`：成员组织保留自身宪法/策略主权，联邦层只做信任/结算/共识/管辖权路由——"治理联邦"而非"治理集权" | `federation/jurisdiction_rules.py` |

### 5.3 Agent 互联网：从"内网协议"到"开放互操作治理"

WAIC 信号：MCP/A2A/ASL 三层收敛、Agent 互联网化、强制性合规。

| 缺口 | 建议 | 落点模块 |
|------|------|---------|
| 协议桥实现分裂 | **重构协议桥**：统一 `protocol_bridge` 与 `integration/a2a_server` 为单一桥层，消除双实现技术债 | `protocols/protocol_bridge.py` |
| 无中国标准适配 | **预留 ASL 适配器**（智能体安全可信互联协议），协议桥抽象层外挂中国标准 | `protocols/` |
| 身份未成网 | **DID 版本化撤销 + Agent DNS**：DID 解析 → 能力目录 → 可撤销凭证，让 agent 在互联网上可验证身份与权限 | `identity/did_registry.py` |
| 无治理证明 | **可验证治理证明（Verifiable Governance Credential）**：把联邦 Merkle 审计链打包为可离线验证的合规凭证，直接对接监管 | `eivl/federated_merkle.py`（复用）、`governance/` |
| 跨组织责任链 | 协议层内置**责任链**：每次跨组织调用带调用方身份 + 授权范围 + 责任归属 | `protocols/`、`identity/` |

### 5.4 横切：安全治理 —— 从"原则宣示"到"强制合规"适配层

WAIC 预判多个司法辖区将进入强制性行业监管。已有 `compliance/eu_ai_act.py`、`geopolitical_risk.py` 底子，建议加**监管适配层**：同一治理策略按辖区（中国生成式 AI 办法 / 欧盟 AI Act / 全球南方）自动映射强制级别。

---

## 6. 优先级与里程碑（按 ROI 排序）

| 序 | 动作 | 战略价值 | 建议窗口 |
|----|------|---------|---------|
| P0 | 重构协议桥 + 升级 A2A/预留 ASL | 从产品竞争升维到标准竞争（国策方向） | 2026 Q3 |
| P0 | **可验证治理证明**（复用 eivl 联邦 Merkle） | 治理能力外部化，企业级付费抓手 | 2026 Q3 |
| P1 | Agent-as-a-Judge（基于执行轨迹） | 补联邦层最大功能空白 | 2026 Q4 |
| P1 | 决策分级授权 + DID 版本化撤销 | 补齐单体与身份层缺口 | 2026 Q4 |
| P2 | 治理拓扑感知 + 监管适配层 | 巩固领先、应对强制合规 | 2027 Q1 |

**成功标准**：三个维度各完成一次"可验证治理"闭环——单 agent 越权可拦截、联邦争议可裁决可溯源、跨组织调用可证明合规。

---

## 7. 风险与依赖

| 风险 | 说明 | 缓解 |
|------|------|------|
| 标准之争不确定性 | A2A 版本演进快、ASL 是否被业界采纳未知 | 桥层抽象隔离，标准适配器可插拔 |
| Agent-as-a-Judge 成本 | 基于执行轨迹裁决需要 LLM 集成，且需要防"自我裁定"偏置 | 多验证者 + 加权共识（已有 trust.py 底子） |
| 记忆治理的合规复杂度 | 遗忘权/去识别实现复杂，跨辖区规则冲突 | 监管适配层抽象，先做最小合规子集 |
| 与编排框架的关系模糊 | 用户可能混淆 MAREF 与 LangGraph/CrewAI | 强化"治理 OS"心智，输出对照白皮书 |

---

## 8. 附录：交叉验证证据表

| 能力点 | 结论 | 证据（文件:行号） |
|--------|------|------------------|
| A2A 网络实现 | 已实现 | `src/maref/integration/a2a_server.py:16,252`; `a2a_types.py:9`（v1.0） |
| A2A↔MCP 协议桥 | 分裂（内存桥未被真实 A2A 层引用） | `protocols/protocol_bridge.py:173` vs `integration/a2a_server.py` |
| DID 身份 | 部分实现，撤销不完整 | `identity/did_registry.py:17,139,178` |
| 联邦 Merkle 审计 | 已实现（在 eivl/） | `src/maref/eivl/federated_merkle.py:178,275` |
| 三层记忆 | 已实现 | `memory/memory_manager.py:117,423` |
| Agent-as-a-Judge | 仅仿真表决 | `governance/verifier_consensus.py:89` |
| 联邦治理五件套 | 已实现 | `federation/`（trust/settlement/metering/jurisdiction/cascade） |
| 安全治理 | 已实现 | `compliance/eu_ai_act.py:154`, `geopolitical_risk.py:191` |
| TLA+ 规格 | 已实现（不变式 2~6 个/模型） | `src/formal/*.tla`, `gray-code-fsm/*.cfg` |
| 10 态 Gray Code FSM | 已实现 | `governance/state_machine.py:168` |

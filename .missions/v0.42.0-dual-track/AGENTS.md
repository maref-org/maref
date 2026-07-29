# Agent Operating Manual: MAREF v0.42.0 Dual Track

> **上位法**: [Athena 系统宪法 v1.5](https://github.com/maref-org/maref/blob/main/docs/CONSTITUTION.md)。冲突时宪法优先。
> **不修改全局 AGENTS.md**。

## 概要

- **名称**: MAREF Dual Track — EU AI Act Compliance + Federated Governance
- **版本**: v0.42.0-dev
- **定位**: 双轨并进 — P0 合规引擎（抢占 EU AI Act 窗口）+ P1 联邦治理（完成跨组织治理闭环）
- **时间窗口**: EU AI Act GPAI 全面执法 2026 年 8 月（3 周后）

## Track C: EU AI Act Compliance Engine (P0)

### 背景
当前 EU AI Act V2 覆盖率 ~50%，GPAI 要求覆盖率 ~15%。
8 月 GPAI 全面执法——MAREF 可成为首个合规 AI Agent 治理框架。

### 里程碑

| ID | 交付 | 依赖 |
|----|------|------|
| C1 | Art.11 + Annex IV 技术文档自动生成 | TechnicalDocumentation (已存在) |
| C2 | Art.12-14 合规桥接（记录/透明/监督) | record_keeping, transparency, human_oversight (已存在) |
| C3 | GPAI Art.53-55 合规映射 (版权/摘要/安全) | gpai.py (已存在) |
| C4 | EU AI Act 合规声明生成 + CE 标志预检查 | conformity_assessment.py (已存在) |

全部基于已有的 `eu_ai_act_v2/` 15 个模块，只需桥接和自动生成。

### 关键文件
| 组件 | 路径 |
|------|------|
| 合规引擎 V2 | `src/maref/compliance/eu_ai_act_v2/` (15 模块) |
| 合规注册表 | `src/maref/compliance/registry.py` |
| 报告生成器 | `src/maref/compliance/report_generator.py` |

## Track F: Federated Governance (P1)

### 背景
v0.40.0 实现了联邦审计（跨组织 Merkle），v0.42.0 实现联邦治理（跨组织策略/状态同步）。

### 里程碑

| ID | 交付 | 依赖 |
|----|------|------|
| F1 | 跨组织八卦状态同步 | EightTrigramsGovernance |
| F2 | 多法域治理策略路由 FederationPolicyEngine | |
| F3 | 联邦政策推送/订阅机制 | |

### 关键文件
| 组件 | 路径 |
|------|------|
| 八卦治理 | `src/maref/recursive/eight_trigrams_governance.py` |
| 联邦策略 | `src/maref/federation/policy.py` |
| 联邦目录 | `src/maref/federation/catalog.py` |

## 不做清单

- 不做 Skill Marketplace 完整实现（延迟至 v0.43+）
- 不做 Token Economy 持久化（延迟至 v0.43+）
- 不做桌面 Agent 闭环增强（延迟至 v0.43+）
- 不做覆盖率提升（保持诚实 36.1%）

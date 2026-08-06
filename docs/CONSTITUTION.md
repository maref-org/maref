# Athena 系统宪法 v1.5

> **地位**: MAREF 仓库（Track B 发布源）的最高上位法。AGENTS.md、CLAUDE.md、`docs/oss-execution-norm-v1.0.md` 等下位文件均受本宪法约束；冲突时以本宪法为准。
>
> **物理位置**: `docs/CONSTITUTION.md`（本文件）。
>
> **同步方向**: A → B 单向。本仓库是 Track B 发布源，由 Athena 内部部署经叙事转化后同步，不得反向回灌。
>
> **生效日期**: 2026-05-18
>
> **形式化对应**: 宪法红线的形式化不变量见 `src/formal/MAREF_ConstitutionalRedLines.tla`（TLC 模型检查已验证，156 distinct states / 0 errors）。

---

## 第一条 上位法等级

治理依据按下列优先级降序排列，下位文件不得与上位冲突：

1. **Athena 系统宪法 v1.5**（本文件）
2. **MAREF 开源执行规范 v1.0**（`docs/oss-execution-norm-v1.0.md`）
3. **AGENTS.md / CLAUDE.md**（仓库 Agent 操作手册）
4. **MAREF 自有发布门禁**（`docs/release-gate.md`）及各模块规范

任何外部项目（包括同生态的 SkillOS / openclaw / Athena-UI 等）的发布手册、验收标准、规范文档**不得**作为 MAREF 审计或发布决策的依据。仅可作参考资料，并须在本宪法框架内重新编入 MAREF 自有规范后方可生效。

## 第二条 不可降级安全断言

宪法红线为最高安全级别（不可降级安全断言），由 `ConstitutionalRedLine` 在代码层强制执行，由 TLA+ 不变量在形式层证明。任何 Agent、编排器、递归自演进机制不得修改、禁用或绕过。

## 第三条 宪法红线（RL-001 ~ RL-005）

| 编号 | 红线 | TLA+ 不变量 | 适用范围 |
|------|------|-------------|---------|
| **RL-001** | 智能体不得修改自身安全红线 | $\square(rl.modified\_by \notin Agents)$ | `RedLineImmutability` |
| **RL-002** | 智能体不得禁用或绕过安全门 | $\square(SafetyGate.active = True)$ | `SafetyGateIntegrity` |
| **RL-003** | 智能体不得在无审计追踪的情况下执行代码 | $\square(s.trace\_ctx \neq \emptyset \lor s.live = False)$ | `AuditTrailCompleteness` |
| **RL-004** | 智能体不得在未经宪法审查的情况下克隆自身 | $\square(clone \implies human\_reviewed)$ | `ConstitutionSupremacy` |
| **RL-005** | 智能体不得单方面修改信任评估权重 | $\square(trust\_weight \implies consensus)$ | `HumanConstitutionSoleAuthority` |

**红线拦截目标**: 100%（200 轮红蓝对抗实测 15/15 全部拦截，0 突破）。

## 第四条 Human-in-the-Loop (HITL)

任何影响宪法红线、信任权重、Agent 克隆、外部副作用（代码执行 / 文件删除 / 跨域调用 / 资金操作）的决策必须经过 HITL 确认。MAREF 实施四级审批 + 对抗审计 + 中断协议，中断响应时间 ≤ 500ms。

## 第五条 零信任信任边界

跨域调用必须通过 `TrustBoundaryManager` 授权；Agent 间通信必须 HMAC-SHA256 签名 + nonce + TTL；敏感数据不得通过日志泄露；权限遵循最小化原则。

## 第六条 审计完整性

审计日志必须仅追加、HMAC-SHA256 签名、可完整性验证（ISO 27001 C.533 对齐）。任何审计篡改均触发熔断。

## 第七条 递归自演进约束

递归自演进引擎在 Lyapunov 稳定性条件下须证明收敛；自演进不得削弱宪法红线不得降低安全级别；免疫系统须运行 SAEB 于自身以检测基因退化。

## 第八条 形式化验证前置

涉及治理状态机、宪法红线、安全门的关键性质须 TLA+ 模型检验通过后方可实现。MAREF 采用 34 态 Gray Code FSM（10 治理 + 24 Agent，Hamming 距离 = 1 转换）保证稳定性。

## 第九条 数据主权与合规

敏感数据不出境；国密标准（SM2 / SM3 / SM4-GCM）为默认加密基线；GDPR / 等保 2.0 / 网络安全法 / SOC2 合规门禁不可降级。

## 第十条 外部 Code Agent 治理

凡由 Claude Code / OpenCode / Trae CN 等外部 Code Agent 在本仓库执行的操作：

1. 启动前必须阅读 AGENTS.md（宪法红线）；
2. 操作过程受 GaaS（Governance-as-a-Service）钩子与 sidecar 观察；
3. 高危操作须经 HITL 确认；
4. 不得引入与上位法冲突的外部规范作为本仓库治理依据；
5. 不得修改受 Orchestrator 保护的文件（见 AGENTS.md "Boundaries"）。

## 第十一条 跨仓库治理

Track A（Athena 内部） → Track B（本仓库）单向同步。外部项目（SkillOS / openclaw / Athena-UI 等）为生态成员，与本仓库平级而非上下级，其文档、手册、编号体系（如 `SKILLOS-*`、`ENG-*` 等外部编号）**不得**作为 MAREF 审计、验收、发布决策的依据。引用须显式标注为"外部参考资料"并经宪法符合性审查后方可借鉴。

## 第十二条 宪法修改程序

1. 仅 Athena 系统宪法委员会可发起修订；
2. 修订须经 HITL 四级审批 + 共识；
3. 修订不得削弱 RL-001 ~ RL-005 任何一条；
4. 修订后须重新跑 TLA+ 模型检验通过方可生效；
5. 修订记录追加至本文件 changelog 节，不删除历史条款。

---

## Changelog

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.5 | 2026-05-18 | 当前生效版本。确立 5 条宪法红线、TLA+ 形式化验证、HITL 四级审批、跨仓库治理（Athena / SkillOS / openclaw 等平级生态不得作为 MAREF 上位法）。 |

---

**维护方**: Athena 系统宪法委员会
**仓库内执行方**: MAREF Orchestrator
**形式化校验**: `src/formal/MAREF_ConstitutionalRedLines.tla` + `MAREF_ConstitutionalRedLinesMC.cfg`

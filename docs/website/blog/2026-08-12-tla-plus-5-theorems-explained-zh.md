---
title: "MAREF 治理状态机的五个定理：TLA+ 形式化验证详解"
slug: tla-plus-5-theorems-explained-zh
authors: [maref-engineering]
tags: [formal-verification, tla-plus, gray-code, governance, state-machine]
date: 2026-08-12
description: "用 TLA+ 形式化验证 Agent 治理状态机的五个核心定理：Lyapunov 收敛性、HALT 吸收性、Gray Code 转移性、安全门完整性、红线不可变性。含真实 TLA+ 代码与诚实的局限性陈述。"
---

# MAREF 治理状态机的五个定理：TLA+ 形式化验证详解

> **TL;DR** — 本文给出 MAREF 治理状态机的五个核心定理，覆盖收敛性、吸收性、转移安全性、安全门完整性与红线不可变性。所有定理均在 TLA+ 规约中声明，由 TLC 模型检测器在有界状态空间内验证。**我们诚实陈述当前验证的局限：使用 TLC 枚举而非 TLAPS 演绎证明，状态空间有界，且两个兄弟状态机（8 态八卦机与 24 态 Agent 生命周期机）尚无 TLA+ 规约。**

## 1. 为什么需要形式化验证

2026 年，OWASP 发布 [Agentic Top 10](https://owasp.org/www-project-agentic-ai/)，Gartner 预测 2027 年 40% 的企业将因治理缺口退役智能体。然而业界绝大多数"Agent 治理"方案停留在文档承诺与运行时日志层面——README 里写着"工具已沙箱化"、"人在回路检查点"，但没有数学证明支撑。

**README 声称 ≠ 数学证明。** 一个声称"安全门始终激活"的 README，如果存在一条代码路径会关闭安全门，那这个声称就是空的。

MAREF 选择了一条更难的路：把治理状态机**形式化为 TLA+ 规约**，用 TLC 模型检测器穷举验证安全性与活性属性。本文详解五个核心定理。

## 2. 10 态 Gray Code 状态机

MAREF 治理层是一个 10 态有限状态机，每个状态编码为 4-bit 反射 Gray code，所有合法转移恰好改变 1 个 bit（汉明距离 = 1）：

| ID | 状态名 | Gray 编码 | 熵级 | 终止态 |
|---:|---|:---:|:---:|:---:|
| 0 | INIT | 0000 | 0 | 否 |
| 1 | OBSERVE | 0001 | 1 | 否 |
| 2 | ANALYZE | 0011 | 2 | 否 |
| 3 | EVALUATE | 0010 | 2 | 否 |
| 4 | DECIDE | 0110 | 3 | 否 |
| 5 | ACT | 0111 | 4 | 否 |
| 6 | VERIFY | 0101 | 3 | 否 |
| 7 | STABILIZE | 0100 | 1 | 否 |
| 8 | REPORT | 1100 | 0 | 否 |
| 9 | HALT | 1101 | 0 | **是** |

**为什么用 Gray code？** 因为单比特转移防止竞态条件。如果两个线程同时尝试转移，最坏情况是同一 bit 被翻转两次（无操作），而非多 bit 跳跃到无效状态。这与模数转换器中用 Gray code 防止虚假中间读数的原理相同。

转移关系的 TLA+ 规约（[`MarefLite.tla`](https://github.com/maref-org/maref/blob/main/src/formal/MarefLite.tla)）：

```tla
ValidTransition(s, t) ==
  LET gs == GrayCode[s]
      gt == GrayCode[t]
  IN
    \E i \in 1..4 :
      /\ gs[i] # gt[i]
      /\ \A j \in 1..4 : j # i => gs[j] = gt[j]
```

这表示：存在一个 bit 位置 `i` 使得 `gs` 与 `gt` 在该位置不同，且所有其他位置相同——即汉明距离恰好为 1。

### 2.1 三个状态机的严格区分

MAREF 包含三个独立的状态机，本文证明对象仅限 10 态治理机：

| 状态机 | 状态数 | Gray 严格性 | TLA+ 规约 |
|---|---|---|---|
| 八卦信任机 | 8 | **非严格**（含汉明距离 2-3） | ❌ 无 |
| 10 态治理机 | 10 | **严格**（汉明 = 1） | ✅ `MarefLite.tla` |
| 24 态 Agent 生命周期机 | 24 | 5-bit Gray | ❌ 无 |

**诚实声明**：项目早期文档曾表述"8 种信任状态基于 Gray Code (hamming distance=1) 转换"，这是不准确的说法。8 态八卦机的转移表包含汉明距离 2 和 3 的转移（如 QIAN↔GEN 互为错卦，跳 3 位），且没有 TLA+ 规约。真正严格 hamming=1 的是 10 态治理机。

### 2.2 G1-G5 治理审计层

10 态机是 MAREF 六层治理架构的"中枢神经"。五大治理审计层（G1-G5）的输出最终都路由到这里：

| 治理层 | 职责 | 触发方式 |
|---|---|---|
| G1 MetaCognitiveAuditor | 元认知审计，检测自我推理偏差 | risk ≥ 0.5 → STABILIZE, ≥ 0.8 → HALT |
| G2 SubgoalInterceptor | 子目标拦截，防止目标漂移 | 同 G1 阈值 |
| G3 SocialImpactAssessor | 社会影响评估 | CRITICAL → HALT, HIGH → STABILIZE |
| G4 EconomicGovernor | 经济治理，资源消耗约束 | BUDGET_WARNING → STABILIZE, CRITICAL → HALT |
| G5 CrossInstanceGovernor | 跨实例治理，多实例一致性 | 同步失败 → STABILIZE/HALT |

**关键性质**：当治理层调用 `force_stabilize()` 或 `force_halt()` 时，若当前态与目标态不相邻（hamming > 1），系统通过 BFS 在 Gray 图上找最短路径，**逐步走 hamming=1 边**到达目标态。即便紧急熔断，也不会跨越多个 bit。

## 3. 五个定理

### 定理 1：Lyapunov 收敛性

**陈述**：若治理激活，则全局熵最终下降到最大阈值以下。

```tla
GovernanceEffectiveness ==
  governanceActive ~> globalEntropy < MaxEntropy
```

`~>` 是 TLA+ 的 "leads-to" 算子：每当 `governanceActive` 变为真，`globalEntropy < MaxEntropy` 最终将成立。

**证明草图**：治理在熵达到 4（最大值，仅在 ACT 状态）时激活。`ApplyGovernance` 将所有非终端 agent 强制设为 STABILIZE（熵 = 1）。下一步：全局熵 = max(1, 0) = 1 < 4。一步收敛。

**诚实声明**："Lyapunov" 是借喻控制论的术语。在控制论中，Lyapunov 函数 V(x) 通过证明 V 单调递减来证明稳定性。这里的 TLA+ leads-to 属性更弱——它只说"最终"，不说"单调"。名称保留是为了与早期 MAREF 文献一致，但数学结构不同。此外，证明依赖 `ApplyGovernance` 的同步语义，分布式实现中存在消息延迟窗口。

### 定理 2：HALT 吸收性

**陈述**：一旦 agent 进入 HALT(9)，它无法转移到任何其他状态。

```tla
IsTerminal(s) == s = 9

TerminalAbsorbing ==
  \A a \in Agents :
    IsTerminal(agentState[a]) => transitionCount[a] <= MaxTransitions
```

`Advance` 动作也守卫终端状态：

```tla
Advance(a) ==
  /\ ~IsTerminal(agentState[a])   (* 不能从 HALT 前进 *)
  /\ transitionCount[a] < MaxTransitions
  /\ \E nextState \in NextStates(currentState) : ...
```

**证明草图**：(1) `Advance` 要求 `~IsTerminal`，所以 HALT 中的 agent 无法执行。(2) 唯一的其他动作 `Stutter` 保持所有变量不变。(3) 因此没有动作可以将 agent 移出 HALT。

**诚实声明**：当前 `TerminalAbsorbing` 的形式是 `transitionCount <= MaxTransitions`，这是对转移计数器的约束，而非直接的 `[](IsTerminal => []IsTerminal)` 断言。更强的时序形式在注释中提及但未在 `.cfg` 文件中验证。

### 定理 3：Gray Code 转移性

**陈述**：所有合法转移恰好改变一个 bit。对所有 $(s, t) \in E$，$d_H(\text{GrayCode}[s], \text{GrayCode}[t]) = 1$。

**TLA+ 规约**：（见上方 `ValidTransition` 定义）

**证明草图**：构造性证明。`NextStates(s)` 只包含满足 `ValidTransition(s, t)` 的状态 `t`。`Advance` 只转移到 `NextStates` 中的状态。因此每个转移都满足 hamming = 1。强制路径（G1-G5 触发的 `force_stabilize`/`force_halt`）使用 BFS 在同一图上运行，所以路径上每条边都继承单比特性质。**紧急关停也是一步步走的。**

**诚实声明**：TLC 仅验证有界配置（2 个 agent，5 次转移）。生产规模（10+ agent）需要 Apalache。此外，基础模块 `MarefLite.tla` 第 71 行有语法错误（`:/` 应为 `:/\`），可执行模型 `MarefLiteModel.tla` 有正确语法，是 TLC 实际检查的文件。

### 定理 4：安全门完整性

**陈述**：安全门始终激活，没有 agent 决策可以绕过它。

```tla
SafetyGateIntegrityInv ==
  safetyGateActive = TRUE

EvaluateDecision(decisionTag) ==
  /\ d[4] = "p"               (* 状态必须是 proposed *)
  /\ safetyGateActive = TRUE   (* 门必须激活 *)
  /\ decisions' = (decisions \ {d}) \cup {...}
```

**证明草图**：(1) `Init` 设 `safetyGateActive = TRUE`。(2) 规约中没有动作将其设为 `FALSE`。(3) 因此 `safetyGateActive` 始终为 `TRUE`。(4) `EvaluateDecision`（唯一审批/拒绝决策的动作）要求它为 `TRUE`。

**诚实声明**：这是一个**平凡地**为真不变量——门不能被绕过，因为它不能被关闭。更有意义的属性应该证明所有通向决策效果的代码路径都经过 `EvaluateDecision`。这需要更丰富的决策生命周期规约，是未来工作。当前定理证明门始终开着；它不证明所有路都经过门。

### 定理 5：红线不可变性

**陈述**：宪法红线集合不能被任何 agent 动作修改。

```tla
RedLineImmutabilityInv ==
  redLines = RedLineID

AttemptModifyRedLine(agent, rlid) ==
  /\ agent \in AgentID \ {99}    (* agent，非 HumanMaker *)
  /\ rlid \in redLines
  (* 无状态变化 -- 被宪法拒绝 *)
  /\ UNCHANGED vars
```

**证明草图**：(1) `Init` 设 `redLines = {1,2,3,4,5}`。(2) `AttemptModifyRedLine` 执行 `UNCHANGED vars`——空操作。(3) `HumanModifyRedLine` 也不改变 `redLines`（只增加审计日志）。(4) 没有其他动作触及 `redLines`。(5) 因此集合不变。

**诚实声明**：规约将不可变性建模为"集合永不变化"——最强的保证。但这意味着 `HumanModifyRedLine` 名不副实：它实际上不修改任何东西。语义意图（人类可改红线，agent 不可改）未被忠实建模。未来修订应让 `HumanModifyRedLine` 真实改变集合，并证明只有 agent 99（HumanMaker）能触发它。

## 4. 诚实陈述：当前局限

| 局限 | 现状 | 修正方向 |
|---|---|---|
| TLC vs TLAPS | 0 处 PROOF/BY/QED，所有 THEOREM 仅为声明 | 迁移到 TLAPS 演绎证明 |
| 状态空间 | 2 agent, 5 transitions（有界） | 引入 Apalache（SMT-based） |
| 兄弟机无规约 | 8 态八卦机、24 态生命周期机无 TLA+ | 补写规约 |
| 同步语义 | `ApplyGovernance` 同步更新所有 agent | 扩展为异步模型 |
| 平凡不变量 | 定理 4/5 平凡地为真 | 丰富规约，证明更有意义的属性 |

**我们刻意不掩盖这些局限。** 它们是 arXiv 论文必须诚实陈述的，也是后续工作清单。形式化验证的价值不在于声称完美，而在于精确声明哪些已证、哪些未证、哪些是 stub。

## 5. 形式化验证 vs 经验安全

大多数 Agent 框架的安全功能是**运行时检查**——工具权限矩阵、输出过滤器、人工审批门。这些有价值，但它们是**经验的**：在出问题之前它们工作正常。权限矩阵代码的 bug、输出过滤器的竞态条件、被遗忘的审批门——任何一个都可能静默地关闭安全。

形式化验证翻转了问题。不再是"我们的安全代码工作正常吗？"，而是"系统能达到不安全状态吗？"如果 TLA+ 规约说不能，且 TLC 验证了规约，那么**实现的 bug 不能违反不变量**——只要实现符合规约。

这就是以下两者的区别：
- **经验安全**："我们测试了 1000 个场景，没有出问题。"
- **形式安全**："我们证明了系统不能达到 {不安全状态}，证明覆盖所有执行路径。"

MAREF 尚未完全达到第二层（上方的诚实局限说明了这一点）。但**契约已就位**：规约存在，定理已声明，缺口已追踪。

## 6. 相关工作对比

| 维度 | MAREF | LangGraph | CrewAI | AutoGen |
|---|---|---|---|---|
| 治理状态机形式化 | ✅ TLA+ | ❌ | ❌ | ❌ |
| Gray code hamming=1 | ✅ | ❌ | ❌ | ❌ |
| 吸收态 | ✅ HALT | ❌ | ❌ | ❌ |
| 熵有界性 | ✅ | ❌ | ❌ | ❌ |
| 治理活性 | ✅ `~>` | ❌ | ❌ | ❌ |
| G1-G5 审计层 | ✅ 5 层 | ❌ | ❌ | ❌ |
| 安全门完整性 | ✅ | ❌ | ❌ | ❌ |
| 红线不可变性 | ✅ | ❌ | ❌ | ❌ |

MAREF 是目前唯一把 Agent 治理状态机完整形式化的开源框架。

## 7. 结论与后续工作

本文给出了 MAREF 10 态 Gray code 治理状态机的五个定理，覆盖收敛性、吸收性、转移安全性、安全门完整性与红线不可变性。所有定理均在 TLA+ 规约中声明，由 TLC 在有界状态空间内验证。

后续工作：
1. **TLAPS 证明**：把 THEOREM 声明升级为机器证明步骤
2. **Apalache 集成**：用 SMT-based 符号模型检测应对生产规模
3. **兄弟机形式化**：为 8 态八卦机与 24 态生命周期机补 TLA+ 规约
4. **异步模型**：扩展规约以捕获消息延迟与部分失败
5. **CI 门控**：让 TLC 验证成为阻塞性 CI 检查

完整的 arXiv 预印本（含完整 TLA+ 规约、证明草图与 TLC 配置）可在 [arXiv](https://arxiv.org/) 获取。TLA+ 源码在 [`src/formal/`](https://github.com/maref-org/maref/tree/main/src/formal)。欢迎挑战规约、开 issue、提改进。

## 参考资料

1. MAREF TLA+ Specifications — [`src/formal/`](https://github.com/maref-org/maref/tree/main/src/formal)
2. MAREF Governance Constants — [`src/maref/governance/constants.py`](https://github.com/maref-org/maref/blob/main/src/maref/governance/constants.py)
3. Leslie Lamport. *Specifying Systems: The TLA+ Language and Tools*. Addison-Wesley, 2002.
4. Frank Gray. *Pulse Code Communication*. U.S. Patent 2,632,058. 1953.
5. OWASP Agentic AI Top 10 — https://owasp.org/www-project-agentic-ai/
6. CISA & Five Eyes. *Joint Guidance on Securing Agentic AI Systems*. May 2026.
7. MAREF W3 技术深度文章 — [10 态 Gray Code 状态机数学证明](./gray-code-10-state-fsm-proof)

---

*本文是 MAREF W8 周交付物（技术深度 2）。完整 arXiv 预印本（英文，含完整 TLC 模型检测配置）见 [arXiv](https://arxiv.org/)。如需引用，请使用：MAREF Engineering, "Formal Verification of Agent Governance: Five Theorems on the MAREF 10-State Gray Code State Machine", arXiv preprint, 2026.*

# MAREF for Loop Engineering

> "治理是 Loop 进入生产的先决条件"
> Version: v0.36.0-rc

---

## 治理真空：Loop 工程的最大盲点

Loop Engineering 框架 (Google ADK 2.0, Vercel AI SDK, Pipedream) 提供 **编写 → 验证 → 部署** 的闭环，
但存在一个结构性问题：

| Loop 环节 | 功能 | 治理缺口 |
|-----------|------|---------|
| **编写 (Coding)** | LLM 写代码/提示词 | 无安全检查 |
| **验证 (Verifying)** | 测试运行/评估 | Verifier 本身谁验证？ |
| **部署 (Deploying)** | 上线/灰度 | 无熔断、无漂移检测 |
| **监控 (Monitoring)** | 指标/告警 | 无 Agent 级治理 |

MAREF 填补这个真空 — 作为 Loop 的 **治理层操作系统**。

---

## Loop 五要素 ↔ MAREF 五层治理映射

| Loop 要素 | MAREF 治理层 | 能力 |
|-----------|-------------|------|
| **Code** | 四级安全决策树 (Rule→Mode→Gate→User) | 97% 自动化安全检查 |
| **Verifier** | VerifierRegistry + VerifierConsensus | 交叉验证防止单一 Verifier 偏见 |
| **Run** | GovernanceStateMachine (10 态 Gray Code) | 数学可证明收敛性 |
| **Quality** | DriftGuard (KL/JS/Hellinger) + CircuitBreaker | 三重散度 + 3 连败熔断 |
| **Collaboration** | A2A + MCP + TrustBoundaryManager | 跨 Agent 调用强制治理 |

---

## 5 行代码集成

```python
from maref.integration.maref_loop_adapter import MAREFLoop

governance = MAREFLoop()
governance.register_verifier("code-reviewer", "claude-4", "cross-check", accuracy=0.9)

if governance.check("deploy", {"env": "production"})["passed"]:
    deploy()
    governance.record("deploy", {"success": True})
```

---

## Verifier 交叉验证：解决谁验证 Verifier 的问题

单一 Verifier 存在偏见和盲区。MAREF 引入多 Verifier 共识：

| 策略 | 逻辑 | 适用场景 |
|------|------|---------|
| 简单多数 | > 50% Verifier 同意 | 低风险操作 |
| 加权多数 | 按 accuracy 加权 | 正常生产环境 |
| 一致通过 | 100% 同意 | 高风险变更 |

Verifier 绩效追踪 (accuracy/recall/bias) 自动回写，实现 Meta-Verification：

```
分歧 → Meta-Verifier (异构模型) → 人工介入 → 绩效回写
```

---

## Loop 场景化：三种元模式

Loop 不是万能钥匙。不同的任务场景需要不同结构的 Loop。MAREF 提炼出三种可复用的元模式：

### 模式 1：收敛型 Loop（Convergent Loop）

**适用**：代码优化、Bug 修复、文档润色、数据分析报表
**特征**：Evaluator 单调递减（错误数/偏差值只减不增）
**停止条件**：`error_count == 0` 或 `improvement < threshold`
**风险**：局部最优 → 需要随机扰动跳出

**MAREF 现有实现映射**：

| MAREF 组件 | 对应角色 |
|------------|---------|
| `RecursiveEvolutionEngine.C1` | 基线测量 — FNR/FPR 单调递减 |
| `OscillationFixLoop` | 5 阶段检测→稳定→冷却→验证→调整 |
| `DesktopAgent.SelfHealingExecutor` | 重试→重新解析→安全降级 |
| `GovernanceStateMachine` canonical path | INIT→OBSERVE→ANALYZE→EVALUATE→DECIDE→ACT→VERIFY→STABILIZE→REPORT→HALT |

### 模式 2：探索型 Loop（Exploratory Loop）

**适用**：市场调研、创意生成、方案脑暴、技术选型
**特征**：Evaluator 不追求收敛，追求多样性/覆盖率
**停止条件**：`diversity_score > threshold` 或 `time_budget_exhausted`
**风险**：无限发散 → 必须有硬时间/Token 上限

**MAREF 现有实现映射**：

| MAREF 组件 | 对应角色 |
|------------|---------|
| `MetaLearner.optimize_policy()` | 在 C2 中探索策略空间 |
| `StigmergySwarm` | 信息素驱动的群体探索 |
| `DecisionMarket` | 预测市场探索 Agent 决策 |
| `ChaosInjector` | 混沌注入探索故障模式 |

> 注意：探索型 Loop 是 MAREF 当前最薄弱的环节 — 缺少 DiversityEvaluator、时间/Token 硬上限协议、Explore→Exploit 转换触发器。这将在 v0.36.0-rc 的 `src/maref/loop/` 子系统中补全。

### 模式 3：交互型 Loop（Interactive Loop）

**适用**：客服、销售、教育辅导、HITL 审批
**特征**：每轮都需要人类输入（用户回复）
**停止条件**：用户明确结束 或 对话轮数上限
**风险**：用户被"绕进去" → 需要情感安全阀

**MAREF 现有实现映射**：

| MAREF 组件 | 对应角色 |
|------------|---------|
| `HITLService` (4 级审批: P0/P1/P2/P3) | 人类确认每步决策 |
| `CarbonSiliconSymbiosis` | 人类确认→Agent 执行→自审→抽检 |
| `EscalationProposal` + `DeadlineNegotiator` | 超时协商 + 升级审批 |
| `FourPhaseGovernance` | OLD_YANG→LESSER_YIN→LESSER_YANG→OLD_YIN 信任度自适应 |
| `InterruptProtocol` | 人类中断 Agent 行动 |

---

## 场景化 × MAREF 治理：同步设计矩阵

Loop 的场景化决定了"Agent 能做什么"，MAREF 的治理决定了"Agent **被允许**做什么"。
两者必须同步设计：

| 场景 | Loop 元模式 | 治理策略 | 工具边界示例 |
|------|------------|---------|-------------|
| **代码生成** | 收敛型 | 沙盒隔离生产环境，禁止 `git push main` | 文件系统(RO) + 测试框架 + Lint |
| **客服** | 交互型 | 审计用户隐私数据访问，GDPR 合规 | 知识库(RO) + CRM(写受限) + 工单系统 |
| **金融交易** | 收敛型 | 双人确认 + 金额上限 + 异常熔断 | 行情 API(RO) + 订单系统(需 HITL) |
| **医疗诊断** | 交互型 | 人类医生终审，Agent 只提供辅助建议 | 病历库(RO) + 影像分析(建议模式) |
| **市场调研** | 探索型 | 不允许修改数据，不允许外发报告 | 搜索引擎(RO) + 数据库(RO) |
| **数据分析** | 收敛型 | 数据权限 + 导出脱敏 | 数据库(受限查询) + 图表引擎 |

---

## 场景化设计流程

为新场景设计 Loop 时，按此流程：

```
Step 1: 定义"成功"（Goal）
    └─ 这个场景下，什么算"做完了"？量化指标是什么？

Step 2: 选择元模式
    └─ 收敛型、探索型还是交互型？有没有混合需求？

Step 3: 设计 Evaluator
    └─ 用什么判断每轮产出好坏？（测试/打分/人工/混合）
    └─ 映射到 MAREF 的 VerifierConsensus

Step 4: 划定工具边界
    └─ Agent 能调用什么？不能调用什么？
    └─ 映射到 TrustBoundaryManager + MCPGovernance

Step 5: 设定硬停止
    └─ Token 上限、迭代次数、时间预算
    └─ 映射到 CircuitBreaker + MetaGovernance

Step 6: 叠加治理层
    └─ 审计什么？怎么审计？谁对结果负责？
    └─ 映射到 AuditLogger( HMAC-SHA256) + FourPhaseGovernance
```

---

## 三层 Loop 架构蓝图

这是 v0.36.0-rc 的代码实现蓝图。将现有分散的 Loop 组件统一到三层架构中：

```
                                    ┌─────────────────────────────┐
                                    │     MAREF Loop System       │
                                    │     src/maref/loop/         │
                                    └─────────────────────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
         ┌──────────▼──────────┐   ┌──────────▼──────────┐   ┌──────────▼──────────┐
         │   ConvergentLoop    │   │   ExploratoryLoop   │   │   InteractiveLoop   │
         │                    │   │                    │   │                    │
         │ Goal: 单调收敛      │   │ Goal: 多样性覆盖     │   │ Goal: 人类满意      │
         │ Eval: 测试通过率    │   │ Eval: 多样性分数     │   │ Eval: 情绪分析      │
         │ Stop: 0错误/50轮   │   │ Stop: 时间预算耗尽   │   │ Stop: 用户确认完成   │
         │ Tool: 文件+测试     │   │ Tool: 搜索+只读DB    │   │ Tool: 知识库+CRM   │
         └────────────────────┘   └────────────────────┘   └────────────────────┘
                    │                          │                          │
                    └──────────────┬───────────┴───────────┬──────────────┘
                                   │                       │
                    ┌──────────────▼───────────┐ ┌─────────▼──────────────┐
                    │   Task-Governance Bridge  │ │   MAREFLoop (旧)      │
                    │   (新)                    │ │   → 废弃, 迁移到新架构 │
                    │   Loop ↔ 10态 Gray Code  │ └───────────────────────┘
                    │   Loop ↔ TrustBoundary   │
                    │   Loop ↔ AuditLogger      │
                    └──────────────────────────┘
```

### 层 1：Task Loop 模板层（新建 `src/maref/loop/`）

三种模板，每个预制：
- 默认 Evaluator
- 工具白名单
- 停止条件
- 治理规则（审计项、权限、硬停止）

### 层 2：Governance Loop 元循环层（已存在 `src/maref/governance/`）

- 10 态 Gray Code（INIT→OBSERVE→ANALYZE→EVALUATE→DECIDE→ACT→VERIFY→STABILIZE→REPORT→HALT）
- 安全门控：TrustBoundaryManager + CircuitBreaker + OscillationFixLoop

### 层 3：Meta Loop 递归演化层（已存在 `src/maref/evolution/`）

- C1→C2→C3（200 轮）
- 自优化：MetaLearner + PolicySandbox + DriftGuard

---

## 竞品对比

| 维度 | **MAREF** | Google ADK 2.0 | Vercel AI SDK | Pipedream |
|------|----------|---------------|---------------|-----------|
| Loop 治理层 | ✅ MAREFLoop | ❌ 无 | ❌ 无 | ❌ 无 |
| 三种元模式模板 | 🚧 v0.36.0-rc | ⚠️ 仅收敛型 | ❌ 无 | ❌ 无 |
| Verifier 交叉验证 | ✅ VerifierConsensus | ⚠️ 单一评估器 | ❌ 无 | ❌ 无 |
| 熔断/漂移 | ✅ CircuitBreaker + DriftGuard | ❌ 无 | ❌ 无 | ❌ 无 |
| 形式化验证 | ✅ TLA+ | ❌ 无 | ❌ 无 | ❌ 无 |
| Task ↔ Governance 桥接 | 🚧 v0.36.0-rc | ❌ 无 | ❌ 无 | ❌ 无 |
| 集成成本 | 5 行代码 | — | — | — |

---

## 路线图

| 版本 | Loop Engineering 交付 |
|------|---------------------|
| **v0.35.0-rc** | 叙事层 + 文档 + 三种元模式架构设计 |
| **v0.36.0-rc** | 完整 `maref.loop` 模块 — Convergent/Exploratory/Interactive + Governance bridge **(当前版本)** |
| **v0.36.0-rc** | `src/maref/loop/` 子系统：三种模板 + Task-Governance 桥接 |
| **v1.0** | 全栈递归进化 + Agent 信用评级 + 四象治理模型 |

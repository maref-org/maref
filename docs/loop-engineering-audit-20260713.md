# Loop Engineering 方法论审计报告

> **审计对象**：用户提供的 Loop Engineering 定义（2026 年兴起的新一代 AI Agent 工程方法论）
> **审计日期**：2026-07-13
> **审计立场**：该框架在「协作编排」维度合理，但在「治理约束」与「交叉验证」维度存在结构性缺口
> **关联上下文**：MAREF G1-G5 辛顿交叉验证、PERCV RSI 循环、RSI 48h run 失败教训（PID 91372）

---

## 一、Loop Engineering 核心摘要

### 1.1 核心定义

> Loop Engineering（循环工程）是 2026 年兴起的新一代 AI Agent 工程方法论，核心是从"人逐句指挥 AI"转变为"设计闭环系统让 AI 自主迭代"。
> 闭环逻辑：**执行 → 观察 → 评估 → 修正 → 再执行**
> 灵魂：让 AI 每一轮都离目标更近，并且**知道什么时候该停止**，验证逻辑才是闭环的关键。

### 1.2 AI 项目效率低的 4 大核心原因

1. **上下文混乱**：脚本、分镜、视觉、渲染需要的材料和判断标准完全不同，混在一起会互相干扰。
2. **无法并行**：找案例、试标题、试脚本角度、试视觉方向这些本可以同时做的事，被单聊天框压成了单线程。
3. **缺少分层验收**：弱稿不该等用户发现，AI 应该先自检、互审，再按标准筛选。
4. **状态记录太弱**：下一轮返工、交接、判断，都只能靠记忆硬接，没有清晰的状态留存。

### 1.3 5 步核心逻辑

1. **监工先拆任务地图**：目标、输入、输出、验收标准、依赖关系、优先级、可并行性、风险等级。
2. **低风险并行，高风险串行**：低风险调研/参考/标题可并行；高风险选题/脚本/发布默认串行。
3. **按固定格式回包**：任务 ID、当前状态、完成摘要、产物路径、证据来源、自检结果、风险点、下一步建议。
4. **监工合并状态、验收返工**：状态板合并、质量检查、冲突发现、小判断 AI 过滤、大判断交给人。
5. **闭环迭代直到完成**：循环推进，每轮离目标更近，直到所有任务通过验收。

### 1.4 价值主张

| 维度 | 宣称收益 |
|------|----------|
| 效率 | 人工干预频次下降 60%+，技术团队重复工时削减 83% |
| 质量 | 任务出错率、漏检率、偏差率下降 40%+，质量持续收敛 |
| 成本 | 长期运维人力成本降低 30%，标准化流程支持多业务复用 |
| 规模化 | 一人多任务，下班后 AI 继续干活，AI 项目真正可规模化 |

---

## 二、核心诊断：六大缺口

| # | 缺口 | 严重度 | 文中表现 | 真实风险 |
|---|------|--------|----------|----------|
| 1 | **缺少硬停止机制（Red Line）** | 🔴 P0 | 仅提及"知道什么时候该停止"，无具体定义 | 长 run 卡死、循环逃逸、不可逆破坏 |
| 2 | **交叉验证层数不足** | 🔴 P0 | 仅"AI 自检 + 互审"两层 | 单一判官偏差放大、模式坍缩 |
| 3 | **无状态一致性约束** | 🟠 P1 | "状态板"概念模糊 | 残留进程、心跳丢失、状态分叉 |
| 4 | **缺乏经济/资源治理** | 🟠 P1 | 未提及 token/时间预算 | 资源耗尽、激励错位 |
| 5 | **缺少目标漂移防护** | 🟠 P1 | 默认"AI 自主迭代" | Goal drift、Reward hacking |
| 6 | **指标量化标准缺失** | 🟡 P2 | "质量、冲突"等抽象词 | 不可比、不可复现、不可审计 |

### 2.1 关键句拆解

- ✅ **"验证逻辑才是闭环的关键"** —— 同意，但文中未给出"验证逻辑"的具体定义。
- ⚠️ **"人工干预频次下降 60% 以上"** —— 这是营销话术，非工程指标。真正的工程指标应是 **human-gate 触发率 + 误报率 + 漏报率**。
- ⚠️ **"技术团队重复工时削减 83%"** —— 缺乏对照实验与统计显著性。

---

## 三、交叉验证专项审计（重点）

### 3.1 文中提到的验证机制

```
步骤 3-5 隐含的验证层：
  Layer 1: 子 AI 自检（"按固定格式回包"）
  Layer 2: 监工验收（"检查质量、发现冲突"）
  Layer 3: 人类终审（"大判断再交给人"）
```

**总计：3 层，但实质上仅 2 层有效**（Layer 1 与 Layer 2 同源——都是 LLM 自评，缺独立性）。

### 3.2 与 MAREF G1-G5 辛顿交叉验证对比

| 维度 | Loop Engineering | MAREF G1-G5 | 差距 |
|------|------------------|-------------|------|
| 元认知审计 | ❌ 无 | ✅ G1 MetaCognitiveAuditor | 自我推理偏差盲区 |
| 子目标拦截 | ⚠️ 隐含 | ✅ G2 SubgoalInterceptor | 越权委派盲区 |
| 社会影响评估 | ❌ 无 | ✅ G3 SocialImpactAssessor | 副作用盲区 |
| 经济治理 | ❌ 无 | ✅ G4 EconomicGovernor | 资源激励盲区 |
| 跨实例一致性 | ❌ 无 | ✅ G5 CrossInstanceGovernor | 多实例分歧盲区 |
| **独立性** | ❌ 同源 LLM | ✅ 5 个独立模块 | **核心缺陷** |

**结论**：Loop Engineering 的"交叉验证"是**伪交叉**——Layer 1 与 Layer 2 由同一模型或同源 prompt 完成，无法构成统计意义上的独立验证。

### 3.3 真实教训对照

> **RSI 48h run (PID 91372) 失败根因**：单点 MetaRatchet 诊断 saturation(low) 未采取实质行动，breakthroughs 误报泛滥，metric 卡 0.99 长达 34h。

这个案例证明：**单一验证层无法发现"自评一致性陷阱"**——当 LLM 持续对自身输出给出 0.99 分时，缺少独立 critic 就会让"假阳性饱和"持续 34h 而无人察觉。

### 3.4 现有 `VerifierConsensus` 的局限性

`src/maref/governance/verifier_consensus.py` 已实现 3 策略（simple_majority / weighted_majority / unanimity），但存在三个**结构性盲点**：

1. **同源假设**：未验证 verifier 之间的 prompt 独立性
2. **无硬停止**：投票通过即继续，无 StopReason 维度
3. **无精度门**：breakthrough 用 `>=` 比较，对浮点噪声过敏（与 RSI 教训同源）

新模块 `src/maref/governance/cross_validator.py` 修复了这三点。

---

## 四、优化建议（按优先级）

### 🔴 P0：必须修复

#### 优化 1：硬停止机制（Hard Stop Semantics）

应补充的停止条件维度：

```python
STOP_CONDITIONS = {
    "safety": ["sentinel_file_exists", "human_gate_triggered", "red_line_violated"],
    "convergence": ["metric_saturated_eps", "no_improvement_n_rounds", "cohens_d_below_threshold"],
    "resource": ["token_budget_exhausted", "time_budget_exhausted", "compute_budget_exhausted"],
    "integrity": ["state_inconsistency", "cross_validation_failed", "audit_score_below_floor"],
}
```

> **参考实现**：`HardStopGate`（`src/maref/governance/cross_validator.py`）已实现 4 维度 11 类停止条件。
> **绑定红线**：RSI-RL-001 human_gate 保护、RSI-RL-002 最小 10 轮沙箱、RSI-RL-004 MAS-TS 分数 ≥60 门槛。

#### 优化 2：独立 critic 池

```python
class CrossValidator:
    def __init__(self, ...):
        self._critics: list[IndependentCritic] = []

    def validate(self, item):
        assert_critic_independence(self._critics)  # 强制多样性
        verdicts = [c.judge(item) for c in self._critics]
        # 多数决 + confidence 加权
```

**关键约束**（已在 `assert_critic_independence` 中强制）：

- 不同 critic 必须**prompt 模板不同**（避免同源偏差）
- 至少 1 个 critic 使用**对抗性 prompt**（`CriticMode.ADVERSARIAL`："找出这个输出的 3 个问题"）
- 至少 1 个 critic 使用**外部工具**（`CriticMode.TOOL_BASED`）
- temperature 跨度 ≥ 0.1
- mode 至少 2 种

#### 优化 3：去重与精度门（参考 RSI 教训）

> [memory] "允许新高度"不能对微小波动过敏。`abs(hist_val - value) < epsilon` 视为相同值。

Loop Engineering 应明确：**验证通过 ≠ 产生新数据点**。必须设置去重 epsilon（如 1e-3），否则循环会产生大量"伪突破"假阳性。

**参考实现**：`BreakthroughDeduplicator`（`src/maref/governance/cross_validator.py`）用 `abs(hist - value) < epsilon` 语义，配置项 `DEFAULT_DEDUP_EPSILON = 1e-3`，与 RSI 噪声底对齐。

### 🟠 P1：强烈建议

#### 优化 4：状态板升级为状态账本

| 现状 | 建议 |
|------|------|
| "状态板" | 分布式状态账本 + 心跳 + 一致性协议 |
| 无心跳机制 | 每轮写入 `cycle_NNN.json` + `heartbeat.ts` + 哨兵文件 |
| 无残留检测 | 必须有 `liveness_probe()` 与 `orphan_cleanup()` |

> [memory] PID 96938 heartbeat_daemon.sh 残留进程教训——心跳丢失 8h 才被发现，需要主动 liveness 探测。

#### 优化 5：经济治理（Economic Governor）

```yaml
budgets:
  tokens_per_cycle: 50000
  cycles_max: 200
  wallclock_hours: 48
  human_review_threshold: 0.7  # compliance score
```

> [memory] G4 EconomicGovernor 是独立治理层，非可选优化项。
> `HardStopGate` 已实现 `max_tokens_per_cycle` / `max_wallclock_hours` 软约束。

#### 优化 6：目标漂移检测

```python
def check_goal_drift(current_goal: Goal, original_goal: Goal, threshold: float = 0.3) -> DriftReport:
    """目标漂移检测：cosine 相似度 < 1 - threshold 即报警"""
    return DriftReport(
        similarity=cosine_sim(current_goal.embed(), original_goal.embed()),
        diverged_subgoals=find_unauthorized_subgoals(current_goal, original_goal)
    )
```

> 参考：G2 SubgoalInterceptor 的越权委派检测。

### 🟡 P2：可后续迭代

#### 优化 7：可复现性

- 固定 random seed
- 记录所有 prompt 模板版本
- 记录 critic 投票明细（非仅最终结论）
- 容器化执行环境

#### 优化 8：审计可观测

- 每轮 cycle 必须产出可审计的 `cycle_log.json`（含 critic 投票、状态快照、决策依据）
- 不可变审计日志（append-only）

---

## 五、结构性建议

### 5.1 Loop Engineering 应增加的概念

```
原结构：执行 → 观察 → 评估 → 修正 → 再执行
建议结构：执行 → 观察 → 交叉验证(多 critic) → 经济检查 → 目标对齐 → 修正 → 硬停止判定 → 再执行
```

新增 3 个 gate：
- **交叉验证 gate**（多独立 critic 投票）
- **经济 gate**（资源预算检查）
- **目标对齐 gate**（防 drift）

### 5.2 与 MAREF 现有体系的集成路径

| 既有体系 | 集成方式 |
|----------|----------|
| MAREF G1-G5 | 作为 Loop Engineering 的"治理底座" |
| PERCV RSI 循环 | 作为具体执行引擎（已有 MetaRatchet、breakthrough 去重） |
| RSI 红线 | 转换为 Loop Engineering 的 hard stop 条件 |
| 沙箱测试 | 转换为 pre-loop 验证（10 轮最小门槛） |
| `VerifierConsensus` | 升级为 `CrossValidator`（向后兼容） |
| `CircuitBreaker` | 作为 stop gate 的子组件 |
| `OscillationFixLoop` | 作为 convergence stop 的辅助检测 |

### 5.3 闭环结构对比

| 层级 | Loop Engineering 原文 | MAREF + Loop Engineering 补全 |
|------|----------------------|-------------------------------|
| L1 编排 | 监工拆任务地图 | Task-Governance Bridge（v0.36.0-rc） |
| L2 执行 | 子 AI 并行 | RoleComposer + Saga |
| L3 评估 | 监工验收 | **CrossValidator**（新增） |
| L4 修正 | 修正 → 再执行 | CapabilityContract + self-healing |
| L5 停止 | "知道什么时候停" | **HardStopGate**（新增） |
| L6 元循环 | 无 | RecursiveEvolutionEngine C1→C2→C3 |

---

## 六、综合评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 闭环编排合理性 | 7/10 | 五步逻辑清晰，但缺硬约束 |
| 交叉验证严谨性 | 3/10 | 伪交叉，仅 2 层同源验证 |
| 安全性设计 | 4/10 | 无 red line / sentinel / kill switch |
| 可审计性 | 5/10 | "状态板"概念模糊 |
| 可复现性 | 3/10 | 无固定 seed / prompt 版本控制 |
| **综合** | **4.4/10** | **方法论骨架可用，治理肌肉未发育** |

**核心结论**：Loop Engineering 是一个**协作编排层（orchestration layer）**的合理设计，但不能独立作为 Agent 治理框架使用。**必须叠加 G1-G5 风格的独立交叉验证层 + 硬停止机制 + 经济治理层**，才能进入生产级 48h 长循环。

---

## 七、与现有 `docs/loop-engineering-integration.md` 的关系

本文档与 [`docs/loop-engineering-integration.md`](../loop-engineering-integration.md) 互补：

- `integration.md`：MAREF → Loop Engineering 的能力映射（MAREF 提供什么）
- `audit-20260713.md`（本文）：Loop Engineering → MAREF 的缺口清单（Loop Engineering 缺什么）
- `architecture-integration.md`：两者融合的三层架构蓝图

三者构成 Loop Engineering × MAREF 完整知识三角。

---

## 八、参考文件

- [src/maref/governance/cross_validator.py](../../) — P0 三项新增实现（独立 critic 池 + 硬停止 + epsilon 去重）
- [src/maref/governance/verifier_consensus.py](../../) — 基础多数决（被 CrossValidator 调用）
- [src/maref/governance/circuit_breaker.py](../../) — 深度/震荡/失败熔断
- [src/maref/governance/oscillation.py](../../) — 5 阶段震荡修复闭环
- [docs/loop-engineering-integration.md](../loop-engineering-integration.md) — MAREF for Loop Engineering
- [docs/loop-engineering/convergent-template.md](../loop-engineering/convergent-template.md) — 收敛型 Loop 模板
- [docs/loop-engineering/architecture-integration.md](../loop-engineering/architecture-integration.md) — 三层架构蓝图（Mermaid）

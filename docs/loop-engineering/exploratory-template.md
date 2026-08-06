# Exploratory Loop Template

> v0.35.0-rc (Spec) → v0.36.0-rc (Implementation)
> 对应 MAREF 组件：`MetaLearner` · `StigmergySwarm` · `DecisionMarket` · `ChaosInjector`

---

## 适用场景

- 市场调研 / 竞品分析
- 创意生成 / 方案脑暴
- 技术选型 / 架构探索
- 故障模式发现
- 任何需要多样性覆盖的任务

---

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│                    Exploratory Loop                          │
│                                                              │
│  INIT → GENERATE → EVALUATE_DIVERSITY → [covered?] → HALT  │
│                    │                        │                 │
│                    ▼                        ▼ no             │
│              记录发现集                  EXPAND              │
│                                          ↓                   │
│                                    NEW_DIRECTION             │
│                                                              │
│  硬限制: MaxTokens (默认 100K tokens)                        │
│          MaxTime (默认 5 min)                                │
│          MaxRounds (默认 20)                                 │
│                                                              │
│  差异点: 没有"修复→重试"循环                                 │
│          而是"发现→记录→分支"模式                              │
└──────────────────────────────────────────────────────────────┘
```

**与收敛型 Loop 的核心区别**：探索型不追求"越来越好"，追求"覆盖越广越好"。
每轮产出不覆盖上一轮，而是**追加到发现集**。

---

## 默认配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_rounds` | 20 | 最大迭代轮数 |
| `max_tokens` | 100000 | Token 硬上限 |
| `max_time_seconds` | 300 | 时间硬上限 |
| `diversity_threshold` | 0.3 | 新产出与已有发现集的余弦相似度 < 此值才算新发现 |
| `coverage_target` | 0.8 | 覆盖率达到此值 → 停止（需预定义覆盖空间） |
| `branch_factor` | 3 | 每轮最多分支出几个新方向 |
| `explore_restart_threshold` | 0.1 | 连续 N 轮无新发现 → 触发重启/切换策略 |

---

## Evaluator 接口

探索型的 Evaluator 不是"好坏评估"而是"多样性评估"：

```python
@dataclass
class ExplorationResult:
    discoveries: list[Discovery]          # 本轮新发现
    novelty_scores: list[float]           # 每条发现的新颖度 (0~1)
    coverage: float                       # 当前发现集对覆盖空间的覆盖率
    diversity_histogram: dict[str, float] # 各维度的分布
    metadata: dict[str, Any]

@dataclass
class Discovery:
    content: str
    source_round: int
    novelty: float                        # 与已有集的差异度
    tags: list[str]                       # 维度标签
```

---

## 工具白名单

| 工具域 | 权限 | 说明 |
|--------|------|------|
| 搜索引擎 | READ | 网页搜索 / 信息检索 |
| 数据库 | READ (只读) | 查询已有知识库 |
| 文件系统 | READ | 读取文档/代码 |
| 缓存系统 | WRITE | 写入发现集缓存 |
| LLM | GENERATE | 调用模型生成新方向 |

禁止：文件修改、Git 操作、生产环境写入、外部 API 写操作。

---

## 停止条件（优先级从高到低）

1. **Token 耗尽** — `total_tokens >= max_tokens` → HALT
2. **时间耗尽** — `elapsed >= max_time_seconds` → HALT
3. **覆盖达标** — `coverage >= coverage_target` → HALT
4. **新鲜度枯竭** — 连续 5 轮 `mean_novelty < explore_restart_threshold` → HALT
5. **最大轮数** — `round >= max_rounds` → HALT
6. **手动中断** — 外部信号 → HALT

---

## MAREF 治理绑定

| 治理层 | 绑定方式 |
|--------|---------|
| 天极 (红线) | `MetaAgentClosure` — 禁止探索绕开安全红线 |
| 人极 (HITL) | `HITLService.P2` — 发现集导出/分享需人类确认 |
| 地极 (信任) | `TrustBoundaryManager` — 强制 READ-ONLY 工具边界 |
| 经卦 (状态机) | `GovernanceStateMachine` — OBSERVE→ANALYZE→REPORT 循环（跳过 ACT） |
| 别卦 (约束) | `BlastRadiusController` — 评估探索方向组合风险 |
| 爻变 (演化) | `MetaLearner` — 将探索发现记为经验，优化后续探索策略 |

---

## 代码骨架（v0.36.0-rc 实现目标）

```python
class ExploratoryLoop:
    def __init__(
        self,
        generator: Callable[[list[Discovery], int], list[Discovery]],
        diversity_evaluator: Callable[[Discovery, list[Discovery]], float],
        tool_boundary: ToolBoundary,
        max_rounds: int = 20,
        max_tokens: int = 100000,
        max_time_seconds: int = 300,
    ):
        self._discoveries: list[Discovery] = []
        self._token_budget = TokenBudget(max_tokens)
        self._time_budget = TimeBudget(max_time_seconds)

    async def explore(self, seed: str) -> ExplorationResult:
        while self._token_budget.has_remaining() and self._time_budget.has_remaining():
            new_discoveries = self._generator(self._discoveries, self._branch_factor)
            filtered = [d for d in new_discoveries
                        if self._diversity_evaluator(d, self._discoveries)
                           > self._diversity_threshold]
            self._discoveries.extend(filtered)

            if self._check_stale():
                return self._finalize()
        return self._finalize()
```

---

## 现有 MAREF 映射已验证

| 现有组件 | 映射到此模板的位置 |
|----------|-----------------|
| `MetaLearner.optimize_policy()` | 策略空间探索（C2 中的 explore component） |
| `StigmergySwarm` 信息素模型 | 多样性追踪的底层机制 |
| `DecisionMarket` | Agent 决策空间的探索 |
| `ChaosInjector` | 故障模式空间的探索 |
| `CostTracker` | Token/时间预算追踪 |
| `Pheromone` (Stigmergy) | 发现集新鲜度衰减模型 |

> **注意**：当前 MAREF 缺少 `DiversityEvaluator`、`TimeBudget`/`TokenBudget` 硬上限协议、
> 和 `Explore→Exploit` 转换触发器。这些是 v0.36.0-rc 的核心新增代码。

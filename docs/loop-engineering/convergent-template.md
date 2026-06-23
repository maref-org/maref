# Convergent Loop Template

> v0.35.0-rc (Spec) → v0.36.0-rc (Implementation)
> 对应 MAREF 组件：`RecursiveEvolutionEngine` · `OscillationFixLoop` · `DesktopAgent.SelfHealingExecutor`

---

## 适用场景

- 代码生成/优化
- Bug 修复
- 文档润色
- 数据分析报表
- 超参数调优
- 任何 Evaluator 单调递减的任务

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Convergent Loop                           │
│                                                             │
│  INIT → EXECUTE → EVALUATE → [converged?] → HALT           │
│                    │              │                          │
│                    ▼              ▼ no                      │
│              记录指标         REFINE → 回到 EXECUTE          │
│                                                             │
│  安全层: CircuitBreaker (3连败熔断)                           │
│         OscillationFixLoop (震荡检测→稳定→调整)               │
│         MaxRoundGate (硬上限, 默认 50 轮)                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 默认配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_rounds` | 50 | 最大迭代轮数 |
| `convergence_threshold` | 0.01 | 连续 n 轮 improvement < threshold 视为收敛 |
| `convergence_window` | 5 | 收敛检测窗口 |
| `circuit_breaker_trips` | 3 | 连续失败次数触发熔断 |
| `oscillation_max_rate` | 10/min | 震荡检测灵敏度 |
| `random_restart_every` | 20 | 每 N 轮加入随机扰动跳出局部最优 |

---

## Evaluator 接口

评估器必须是可调用的 `Callable[[State], EvaluationResult]`：

```python
@dataclass
class EvaluationResult:
    score: float                       # 0.0 ~ 1.0, 越高越好
    errors: list[str]                  # 本轮发现的问题
    improvement: float                 # 与上轮比较的改善量 (负值 = 退化)
    metadata: dict[str, Any]           # 扩展指标
```

默认 Evaluator 是 VerifierConsensus（交叉验证），但允许替换为：
- 单元测试通过率
- Lint 检查通过数
- 用户评分
- 混合评估器（加权组合多个指标）

---

## 工具白名单

默认白名单（v0.36.0-rc 通过 TrustBoundaryManager 强制执行）：

| 工具域 | 权限 | 说明 |
|--------|------|------|
| 文件系统 | READ | 读取源文件 |
| 文件系统 | WRITE | 写入修改后的文件（受沙盒路径限制） |
| 测试框架 | EXECUTE | 运行测试套件 |
| Lint | EXECUTE | 运行代码检查 |
| Git | STATUS + DIFF | 查看变更，不允许 PUSH |

禁止：网络请求、生产环境部署、密钥读取、数据库写入。

---

## 停止条件（优先级从高到低）

1. **电路熔断** — 连续 3 轮 `score` 比基线更差 → HALT
2. **收敛** — 连续 5 轮 `improvement` < 0.01 → HALT
3. **满分** — `score == 1.0`（例如测试全绿） → HALT
4. **最大轮数** — `round >= max_rounds` → HALT
5. **退化检测** — `score` 连续 3 轮下降 → 触发随机重启或 HALT
6. **手动中断** — 外部信号 → HALT

---

## MAREF 治理绑定

| 治理层 | 绑定方式 |
|--------|---------|
| 天极 (红线) | `MetaAgentClosure` 验证收敛目标不可修改 |
| 人极 (HITL) | `HITLService.P1` — 首次部署/高风险变更需人类确认 |
| 地极 (信任) | `TrustBoundaryManager` 强制执行工具白名单 |
| 经卦 (状态机) | `GovernanceStateMachine` 跟踪每轮状态: OBSERVE→ANALYZE→DECIDE→ACT→VERIFY→STABILIZE |
| 别卦 (约束) | `CapabilityContract` 验证每轮输出符合 schema |
| 爻变 (演化) | `RecursiveEvolutionEngine` 将收敛指标记入演化历史 |

---

## 代码骨架（v0.36.0-rc 实现目标）

```python
class ConvergentLoop:
    def __init__(
        self,
        evaluator: Callable[[Any], EvaluationResult],
        tool_boundary: ToolBoundary,
        max_rounds: int = 50,
        convergence_threshold: float = 0.01,
    ):
        self._state = ConvergentState()
        self._breaker = CircuitBreaker(max_consecutive_failures=3)
        self._oscillation = OscillationFixLoop(...)

    async def run(self, initial_input: Any) -> ConvergentResult:
        for round in range(self._max_rounds):
            output = await self._execute(initial_input)
            result = self._evaluator(output)
            self._state.record(result)

            if self._check_stop():
                return self._finalize()
        return self._finalize()
```

---

## 现有 MAREF 映射已验证

| 现有组件 | 映射到此模板的位置 |
|----------|-----------------|
| `RecursiveEvolutionEngine._check_stop_conditions()` | 停止条件层: gradient_disaster + circuit_breaker 检测 |
| `OscillationFixLoop.detect_and_fix()` | 震荡安全层 |
| `DesktopAgent.SelfHealingExecutor` | 重试→重新解析→降级 的自愈策略 |
| `VerifierConsensus.evaluate()` | 默认 Evaluator |
| `GovernanceStateMachine` canonical path | 每轮的治理状态跟踪 |

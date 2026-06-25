# MAREF API 文档

## 目录

- [MAREF-Lite 状态机](#maref-lite-状态机)
- [Sidecar 观测器](#sidecar-观测器)
- [DriftGuard 漂移检测](#driftguard-漂移检测)
- [治理覆盖层](#治理覆盖层)
- [混沌工程](#混沌工程)
- [MCP 协议端点](#mcp-协议端点)

---

## MAREF-Lite 状态机

### `GovernanceState`

10 态 Gray Code 治理状态枚举。

```python
class GovernanceState(Enum):
    INIT = 0        # 初始状态
    OBSERVE = 1     # 观测
    ANALYZE = 2     # 分析
    EVALUATE = 3    # 评估
    DECIDE = 4      # 决策
    ACT = 5         # 执行
    VERIFY = 6      # 验证
    STABILIZE = 7   # 稳定
    REPORT = 8      # 报告
    HALT = 9        # 终止
```

### `GovernanceStateMachine`

核心治理状态机，管理 Agent 生命周期。

#### 构造函数

```python
sm = GovernanceStateMachine()
```

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `current_state` | `GovernanceState` | 当前状态 |
| `current_entropy` | `int` | 当前熵值 (0-4) |

#### 方法

**`can_transition(target: GovernanceState) -> bool`**

检查是否可以转换到目标状态（单比特 Gray Code 约束）。

```python
if sm.can_transition(GovernanceState.OBSERVE):
    sm.transition(GovernanceState.OBSERVE)
```

**`transition(target: GovernanceState, reason: str = "") -> bool`**

执行状态转换，触发所有回调。

```python
success = sm.transition(GovernanceState.ANALYZE, reason="data_collected")
```

**`force_stabilize(reason: str = "entropy_threshold") -> bool`**

强制进入 STABILIZE 状态（BFS 路径查找）。

```python
sm.force_stabilize("critical_anomaly")
```

**`force_halt(reason: str = "emergency") -> bool`**

强制进入 HALT 状态。

```python
sm.force_halt("manual_override")
```

**`get_history() -> list[StateTransition]`**

获取完整的状态转换历史。

**`get_entropy_trend() -> dict[str, float]`**

获取熵值趋势统计（mean, max, current）。

**`is_terminal() -> bool`**

检查是否处于终止状态（HALT）。

**`get_valid_next_states() -> list[GovernanceState]`**

获取当前状态允许的所有下一状态。

---

## Sidecar 观测器

### `AgentAdapter`

抽象适配器接口，用于接入不同 Agent 框架。

```python
class MyAdapter(AgentAdapter):
    async def list_agents(self) -> list[AgentId]:
        ...

    async def get_state(self, agent_id: AgentId) -> StateSnapshot | None:
        ...

    async def get_entropy(self, agent_id: AgentId) -> EntropyReading | None:
        ...
```

### `ObservationCollector`

观测收集器，通过适配器轮询 Agent 状态。

#### 构造函数

```python
collector = ObservationCollector(
    adapter=my_adapter,
    buffer_size=1000,      # 环形缓冲区大小
    poll_interval=1.0,     # 轮询间隔（秒）
)
```

#### 方法

**`add_callback(callback: Callable[[Observation], None]) -> None`**

注册新观测回调。

```python
collector.add_callback(lambda obs: print(f"New: {obs}"))
```

**`async collect_once() -> list[Observation]`**

执行单次收集。

**`async run() -> None`**

启动持续收集循环。

**`stop() -> None`**

停止收集循环。

**`get_recent(n: int = 100) -> list[Observation]`**

获取最近的 n 条观测。

---

## DriftGuard 漂移检测

### `compute_drift_metrics`

计算基线与当前权重之间的漂移指标。

```python
from src.drift_guard.metrics import compute_drift_metrics

metrics = compute_drift_metrics(
    baseline_weights=np.array(...),
    current_weights=np.array(...),
    num_bins=100,
)
# Returns: {"kl_divergence": float, "js_divergence": float, "hellinger_distance": float}
```

### `kl_divergence`

KL 散度：D_KL(P || Q)，非对称，衡量信息损失。

```python
from src.drift_guard.metrics import kl_divergence

kl = kl_divergence(p, q, epsilon=1e-10)
```

### `js_divergence`

JS 散度：对称有界变体，范围 [0, ln(2)]。

```python
from src.drift_guard.metrics import js_divergence

js = js_divergence(p, q)
```

### `hellinger_distance`

Hellinger 距离：有界度量，范围 [0, 1]。

```python
from src.drift_guard.metrics import hellinger_distance

h = hellinger_distance(p, q)
```

### `DriftDetectionPipeline`

漂移检测流水线，含人工仲裁门控。

#### 构造函数

```python
from src.drift_guard.types import PipelineConfig

pipeline = DriftDetectionPipeline(
    config=PipelineConfig(
        kl_warning=0.1,
        kl_critical=0.5,
        kl_max=1.0,
        hellinger_warning=0.2,
        hellinger_critical=0.5,
        check_interval_seconds=60.0,
        review_timeout_seconds=300.0,
        reset_cooldown_seconds=60.0,
        reset_on_critical=True,
    )
)
```

#### 方法

**`async check_drift(baseline, current, model, baseline_sig) -> DriftEvent | None`**

执行单次漂移检查。

```python
event = await pipeline.check_drift(
    baseline_weights=base,
    current_weights=curr,
    model=ModelSignature(name="gpt-4", version="1.0"),
    baseline=ModelSignature(name="gpt-4", version="1.0"),
)
if event:
    print(f"Drift: {event.reading.severity}")
```

**`approve_event(event_id: str) -> bool`**

人工批准待审核事件。

**`reject_event(event_id: str) -> bool`**

人工拒绝待审核事件。

**`get_stats() -> dict[str, Any]`**

获取流水线统计信息。

---

## 治理覆盖层

### `GovernanceOverlay`

整合状态机、Sidecar 和 DriftGuard 的中央协调器。

#### 构造函数

```python
overlay = GovernanceOverlay(
    state_machine=GovernanceStateMachine(),
    collector=observation_collector,
    monitor=CompositeMonitor(),
    drift_pipeline=DriftDetectionPipeline(),
)
```

#### 方法

**`async check_drift(baseline, current, model, baseline_sig) -> None`**

执行漂移检查并可能触发状态转换。

**`get_status() -> dict[str, Any]`**

获取当前治理状态。

```python
status = overlay.get_status()
# {
#     "state": "OBSERVE",
#     "entropy": 1,
#     "entropy_trend": {"mean": 1.2, "max": 3, "current": 1},
#     "anomaly_count": 5,
#     "critical_count": 0,
#     "decision_count": 12,
#     "is_terminal": False,
# }
```

**`get_decisions() -> list[GovernanceDecision]`**

获取治理决策历史。

**`async run() -> None`**

启动治理主循环。

```python
await overlay.run()
```

**`stop() -> None`**

停止治理循环。

---

## 混沌工程

### `ChaosInjector`

混沌注入器，用于系统韧性验证。

```python
from tests.chaos.test_chaos_scenarios import ChaosInjector

injector = ChaosInjector(agents=[agent1, agent2])

# 注入熵值尖峰
await injector.inject_entropy_spike(agent1, magnitude=5.0)

# 注入状态振荡
await injector.inject_state_oscillation(agent1, cycles=10)

# 注入消息队列堆积
await injector.inject_message_queue_buildup(agent1, count=1000)

# 注入网络延迟
await injector.inject_network_latency(agent1, delay_ms=5000)

# 注入模型漂移
await injector.inject_model_drift(agent1, drift_magnitude=0.8)
```

---

## 配置示例

### 完整初始化

```python
import asyncio
from src.maref_lite.governance import GovernanceOverlay
from src.maref_lite.state_machine import GovernanceStateMachine
from src.sidecar.collector import ObservationCollector, MockAgentAdapter
from src.sidecar.monitor import CompositeMonitor
from src.drift_guard.pipeline import DriftDetectionPipeline
from src.drift_guard.types import PipelineConfig

async def main():
    # 创建组件
    adapter = MockAgentAdapter(num_agents=3)
    collector = ObservationCollector(adapter)
    monitor = CompositeMonitor()
    pipeline = DriftDetectionPipeline(PipelineConfig())

    # 创建治理覆盖层
    overlay = GovernanceOverlay(
        state_machine=GovernanceStateMachine(),
        collector=collector,
        monitor=monitor,
        drift_pipeline=pipeline,
    )

    # 启动
    await overlay.run()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 类型参考

### `StateSnapshot`

```python
@dataclass
class StateSnapshot:
    agent_id: AgentId
    timestamp: float
    state: AgentState      # IDLE | RUNNING | ERROR | TERMINATED
    current_task: str
    task_progress: float   # 0.0 - 1.0
    pending_messages: int
```

### `Observation`

```python
@dataclass
class Observation:
    obs_type: ObservationType   # STATE_SNAPSHOT | ENTROPY_METRIC | DRIFT_EVENT
    payload: Any
    source: str
```

### `DriftEvent`

```python
@dataclass
class DriftEvent:
    event_id: str
    timestamp: datetime
    reading: DriftReading
    action_taken: DriftAction
    gate_status: GateStatus
    reason: str
    resolved: bool = False
    resolution_time: datetime | None = None
```

---

## MCP 协议端点

MAREF Sidecar 提供 MCP (Model Context Protocol) 端点，支持 AI Agent 发现和调用治理能力。

### MCP 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/mcp` | POST | MCP JSON-RPC 处理器 |
| `/api/mcp/.well-known` | GET | MCP 能力发现 |

### MCP 协议版本

- `protocol`: `mcp`
- `version`: `2024-11-05`
- `serverInfo`: `MAREF Sidecar`

### 支持的工具 (22+)

| 工具名 | 描述 | 参数 |
|--------|------|------|
| `maref_observe_agent` | 观测指定 Agent 状态 | `agent_id: string` |
| `maref_read_entropy` | 读取 Agent 熵值 | `agent_id: string` |
| `maref_read_observations` | 读取最近观测数据 | `count: integer` |
| `maref_read_anomalies` | 读取最近异常 | `count: integer` |
| `maref_compliance_check` | 合规检查 | `agent_id, action` |
| `maref_ingest_signal` | 注入外部信号 | `signal_type, payload, source` |
| `maref_list_agents` | 列举所有已注册 Agent | — |
| `maref_get_snapshot` | 获取完整状态快照 | `agent_id: string` |
| `maref_health_check` | Sidecar 健康检查 | `detail: boolean` |
| `maref_get_correlation` | 获取关联数据 | `source: string` |
| `maref_migrate` | Agent 状态迁移 | `agent_id, target_state` |

### MCP 调用示例

```python
import httpx

# 列举工具
response = httpx.post("http://localhost:8000/api/mcp", json={
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 1,
})
tools = response.json()["result"]["tools"]

# 调用治理工具
response = httpx.post("http://localhost:8000/api/mcp", json={
    "jsonrpc": "2.0",
    "method": "tools/call",
    "id": 2,
    "params": {
        "name": "maref_compliance_check",
        "arguments": {
            "agent_id": "agent-1",
            "action": "read_file",
        },
    },
})
result = response.json()["result"]
```

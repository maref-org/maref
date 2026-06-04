# Harness Engineering 工程实施方案

> **版本**: v1.0 | **日期**: 2026-06-04
> **基线**: MAREF v0.30.0-GA, openclaw
> **规划依据**: PERCV 研究报告 (2026-06-03)
> **文件结构**: `harness-plan/` — task_plan.md（本文件）+ findings.md（架构决策）+ progress.md（跨会话进度）

---

## 总体策略

从现有 `src/maref/stress/` 的三个 Harness（StressHarness、DistributedStressHarness、EmergenceHarness）出发，逐层向外构建。每个 Phase 独立可交付，可以在单独的 Claude Code 会话中完成。

```
Phase 0: 存量复用 ─── 现有代码快速包装 → maref harness CLI 命令
    ↓
Phase 1: 生命周期 ─── BaseAgentHarness + 治理深度集成
    ↓
Phase 2: Hook 系统 ─── 运行时权限 + 生命周期钩子
    ↓
Phase 3: 上下文管理 ─── 懒加载 + 压缩 + 预算控制
    ↓
Phase 4: 工具标准化 ─── ToolOrchestrator + MCP 协议
    ↓
Phase 5: 多Agent ─── 协调器 + 任务分解归并
    ↓
Phase 6: 遥测与进化 ─── 遥测管道 + 递归引擎对接
    ↓
Phase 7: 服务化 ─── API + Docker + 多模型适配
```

---

## Phase 0: 存量复用 — 现有 StressHarness 快速包装

**目标**: 零新功能，把现有 3 个 Harness 包装为可调用的 CLI 命令。
**估算**: 1 次会话（~2h）
**依赖**: 无（纯包装）

### Task 0.0: 创建 `execution/harness/` 包

新建 `src/maref/execution/` 包（当前不存在 execution 目录）：

```
src/maref/execution/
├── __init__.py                  # 包导出
├── harness/
│   ├── __init__.py              # 导出 BaseHarness, HarnessConfig, HarnessResult
│   ├── base.py                  # BaseHarness 抽象类（生命周期接口）
│   ├── types.py                 # HarnessConfig, HarnessResult, HarnessStatus
│   └── exceptions.py            # HarnessException 体系
```

**接口定义** (`base.py`):
```python
class BaseHarness(ABC):
    @abstractmethod
    def configure(self, config: HarnessConfig) -> None: ...
    @abstractmethod
    def run(self, round_id: str = "") -> HarnessResult: ...
    def preflight(self) -> list[str]: ...         # 可选：执行前检查
    def validate(self, result: HarnessResult) -> bool: ...  # 可选：结果验证
```

**验收**: `src/maref/execution/` 包可 import，`BaseHarness` 抽象类可被继承。

### Task 0.1: StressHarnessAdapter

新建：
```
src/maref/execution/harness/adapters/
├── __init__.py                    # 导出三个 Adapter
├── stress_adapter.py              # StressHarness → BaseHarness
├── distributed_adapter.py         # DistributedStressHarness → BaseHarness
└── emergence_adapter.py           # EmergenceHarness → BaseHarness
```

**做法**: 每个 Adapter 继承 `BaseHarness`，内部持有对应 Harness 实例，`run()` 委托给内部实例。

**验收**: 三个 Adapter 可实例化、可运行，结果类型统一为 `HarnessResult`。

### Task 0.2: CLI 子命令 `maref harness`

在 `src/maref_lite/cli.py` 新增 `harness_app` 子命令组：

```
maref harness stress --level L3 --duration 2          # StressHarness
maref harness distributed --workers 4 --level L2       # DistributedStressHarness
maref harness emergence --scenario conflict --runs 10  # EmergenceHarness
maref harness list                                     # 列出可用 Harness
```

**验收**: `maref harness --help` 显示完整子命令，所有三个 Harness 可从 CLI 调用。

### Task 0.3: 测试与验证

```bash
maref harness stress --level L1 --duration 0.1    # 快速冒烟
maref harness distributed --workers 2 --level L1 --rounds 3
maref harness emergence --runs 5
```

**验收**: 三条命令全部通过，输出格式统一（Rich table + JSON）。

---

## Phase 1: 生命周期标准化 — UnifiedHarness

**目标**: 构建 UnifiedHarness 完整生命周期，集成 Governance 状态机和 CircuitBreaker。
**估算**: 1-2 次会话
**依赖**: Phase 0

### Task 1.1: UnifiedHarness 实现

新建 `src/maref/execution/harness/unified.py`：

```
UnifiedHarness(BaseHarness)
├── 生命周期状态: INIT → PREFLIGHT → READY → RUNNING → VALIDATING → REPORTING → DONE
│   (单向推进，异常时 → FAILED)
├── configure(config) — 设置参数
├── preflight() → list[str] — 环境检查，返回警告列表
├── run(round_id) → HarnessResult — 执行主逻辑
└── validate(result) → bool — 结果自检
```

**核心逻辑**: `run()` 内部维护生命周期状态转换 + 异常处理。

**验收**: UnifiedHarness 可独立运行，生命周期状态转换可观测。

### Task 1.2: Governance 状态机集成

新建 `src/maref/execution/harness/governance_bridge.py`：

```python
class GovernanceBridge:
    """在每个生命周期阶段检查治理状态机。"""
    def __init__(self, state_machine: GovernanceStateMachine): ...
    def check(self, lifecycle_stage: str) -> bool:
        """当前治理状态是否允许此阶段执行。"""
    def record(self, lifecycle_stage: str, result: bool): ...
```

**集成方式**:
- PREFLIGHT → 检查 state_machine.current_state 是否为 OBSERVE/ANALYZE
- RUNNING → 每次 step 前检查 CircuitBreaker 状态
- 违规时触发 state_machine.transition(HALT)

**验收**: UnifiedHarness 在 HALT 状态下拒绝执行，CircuitBreaker OPEN 时自动中止。

### Task 1.3: Orchestration 集成

新建 `src/maref/execution/harness/orchestration_bridge.py`：

```python
class OrchestrationBridge:
    """包装 TaskGraph + PlanExecutor。"""
    def decompose(self, task: str) -> TaskGraph: ...
    def execute(self, graph: TaskGraph) -> dict: ...
```

**集成方式**: 现有 `orchestration/task_graph.py` 和 `orchestration/plan_executor.py` 的代理层。

**验收**: UnifiedHarness 可通过 OrchestrationBridge 执行任务图。

### Task 1.4: 测试

```bash
maref harness run --config unified_config.yaml   # 完整生命周期运行
maref harness run --halt-test                    # 验证 HALT 阻断
```

**验收**: 生命周期全流程通过，HALT 阻断验证通过。

---

## Phase 2: Hook 系统与运行时权限

**目标**: 让 Harness 生命周期触发 Hook 事件，集成运行时权限控制。
**估算**: 1 次会话
**依赖**: Phase 1

### Task 2.1: Harness 生命周期钩子

新建 `src/maref/execution/harness/hooks.py`：

```python
# 注册到现有的 HookRegistry
HARNESS_TOPICS = [
    "harness.start",      # UnifiedHarness.run() 开始
    "harness.preflight",  # preflight 检查
    "harness.step",       # 每个执行步骤
    "harness.stop",       # 正常停止
    "harness.fail",       # 异常失败
    "harness.validate",   # 验证阶段
]
```

**集成方式**: 使用 `recursive/hook_registry.py` 的 `register(topic, handler)` 接口。

**验收**: `HookRegistry` 中包含所有 6 个 `harness.*` 主题，hook handler 可被触发。

### Task 2.2: 运行时权限 Hook

新建 `src/maref/execution/harness/permission_hooks.py`：

```python
class PermissionHook:
    """运行时权限检查钩子，在每次 tool call 前触发。"""
    def __init__(self, registry: HookRegistry):
        registry.register("harness.tool_call", self._check_permission)
    
    def _check_permission(self, event_data: dict) -> HookResult:
        # 读取 governance/ 的权限配置
        # 返回 PASS / BLOCK
```

**集成方式**: 在 UnifiedHarness 每次 tool_call 前调用 HookRegistry。

**验收**: 工具调用可通过 Hook 被允许/阻止，阻止时返回有意义的错误消息。

### Task 2.3: 审计日志集成

在 `src/maref/execution/harness/audit_logger.py` 中实现：
- 每个生命周期阶段写入审计日志
- 使用现有 `governance/audit.py` 的 HMAC-SHA256 签名

**验收**: `maref harness run` 执行后可在审计日志中查到完整事件链。

---

## Phase 3: 上下文管理

**目标**: 实现 Knowledge-on-Demand 懒加载和 Context Compression。
**估算**: 1 次会话
**依赖**: Phase 1

### Task 3.1: LazyContextLoader

新建 `src/maref/execution/context/lazy_loader.py`：

```python
class LazyContextLoader:
    """按需加载上下文，避免启动时上下文爆炸。"""
    def load(self, key: str) -> str: ...       # 实际使用时才加载
    def prefetch(self, keys: list[str]): ...    # 预加载提示
    def purge(self, key: str): ...              # 释放
```

**验收**: 100 个上下文项中只实际加载被访问的 <10 项，未访问项零加载。

### Task 3.2: ContextCompressor

新建 `src/maref/execution/context/compressor.py`：

```python
class ContextCompressor:
    """智能截断：优先保留工具定义，压缩历史对话。"""
    def compress(self, context: str, budget: int) -> str: ...
    def estimate_tokens(self, text: str) -> int: ...
```

**验收**: 压缩后 token 数 ≤ budget，关键工具定义不被截断。

### Task 3.3: UnifiedHarness 集成

在 UnifiedHarness 中集成 LazyContextLoader + ContextCompressor：
- `configure()` 时设置 token budget
- `run()` 中使用 loader 加载上下文
- 超出 budget 时自动压缩

**验收**: UnifiedHarness 运行时 token 消耗符合 budget 设置。

---

## Phase 4: 工具标准化

**目标**: 统一工具调用接口，支持 MCP 协议。
**估算**: 1-2 次会话
**依赖**: Phase 2

### Task 4.1: ToolOrchestrator

新建 `src/maref/execution/tools/orchestrator.py`：

```python
class ToolOrchestrator:
    """统一工具调度：发现 → 选择 → 执行 → 结果处理。"""
    def register(self, tool: Tool) -> None: ...
    def execute(self, name: str, params: dict) -> ToolResult: ...
    def list_tools(self) -> list[ToolSpec]: ...
```

**验收**: 可注册/执行/列出工具，与现有 `governance/` 的权限系统连接。

### Task 4.2: MCP 客户端

新建 `src/maref/execution/tools/mcp_client.py`：

```python
class MCPClient:
    """MCP 协议客户端，连接外部 MCP 服务。"""
    def connect(self, url: str) -> None: ...
    def call_tool(self, name: str, args: dict) -> ToolResult: ...
    def list_tools(self) -> list[ToolSpec]: ...
```

**验收**: 可连接 MCP 服务，调用远程工具。

### Task 4.3: Harness 集成

在 UnifiedHarness 中添加 ToolOrchestrator 作为工具调用入口，替换当前散落的工具调用。

**验收**: UnifiedHarness 的所有工具调用通过 ToolOrchestrator 统一管理。

---

## Phase 5: 多Agent 协调

**目标**: 多Agent 生命周期管理 + 任务分解归并。
**估算**: 1-2 次会话
**依赖**: Phase 1

### Task 5.1: MultiAgentCoordinator

新建 `src/maref/execution/multi_agent/coordinator.py`：

```python
class MultiAgentCoordinator:
    """多Agent 协调器，管理多个 SubHarness 实例。"""
    def add_agent(self, harness: BaseHarness, role: str): ...
    def run_all(self, task: str) -> list[HarnessResult]: ...
    def aggregate(self, results: list[HarnessResult]) -> dict: ...
```

**验收**: 可创建 3 个不同角色的 SubHarness 并协调执行。

### Task 5.2: 任务分解

新建 `src/maref/execution/multi_agent/decomposer.py`：

```python
class HarnessTaskDecomposer:
    """把大任务分解为 Agent-子任务映射。"""
    def decompose(self, task: str, agents: list[str]) -> dict[str, str]: ...
    def merge(self, results: dict[str, HarnessResult]) -> HarnessResult: ...
```

**复用**: 策略上复用 `orchestration/task_graph.py` + `orchestration/decomposer.py`。

**验收**: 分解+执行+归并全链路可跑通。

---

## Phase 6: 遥测与进化对接

**目标**: Harness 执行数据喂入递归自演化引擎。
**估算**: 1 次会话
**依赖**: Phase 1

### Task 6.1: HarnessTelemetryCollector

新建 `src/maref/execution/telemetry/collector.py`：

```python
class HarnessTelemetryCollector:
    def record(self, event: TelemetryEvent) -> None: ...
    def report(self) -> TelemetryReport:
        """生成格式化的遥测报告，供递归引擎消费。"""
```

**TelemetryEvent 字段**: timestamp、harness_id、lifecycle_stage、latency_ms、error、tool_calls、token_count

**验收**: UnifiedHarness 运行时每秒记录遥测事件，可生成汇总报告。

### Task 6.2: 递归引擎数据源

在 `src/maref/execution/telemetry/evolution_feed.py` 中实现：

```python
class EvolutionDataFeed:
    """把 Harness 遥测适配为 recursive/self_observer.py 的输入格式。"""
```

**集成方式**: 数据写入 `recursive/self_observer.py` 的观察队列，触发自治愈/自优化循环。

**验收**: Harness 遥测数据出现在 recursive engine 的观察日志中。

---

## Phase 7: 服务化部署

**目标**: Harness 可作为独立服务运行。
**估算**: 1 次会话
**依赖**: Phase 1

### Task 7.1: FastAPI Harness 服务

新建 `src/maref/execution/server.py`：

```
POST /harness/run          # 执行 Harness 任务
GET  /harness/status       # Harness 状态
GET  /harness/results/{id} # 查询结果
POST /harness/stop/{id}    # 停止任务
```

**验收**: 服务启动后可通过 HTTP 调用 UnifiedHarness。

### Task 7.2: Docker 化

```
execution/Dockerfile          # 基于现有 Dockerfile 扩展
execution/docker-compose.yml  # + Redis (结果缓存)
```

**验收**: `docker-compose up` 启动 Harness 服务，API 可达。

### Task 7.3: 多模型适配器

新建 `src/maref/execution/adapters/` — 适配不同 LLM 提供商的 Harness 调用方式。

**验收**: 至少适配 2 个不同的模型调用方式。

---

## 会话分配建议

| 会话 | Phase | 核心产出 | 代码量估算 |
|------|-------|---------|-----------|
| Session 1 | Phase 0 | `execution/` 包 + CLI + 3 Adapters | ~400 行 |
| Session 2 | Phase 1 | UnifiedHarness + GovernanceBridge | ~500 行 |
| Session 3 | Phase 1+2 | OrchestrationBridge + Hooks | ~350 行 |
| Session 4 | Phase 3 | Context Load/Compress | ~300 行 |
| Session 5 | Phase 4 | ToolOrchestrator + MCP | ~400 行 |
| Session 6 | Phase 5 | MultiAgentCoordinator | ~400 行 |
| Session 7 | Phase 6 | Telemetry + Evolution Feed | ~300 行 |
| Session 8 | Phase 7 | FastAPI + Docker | ~200 行 |

每个会话独立启动，通过 `progress.md` 接力。

# Harness Engineering 架构决策与发现

> **版本**: v1.0 | **日期**: 2026-06-04
> **关联**: task_plan.md

---

## 一、现有可复用代码

### 1.1 StressHarness（`src/maref/stress/stress_harness.py`）

可以直接包装为 BaseHarness 的成熟代码：

| 能力 | 复用方式 | 改造量 |
|------|---------|-------|
| `set_level(L1-L5)` | 直接代理 | 0 |
| 6 轴压力配置 | 通过 `configure()` 透传 | 少 |
| CircuitBreaker + StateMachine 依赖 | 已导入，无需额外安装 | 0 |
| `run()` → `StressResult` | 完整结果涵盖 latency/resilience/errors | 0 |
| latency_tracker（P50/P99/P99.9） | 嵌入 UnifiedHarness | 少 |

**注意**: StressHarness 的 `run()` 是模拟压力测试，不是真实 Agent 执行。Phase 1 的 UnifiedHarness 需要新增真实执行路径。

### 1.2 DistributedStressHarness（`src/maref/stress/distributed_harness.py`）

| 能力 | 复用方式 |
|------|---------|
| multiprocessing.Pool 并发 | Adapter 直接代理 |
| `run_progressive_load()` | 多 Worker 渐变负载 |
| `aggregate()` | 结果聚合统计 |

### 1.3 EmergenceHarness（`src/maref/stress/emergence_harness.py`）

| 能力 | 复用方式 |
|------|---------|
| Temporal perturbation | 冲突一致性检测 |
| Byzantine tampering | 安全违规模拟 |
| `EmergenceReport` | 一致性率指标 |

### 1.4 基础设施模块

| 模块 | 位置 | 在 Harness 中的用途 |
|------|------|-------------------|
| `GovernanceStateMachine` | `governance/state_machine.py` | 生命周期阶段治理检查 |
| `CircuitBreaker` | `governance/circuit_breaker.py` | 执行中断言+自恢复 |
| `HookRegistry` | `recursive/hook_registry.py` | Harness 生命周期钩子注册 |
| `HookChain` | `recursive/hook_chain.py` | 钩子链执行+超时控制 |
| `TaskGraph` | `orchestration/task_graph.py` | 任务分解图 |
| `PlanExecutor` | `orchestration/plan_executor.py` | 计划执行引擎 |
| `audit_logger` | `maref/integration/audit_logger.py` | 审计日志签名 |
| `ResilienceEvaluatorV2` | `recursive/resilience_v2.py` | 弹性评分 |
| `RealLatencyTracker` | `stress/real_latency.py` | 延迟追踪 |

---

## 二、架构决策

### ADR-1: 包位置

**决策**: 在 `src/maref/` 下新建 `execution/` 包，不放在 `internal/execution/harness/`。

**理由**:
- `internal/` 目录不含 Python 包（无 `__init__.py`）
- `src/maref/` 下的模块可直接被 `maref` CLI 导入
- 符合现有 `governance/`、`orchestration/`、`recursive/` 的组织方式
- 未来需要发布时，`execution/` 自然成为 `maref[execution]` optional dep

**后果**:
- `internal/execution/harness/` 不要了，内容移到 `src/maref/execution/harness/`
- import 路径：`from maref.execution.harness import BaseHarness`

### ADR-2: 生命周期状态机 vs 治理状态机

**决策**: Harness 生命周期是独立状态机，不共用户治理状态机的 10 态 Gray Code。

**理由**:
- 治理状态机（INIT→OBSERVE→...→HALT）描述**系统治理状态**
- Harness 生命周期（INIT→PREFLIGHT→...→DONE）描述**一次执行流程**
- 两者正交：同一治理状态下可多次执行 Harness
- 混淆会导致治理状态机被执行流程污染

**关系**: Harness 生命周期**查询**治理状态机（"当前治理状态允许我执行吗？"），但不修改它。

### ADR-3: Hook 复用 vs 自建

**决策**: 直接复用 `recursive/hook_registry.py` + `recursive/hook_chain.py`。

**理由**:
- HookRegistry 已有 topic 注册、优先级排序、handler 管理
- HookChain 已有超时控制、结果聚合、CHAIN_BREAK 机制
- 只需注册新 topic（`harness.*`），零基础设施改造

### ADR-4: StressHarness 改与不改

**决策**: Harness Adapter 包装 StressHarness，**不修改 StressHarness 源码**。

**理由**:
- StressHarness 是稳定的测试工具，改它可能影响 5,651 个测试
- Adapter 模式保持向后兼容
- UnifiedHarness 与 StressHarness 并行存在，互不干扰

### ADR-5: CLI 组织

**决策**: `maref harness` 作为顶级子命令组，平行于 `maref desktop`、`maref audit`。

**理由**:
- 用户心智模型：`maref <模块> <动作>`
- 与 PERCV 报告中的 "Harness 是一等公民" 定位一致
- 便于后续 Phase 扩展子命令

---

## 三、演进策略

### Phase 0→1 过渡

Phase 0 创建的 `execution/harness/` 包是基础骨架。Phase 1 会在其中添加 `unified.py` 和 `governance_bridge.py`，不破坏 Phase 0 的接口。

### 向后兼容承诺

| 接口 | 承诺 |
|------|------|
| `BaseHarness` 抽象类 | Phase 1-7 只增方法，不改签名 |
| `stress_adapter.py` | 永远可用，不会因 UnifiedHarness 过时 |
| `maref harness stress` CLI | 保持稳定 |

### 废弃策略

Phase 0 的 Adapter 模式是"包装不替换"。即使 UnifiedHarness 成熟后：
- `StressHarness` 本身继续作为轻量级测试工具存在
- `maref harness stress` CLI 保留
- `DistributedStressHarness` 和 `EmergenceHarness` 同理

---

## 四、风险评估

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| `execution/harness/` 与现有包名冲突 | 低 | 10% | 已在 src/maref/ 下确认无同名 |
| GovernanceStateMachine 接口变更 | 中 | 30% | Adapter 层隔离变动 |
| HookRegistry 并发问题 | 中 | 20% | HookChain 已有超时控制 |
| StressHarness run() 行为变更 | 低 | 5% | Adapter 模式，不改源码 |
| 与服务化需求冲突 | 低 | 15% | 7 个 Phase 可独立决策 |

---

## 五、关键文件清单

**新建文件（预计 ~2,850 行）**:

```
Phase 0  src/maref/execution/__init__.py              ~10行
Phase 0  src/maref/execution/harness/__init__.py       ~30行
Phase 0  src/maref/execution/harness/base.py           ~80行
Phase 0  src/maref/execution/harness/types.py          ~80行
Phase 0  src/maref/execution/harness/exceptions.py     ~30行
Phase 0  src/maref/execution/harness/adapters/__init__.py    ~30行
Phase 0  src/maref/execution/harness/adapters/stress_adapter.py       ~60行
Phase 0  src/maref/execution/harness/adapters/distributed_adapter.py  ~50行
Phase 0  src/maref/execution/harness/adapters/emergence_adapter.py    ~50行
Phase 1  src/maref/execution/harness/unified.py              ~200行
Phase 1  src/maref/execution/harness/governance_bridge.py     ~80行
Phase 1  src/maref/execution/harness/orchestration_bridge.py  ~100行
Phase 2  src/maref/execution/harness/hooks.py              ~60行
Phase 2  src/maref/execution/harness/permission_hooks.py    ~100行
Phase 2  src/maref/execution/harness/audit_logger.py        ~80行
Phase 3  src/maref/execution/context/__init__.py            ~10行
Phase 3  src/maref/execution/context/lazy_loader.py         ~120行
Phase 3  src/maref/execution/context/compressor.py          ~100行
Phase 4  src/maref/execution/tools/__init__.py              ~10行
Phase 4  src/maref/execution/tools/orchestrator.py          ~150行
Phase 4  src/maref/execution/tools/mcp_client.py            ~120行
Phase 5  src/maref/execution/multi_agent/__init__.py        ~10行
Phase 5  src/maref/execution/multi_agent/coordinator.py     ~150行
Phase 5  src/maref/execution/multi_agent/decomposer.py      ~120行
Phase 6  src/maref/execution/telemetry/__init__.py          ~10行
Phase 6  src/maref/execution/telemetry/collector.py         ~100行
Phase 6  src/maref/execution/telemetry/evolution_feed.py    ~80行
Phase 7  src/maref/execution/server.py                      ~150行
Phase 7  execution/Dockerfile                               ~30行
Phase 7  execution/docker-compose.yml                       ~30行
```

**修改文件**:
```
Phase 0  src/maref_lite/cli.py   (+ harness_app, ~80行)
Phase 2  test 或 config           (+ Harness hook topic 注册)
Phase 6  recursive/self_observer.py  (+ 遥测数据源, ~30行)
```

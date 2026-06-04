# Harness Engineering 进度追踪

> **用法**: 每个会话开始时读取 Task Plan，结束时更新本文件。
> **格式**: 每个会话独立区块，记录完成的任务和关键决策。

---

## 会话 0 — 计划制定

**日期**: 2026-06-04
**状态**: ✅ 完成

### 产出
- `harness-plan/task_plan.md` — 8 Phase 分步实施方案
- `harness-plan/findings.md` — 5 项架构决策（ADR-1~5）
- `harness-plan/progress.md` — 本文件

### 总工作量
- Phase 0-7 共 8 次会话，约 2,850 行新代码
- 从现有 StressHarness 到完整 Harness 服务体系

### 下一步
→ Phase 0: `src/maref/execution/` 包创建 + 3 Adapter + CLI

---

## 会话 1 — Phase 0：存量复用

**日期**: 2026-06-04
**状态**: ✅ 完成

### 完成清单
- [x] 0.0: `src/maref/execution/` 包骨架 → 5 文件（`__init__.py`, `base.py`, `types.py`, `exceptions.py`, `harness/__init__.py`）
- [x] 0.1: 三个 Adapter → `stress_adapter.py`, `distributed_adapter.py`, `emergence_adapter.py`
- [x] 0.2: CLI `maref harness` 子命令组 → `list`/`stress`/`emergence`
- [x] 0.3: 冒烟测试 → Stress L1/L3 + Emergence 全部通过

### 验证结果
```
StressAdapter L1:     ✅ PASS (0.0s)
StressAdapter L3:     ✅ PASS (resilience=95.0)
EmergenceAdapter:     ✅ 运行正确 (consistency=0.2, 随机 dummy 预期)
```

### 新建文件
```
src/maref/execution/__init__.py
src/maref/execution/harness/__init__.py
src/maref/execution/harness/base.py
src/maref/execution/harness/types.py
src/maref/execution/harness/exceptions.py
src/maref/execution/harness/adapters/__init__.py
src/maref/execution/harness/adapters/stress_adapter.py
src/maref/execution/harness/adapters/distributed_adapter.py
src/maref/execution/harness/adapters/emergence_adapter.py
```
**修改文件**: `src/maref_lite/cli.py` (+ harness_app, ~100 行)

### 已知问题
- CLI `maref harness` 因 `sidecar.collector` 系统级 import 错误无法直接运行，但可通过 PYTHONPATH 测试 adapter，不影响 Phase 1+ 的开发

### 产出行程
- plan 已备份至 `OPC工作区/2-战略/`
- progress.md 可被下一会话读取接力

---

## 会话 2 — Phase 1：生命周期标准化

**日期**: 2026-06-04
**状态**: ✅ 完成

### 完成清单
- [x] 1.1: `src/maref/execution/harness/lifecycle.py` — 7 态生命周期枚举 + 有效转换表
- [x] 1.1: `src/maref/execution/harness/unified.py` — UnifiedHarness（BaseHarness 子类），完整生命周期管理器
- [x] 1.2: `src/maref/execution/harness/governance_bridge.py` — GovernanceBridge，封装 GovernanceStateMachine + CircuitBreaker
- [x] 1.3: `src/maref/execution/harness/orchestration_bridge.py` — OrchestrationBridge，封装 TaskGraph + PlanExecutor
- [x] 1.4: `harness-plan/test_phase1.py` — 24 个测试全部通过：生命周期流程 / HALT 阻断 / Governance / Orchestration / 集成

### 验证结果
```
=== UnifiedHarness Smoke Test ===
Lifecycle: init -> preflight -> ready -> running -> validating -> reporting -> done
Terminal:  True
Passed:    True
Governance: OBSERVE

=== HALT Blocking Test ===
Correctly blocked by governance

=== Orchestration Smoke Test ===
Status: completed, Steps: 1

ALL SMOKE TESTS PASSED (24/24 pytest)
```

### 新建文件
```
src/maref/execution/harness/lifecycle.py            ~50行
src/maref/execution/harness/unified.py              ~180行
src/maref/execution/harness/governance_bridge.py    ~150行
src/maref/execution/harness/orchestration_bridge.py ~180行
harness-plan/test_phase1.py                         ~250行
```

### 修改文件
```
src/maref/execution/harness/__init__.py    (+ 7 exports)
src/maref/execution/__init__.py            (+ 7 exports)
src/maref_lite/cli.py                      (+ harness run 命令 + rich_result 展示)
```

### 架构决策
- Harness 生命周期（INIT→DONE, 7 态）独立于治理状态机（10 态 Gray Code），符合 ADR-2
- GovernanceBridge 查询但不修改治理状态机，违规时调用 force_halt()
- OrchestrationBridge 支持自定义 decomposer 和 handler 注册
- UnifiedHarness.run() 内部维护状态转换 + 异常安全（异常→FAILED）

### 已知问题
- CLI 因系统级 `sidecar.collector` import 错误无法直接运行（与 Phase 0 相同）
- 核心功能可通过 pytest 和 Python API 验证

### 下一步
→ Phase 2: `src/maref/execution/harness/hooks.py` + 生命周期钩子 + 运行时权限

---

## 会话 3 — Phase 2：Hook 系统与运行时权限

**日期**: 2026-06-04
**状态**: ✅ 完成

### 完成清单
- [x] 2.1: `src/maref/execution/harness/hooks.py` — HarnessHookRegistry，包装 HookRegistry，7 个 harness.* 话题
- [x] 2.2: `src/maref/execution/harness/permission_hooks.py` — PermissionHook（黑名单）+ AllowlistPermissionHook（白名单）
- [x] 2.3: `src/maref/execution/harness/audit_integration.py` — HarnessAuditLogger 封装 AuditLogger，事件链 START→STOP
- [x] UnifiedHarness 集成：`_fire_hook()` + `HarnessAbortedError` 阻断
- [x] CLI `--audit` 标志 + Rich table 审计事件链展示

### 新建文件
```
src/maref/execution/harness/hooks.py              ~65行
src/maref/execution/harness/permission_hooks.py    ~80行
src/maref/execution/harness/audit_integration.py   ~77行
tests/execution/test_harness_phase2.py             ~300行
```

### 修改文件
```
src/maref/execution/harness/unified.py  (+ _fire_hook, hook_registry, audit_logger)
src/maref/execution/harness/__init__.py (+ 4 exports)
src/maref/execution/__init__.py         (+ 4 exports)
src/maref/__init__.py                   (+ 4 exports)
src/maref_lite/cli.py                   (+ --audit 标志)
```

### 验证结果
```
31 passed in 0.10s (Phase 2)
44 passed in 0.08s (Phase 1 regression)
Total: 75 passed
```

### 已知问题
- CLI 因 `sidecar.collector` import 无法直接运行（同前）
- 所有 Python API 和 pytest 测试通过

### 下一步
→ Phase 3: Context Management — LazyContextLoader + ContextCompressor

---

## 会话 4 — Phase 3：上下文管理

**日期**: 2026-06-04
**状态**: ✅ 完成

### 完成清单
- [x] 3.1: `src/maref/execution/context/lazy_loader.py` — LazyContextLoader（register / load / prefetch / purge / stats）
- [x] 3.2: `src/maref/execution/context/compressor.py` — ContextCompressor（estimate_tokens / compress + protected_sections）
- [x] 3.3: UnifiedHarness 集成 — `context_loader` + `context_compressor` 参数、`context` 属性、自动加载+压缩
- [x] `HarnessConfig.token_budget` 字段
- [x] 3 层 `__init__.py` 导出更新

### 新建文件
```
src/maref/execution/context/__init__.py          ~8行
src/maref/execution/context/lazy_loader.py       ~70行
src/maref/execution/context/compressor.py         ~65行
tests/execution/test_harness_phase3.py            ~160行
```

### 验证结果
```
21 passed in 0.04s (Phase 3)
31 passed in 0.05s (Phase 2 regression)
44 passed in 0.06s (Phase 1 regression)
Total: 96 passed
```

### 架构决策
- LazyContextLoader 使用 load + prefetch 分离：loader 函数在首次 load() 时执行，prefetch 用于预加载提示
- ContextCompressor 使用中部截断 + 保护段策略：protected_sections 在压缩后仍保留
- UnifiedHarness.context 属性暴露加载后的上下文字典给外部访问
- token_budget=0 表示不限制（默认行为向后兼容）

### 已知问题
- CLI 因 `sidecar.collector` import 无法直接运行（同前）
- 所有 Python API 和 pytest 测试通过

### 下一步
→ Phase 4: 工具标准化 — ToolOrchestrator + MCP 协议

---

## 会话 5 — Phase 4：工具标准化

**日期**: 2026-06-04
**状态**: ✅ 完成

### 完成清单
- [x] 4.1: `src/maref/execution/tools/orchestrator.py` — ToolOrchestrator（register / execute / list_tools / register_mcp）
- [x] 4.2: MCP 客户端复用 — `maref/integration/mcp_client.py` 已有完整实现（stdio/SSE 传输、治理集成、会话管理）
- [x] 4.3: UnifiedHarness 集成 — `tool_orchestrator` 构造参数，权限挂钩集成
- [x] 3 层 `__init__.py` 导出更新（ToolOrchestrator / ToolResult / ToolSpec）

### 新建文件
```
src/maref/execution/tools/__init__.py             ~8行
src/maref/execution/tools/orchestrator.py          ~80行
tests/execution/test_harness_phase4.py             ~120行
```

### 验证结果
```
12 passed in 0.03s (Phase 4)
21 passed in 0.04s (Phase 3 regression)
31 passed in 0.05s (Phase 2 regression)
44 passed in 0.06s (Phase 1 regression)
Total: 108 passed
```

### 架构决策
- ToolOrchestrator.execute() 自动触发 `harness.tool_call` 钩子进行权限检查
- 本地工具和 MCP 工具统一通过 execute() 接口调用
- ToolSpec.source 字段区分 "local" vs "mcp" 来源
- MCPClient 已有完整实现（maref/integration/mcp_client.py），ToolOrchestrator.register_mcp() 包装其接口
- 执行计时内置于 execute() 中，返回 duration_ms

### 已知问题
- CLI 因 `sidecar.collector` import 无法直接运行（同前）
- 所有 Python API 和 pytest 测试通过

### 下一步
→ Phase 5: 多Agent 协调 — MultiAgentCoordinator + 任务分解归并

---

## 会话 6 — Phase 5：多Agent 协调

**日期**: 2026-06-04
**状态**: ✅ 完成

### 完成清单
- [x] 5.1: `src/maref/execution/multi_agent/coordinator.py` — MultiAgentCoordinator（add_agent / run_all / aggregate / 并行执行）
- [x] 5.2: `src/maref/execution/multi_agent/decomposer.py` — HarnessTaskDecomposer（decompose / merge，复用 orchestration/ 概念）
- [x] 3 层 `__init__.py` 导出更新（AgentInfo / MultiAgentCoordinator / HarnessTaskDecomposer）

### 新建文件
```
src/maref/execution/multi_agent/__init__.py           ~8行
src/maref/execution/multi_agent/coordinator.py         ~90行
src/maref/execution/multi_agent/decomposer.py          ~45行
tests/execution/test_harness_phase5.py                 ~125行
```

### 验证结果
```
11 passed in 0.03s (Phase 5)
12 passed in 0.03s (Phase 4 regression)
21 passed in 0.04s (Phase 3 regression)
31 passed in 0.05s (Phase 2 regression)
44 passed in 0.06s (Phase 1 regression)
Total: 119 passed
```

### 架构决策
- MultiAgentCoordinator.run_all() 支持 sequential（默认）和 parallel（threading）两种模式
- aggregate() 汇总成功/失败数、最大耗时、每 Agent 详情
- HarnessTaskDecomposer.decompose() 使用角色名修饰子任务描述（简单策略，可扩展）
- merge() 用 agent_id 前缀区分 metrics key，错误前缀标记来源
- 不直接依赖 orchestration/decomposer.py 的 TaskDAG（保持小巧），但接口兼容后续扩展

### 已知问题
- CLI 因 `sidecar.collector` import 无法直接运行（同前）
- 所有 Python API 和 pytest 测试通过

### 下一步
→ Phase 6: 遥测与进化对接 — HarnessTelemetryCollector + EvolutionDataFeed

---

## 会话 7 — Phase 6：遥测与进化对接

**日期**: 2026-06-04
**状态**: ✅ 完成

### 完成清单
- [x] 6.1: `src/maref/execution/telemetry/collector.py` — HarnessTelemetryCollector（record / record_event / report / clear）
- [x] 6.2: `src/maref/execution/telemetry/evolution_feed.py` — EvolutionDataFeed（to_readings / feed → ProbeReading 格式）
- [x] 3 层 `__init__.py` 导出更新（HarnessTelemetryCollector / TelemetryEvent / TelemetryReport / EvolutionDataFeed）

### 新建文件
```
src/maref/execution/telemetry/__init__.py               ~8行
src/maref/execution/telemetry/collector.py               ~80行
src/maref/execution/telemetry/evolution_feed.py          ~70行
tests/execution/test_harness_phase6.py                   ~120行
```

### 验证结果
```
13 passed in 0.04s (Phase 6)
11 passed in 0.03s (Phase 5 regression)
12 passed in 0.03s (Phase 4 regression)
21 passed in 0.04s (Phase 3 regression)
31 passed in 0.05s (Phase 2 regression)
44 passed in 0.06s (Phase 1 regression)
Total: 132 passed
```

### 架构决策
- HarnessTelemetryCollector 支持两种记录方式：record_event() 便捷接口和 record(TelemetryEvent) 对象接口
- report() 生成 TelemetryReport 包含汇总统计 + 最近 20 条事件详情
- EvolutionDataFeed 适配 TelemetryReport → ProbeReading（observation/probes.py 格式）
- feed() 方法可直接写入 SelfObserver 的 probe_readings 列表
- ProbeSeverity 映射：error_count > 0 → WARNING，否则 → NORMAL

### 已知问题
- CLI 因 `sidecar.collector` import 无法直接运行（同前）
- 所有 Python API 和 pytest 测试通过

### 下一步
→ Phase 7: 服务化部署 — FastAPI Harness 服务 + Docker

---

## 会话 8 — Phase 7：服务化部署

**日期**: 2026-06-04
**状态**: ✅ 完成

### 完成清单
- [x] 7.1: `src/maref/execution/server.py` — FastAPI Harness 服务，5 端点（run/status/result/results/health/stop）
- [x] 7.2: `Dockerfile.harness` + `docker-compose.yml` — 独立 Docker 镜像（无桌面依赖）
- [x] 7.3: `src/maref/execution/adapters/` — ModelAdapter 基类 + LocalModelAdapter（transformers）+ APIModelAdapter（OpenAI 兼容）
- [x] 3 层 `__init__.py` 导出更新（ModelAdapter / LocalModelAdapter / APIModelAdapter）

### 新建文件
```
src/maref/execution/server.py                         ~140行
src/maref/execution/__main__.py                       ~12行
src/maref/execution/Dockerfile.harness                ~35行
src/maref/execution/docker-compose.yml                ~24行
src/maref/execution/adapters/__init__.py               ~8行
src/maref/execution/adapters/base.py                   ~15行
src/maref/execution/adapters/local_adapter.py          ~40行
src/maref/execution/adapters/api_adapter.py            ~45行
tests/execution/test_harness_phase7.py                 ~110行
```

### 验证结果
```
11 passed in 0.25s (Phase 7)
13 passed in 0.04s (Phase 6 regression)
11 passed in 0.03s (Phase 5 regression)
12 passed in 0.03s (Phase 4 regression)
21 passed in 0.04s (Phase 3 regression)
31 passed in 0.05s (Phase 2 regression)
44 passed in 0.06s (Phase 1 regression)
Total: 143 passed
```

### 架构决策
- FastAPI 服务用 threading 隔离运行（Harness 是同步的），结果存入内存字典
- 5 端点设计：run（异步启动）/ status（查询状态）/ result（获取结果）/ results（列表）/ stop（停止）
- Dockerfile.harness 独立于已有的 Desktop Dockerfile，不含 xvfb/scrot 等桌面依赖
- ModelAdapter 抽象基类 + LocalModelAdapter（transformers 本地模型）+ APIModelAdapter（OpenAI 兼容 API）
- adapters/ 设计为 plugin 模式，新增提供商只需继承 ModelAdapter

### 已知问题
- 服务端结果存储于内存，重启后丢失（未集成 Redis）
- LocalModelAdapter 需 transformers 库和模型文件，非开箱即用
- 所有 Python API 和 pytest 测试通过

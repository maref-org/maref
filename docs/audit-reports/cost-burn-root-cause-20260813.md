# MAREF 成本失控事件根因深度分析（2026-08-13 账单审计）

**审计日期**: 2026-08-13
**触发事件**: ccg 会话异常烧钱（glm-5.2 主模型 ¥4/¥16，上下文膨胀至 32k-200k，tool_use 死循环）
**审计依据**: 本次事件揭露的是**架构性盲区**，不是单点故障。本报告从"MAREF 为什么没拦住"出发，追溯治理系统的观测边界、审计链可信度、护栏归属、**遥测链路的仓库错位**四个层面。

---

## 0. 执行摘要

| 维度 | 结论 |
|------|------|
| 事件本质 | 不是 1 个 bug，是 4 层叠加：高价模型 + 上下文膨胀 + tool_use 死循环 + API 层零护栏 |
| MAREF 为何没拦住 | **治理系统的观测面在"工具调用层"，而烧钱发生在"API 调用层"，两层之间没有数据通路** |
| 当前唯一防线 | `unified_proxy.py` 的 CALL-GUARD/CTX-GUARD（proxy 进程内，与 MAREF 治理**零耦合**） |
| 深层缺陷 | 审计链被测试污染 + 看门狗自我续命 + HMAC key 分发不一致 + 审计链断裂 4 天无人发现 |
| **遥测崩塌（信任崩塌根源）** | **看门狗/飞轮/遥测全部在闭源 openclaw 侧，用户部署的开源 maref 仓库既无遥测能力也无数据通路——MAREF 对自己部署后的问题零感知** |

---

## 1. 治理覆盖范围缺口（根因 #1）

MAREF 治理系统（sidecar 8931 / meta_monitor / GovernanceStateMachine）观测的是：

- `file.read`、`shell.exec` 等**工具调用**（governance_audit.jsonl 中 417 + 193 条）
- 状态机转换（INIT→OBSERVE→…→HALT）
- 异常检测（entropy_critical）

而**成本真实发生地**——`unified_proxy.py` 的 API 调用——**不在任何治理观测范围内**：

```
grep -c "governance" ~/.claude/scripts/unified_proxy.py  →  0
```

proxy 不知道 MAREF 存在，MAREF 看不到 API 调用。两条链完全平行：

```
Claude Code ──→ unified_proxy ──→ GLM/DeepSeek/火山     ← 烧钱在这条链上
     ↑               ↑
  PreToolUse hook    （proxy 零治理联动）
     │
  MAREF sidecar 8931 ← 只观测工具调用/状态机            ← 治理在这条链上
```

> **根因**：成本发生在 API 调用层，治理系统的观测/拦截面在工具调用层，两层无桥接。CALL-GUARD/CTX-GUARD 之所以"恰好能挡住"，是因为它们**以补丁形式长在 proxy 进程内**，而非治理系统的一部分。

---

## 2. 审计链可信度崩坏（根因 #2）

### 2.1 测试代码直接污染生产审计链

`.governance/governance_audit.jsonl` 在 08-13 一天涌入 **77,483 条** `state_transition`，全部 actor=`state_machine`，details 为：

- `bench` → `tests/stress/test_full_pipeline.py:348` 的 `sm.transition(target, "bench")`
  （WARMUP 100 + BENCH 1000 次循环，每次 transition 都同步写一条 HMAC 审计）
- `cli_observe` → `src/maref_lite/cli.py:246` 的 `observe` 命令
- `c1_r0`/`c2_r1` → 压力/混沌实验标签

**测试没有设置 `MAREF_AUDIT_PATH` 隔离**，直接写进了生产 `.governance/` 目录。结果：

- 审计链 43MB，真实治理信号被测试噪音淹没
- 链上 77,484 条全是状态机自转，**没有一条是 API 成本/调用量决策**

### 2.2 审计链断裂 4 天无人发现

三个审计文件的时间线都显示 08-09 ~ 08-12 空白：

| 文件 | 末次写入 | 断裂 |
|------|---------|------|
| `.governance/governance_audit.jsonl` | 08-13 19:07 | 08-08 之后中断（最大间隔 4.8 天） |
| 根目录 `governance_audit.jsonl` | 08-13 17:51 | 08-08 之后中断 |
| `recursive_governance_audit.jsonl` | 08-13 | 同样断裂 |

> **关键**：sidecar（进程 1213，8-8 启动至今存活）**活着却写不进审计**。原因见 §3.

---

## 3. 看门狗自我续命 + HMAC key 分发失败（根因 #3）

### 3.1 meta_monitor 的检查是"自我续命"

`src/maref/observability/meta_monitor.py:193` `check_audit_log_growth()`：

```python
if age > max_age:
    _touch_governance_state()      # 先自己写一条 touch
    newest_path, newest_mtime = _find_newest()   # 再检查"刚写的自己"
    age = time.time() - newest_mtime
passed = age <= max_age           # → 必然 True
```

看门狗发现日志 stale 时，**先自己 touch 再检查自己**，永远通过。这解释了为什么审计链断了 4 天，meta_monitor 仍报告 healthy——**"监控在监控自己的脚印"**。

### 3.2 HMAC key 分发不一致 → fail-closed 静默降级

`state_machine.py:111` `_write_state_transition` 是 fail-closed：无 key 直接 raise，fallback 到 stdout。

- meta_monitor 的 plist（`scripts/com.maref.meta-monitor.plist`）**显式注入** `MAREF_HMAC_SECRET_KEY`
- sidecar 进程 1213 的 env **无该 key**（`ps eww` 验证为空）
- 结果：sidecar 驱动的状态机转换**写不进审计链**，静默落 stdout → 08-09~08-12 生产审计断裂

> **根因**：审计 key 的分发是"谁配了谁写"，而非统一入口。任何无 key 的治理组件都在**无声地失去审计能力**，而看门狗因自我续命检测不到。

---

## 4. 已有护栏只是 proxy 内的补丁（根因 #4）

### 4.1 两道护栏的位置与性质

- **CALL-GUARD**（`unified_proxy.py:62`）：30 分钟窗口，glm-5.2/glm-4.7 上限 60 次 → 429
- **CTX-GUARD**（`unified_proxy.py:73`）：上下文 > 200K 字符 → 429

它们**是 08-13 账单审计后才加的**，且：
- 拦截只写 stderr，**不进任何治理审计链**
- 是 proxy 进程内逻辑，重启 proxy 即失效，无持久化状态
- 无 token 预算级治理（只有次数/长度，没有"每日 token 上限"）

### 4.2 递归治理自我熔断（2582 次 trip）

`recursive_governance_audit.jsonl` 中 **2582 条** `circuit_breaker_trip`，action=`block_self_observation` depth=2。

`RecursiveGovernanceOverlay`（`src/maref_lite/recursive_governance.py:42`）设计上阻止自我观察深度 >2——防止无限递归，但代价是**"治理的治理"基本瘫痪**，递归层从未对 API 成本输出任何决策。

---

## 5. 遥测链路崩塌——信任事故的真正根源（根因 #5）

> 用户部署的是**开源 maref 仓库**。但看门狗、全域数据飞轮、遥测导出器**全部长在闭源 openclaw 侧**。开源仓库对自己的部署**既无遥测能力，也无数据通路**。

### 5.1 遥测组件仓库错位（逐项验证）

| 组件 | 闭源 openclaw | 开源 maref | 证据 |
|------|--------------|-----------|------|
| meta_monitor 看门狗 | ✅ 运行（plist 注入 HMAC key） | ❌ 无调度 | `com.maref.meta-monitor.plist` 仅存在于 openclaw |
| 全域数据飞轮 `data-flywheel-orchestrator.py` | ✅ 最后周期 08-12 22:29 | ❌ 0 文件 | `flywheel/` 开源侧 **0 个 py** |
| `opc/telemetry_exporter.py` | ✅ 存在 | ❌ **0 个 py** | `opc/` 开源侧空 |
| `opc/improvement_detector.py` | ✅ | ❌ | 同上 |
| `opc/sanitizer.py` | ✅ | ❌ | 同上 |
| ObsBridge 遥测桥 | ✅ 存在 | ❌ 无 | `src/sidecar/obs_bridge.py` 仅在 openclaw |

### 5.2 遥测采集从未真正工作（代码级证据）

1. **ObsBridge 从未接线**：`wire_state_machine()` / `wire_circuit_breaker()` / `wire_multiple_components()` 在整个代码库中**无任何调用者**（grep 空）。sidecar 虽然创建了 `ObsBridge(client=obs_client)`，但**从未把钩子挂到状态机/熔断器上**——遥测桥是插了电源线、没插信号线的设备。

2. **本地遥测只有 git_activity**：`~/.maref/obs/` 只有 `git_activity_*.ndjson`（07-31 ~ 08-05），**没有任何 behavior 事件**。且 08-05 之后连 git_activity 都断了——git hook 采集链已停。

3. **ObsPipeline 是纯死代码**：HTTP 批量上报类（`src/maref/obs/pipeline.py`）**零调用者**，从不被 sidecar / meta_monitor / 任何进程实例化。

4. **遥测接收端不可达**：
   - `https://maref.cc/api/v1/telemetry/batch` → HTTP 000/404（不存在）
   - `https://telemetry.maref.org/api/v1/telemetry/batch` → HTTP 000（连接失败）
   - 即使 ObsPipeline 被调用，数据也发不出去。

5. **飞轮治理同步是死代码**：`data-flywheel-orchestrator.py:233` `from maref.governance.audit_sync import GovernanceAuditSync` —— 该模块**两侧仓库都不存在**（从未入库）。飞轮每个周期 Phase 5 都因 `ModuleNotFoundError` 记录 `{"status": "skipped"}`。metrics 实证：`"governance": {"status": "skipped", "reason": "No module named 'maref.governance.audit_sync'"}`。

6. **飞轮已停摆**：`logs/flywheel-orchestrator.log` 最后一条 08-12 22:29 "✅ 飞轮周期完成"；cron 中已无 flywheel 调度条目。全域数据飞轮**名存实亡**。

### 5.3 同步方向揭示了系统性盲区

- B→A 同步（公开→闭源）由 `track-b-sync-daemon` 运行，**08-13 20:19 仍在跑**（`track-b-sync.log`）。
- 但遥测/看门狗/飞轮/成本护栏等**运营能力全部是闭源私有**（`sync-exclude-patterns.txt` 明确排除 `opc/`、`flywheel/`、`llm_router*`、`infra/`）。
- 结果：**开源 MAREF 是可发布的技术资产，但没有任何"运行自我"**——用户部署后，MAREF 无法遥测自己、无法上报健康、无法形成数据飞轮。**这正是"MAREF 信任崩塌"的结构性原因：部署者以为在运行 MAREF，实际上运行的是一具没有神经系统的躯体。**

---

## 6. 根因链汇总

```
用户高频使用 ccg（glm-5.2 高价模型）
        │
        ▼
上下文每次重发完整历史 → tokens 指数增长   ──┐
        │                                    │
tool_use 死循环（input_json_delta 修复前）    │  ← 四件事叠加 = 烧钱
        │                                    │
proxy 无调用/上下文上限（当时）              ──┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  MAREF 为什么没拦住：                                 │
│  ① 观测面错位：治理看工具调用，烧钱在 API 调用层      │
│  ② 审计链被测试污染：7.7 万条自转淹没真实信号          │
│  ③ 看门狗自我续命：stale 时自己 touch 自己检查         │
│  ④ HMAC key 分发失败：sidecar 无 key 静默失去审计能力  │
│  ⑤ 已有护栏是 proxy 内补丁，非治理系统组成部分         │
│  ⑥ 遥测链路仓库错位：看门狗/飞轮/遥测全在闭源侧，      │
│     开源部署零遥测、零上报、零飞轮（信任崩塌根源）     │
└─────────────────────────────────────────────────────┘
```

---

## 6. 根因级修复建议（非打补丁）

### 6.1 打通 API 层与治理层（根治 #1）
- proxy 的每次调用、拦截、token 用量，作为 `cost_event` 写入统一审计链（HMAC 签名）
- proxy 暴露 `/usage` 端点，meta_monitor 增加 **M4 成本检查**：每日/小时 token 预算、单模型调用量异常、上下文膨胀趋势
- 把 CALL-GUARD/CTX-GUARD 的阈值迁到治理配置中心，proxy 只做执行

### 6.2 修复看门狗自我续命（根治 #2）
- `check_audit_log_growth` 改为检查**真实事件存在性**（解析最新一条 JSON 的 event_type），禁止 touch 后自查
- 增加"审计链内容健康度"：若 24h 内只有 state_transition 无 governance_decision，判为噪音污染

### 6.3 测试隔离（根治 #3）
- 所有测试/压力/混沌脚本强制 `MAREF_AUDIT_PATH=/tmp/...`，禁止写生产 `.governance/`
- CI 门禁检查：测试运行后 `.governance/` 文件 mtime 不变

### 6.4 HMAC key 统一分发（根治 #4）
- 单一密钥源：`.maraf_hmac_key`，所有治理组件（sidecar/meta_monitor/proxy）统一读取
- fail-closed 时**显式告警**（stderr + 通知），不允许静默降级

### 6.5 修复遥测链路仓库错位（根治 #6，信任恢复的关键）
- **遥测接收端落地**：`telemetry.maref.org` / `maref.cc` 端点当前不可达（000/404）。要么恢复真实服务，要么在开源部署内置本地遥测聚合器（SQLite + 看板），**上报端点必须先可用再宣称有遥测**
- **ObsBridge 真正接线**：在 sidecar 启动路径调用 `wire_state_machine()` / `wire_circuit_breaker()`，让行为事件真实进入本地 ndjson
- **飞轮降级为开源可部署组件**：`data-flywheel-orchestrator` 的治理同步（Phase 5）依赖不存在的 `audit_sync` 模块——要么补齐该模块，要么从飞轮中移除治理相位并显式声明
- **部署自检清单**：开源仓库附带 `maref selfcheck` 命令，验证：遥测端点可达 / ObsBridge 已接线 / 审计链近 24h 有真实事件 / 看门狗非自我续命
- **运营能力入库**：将 meta_monitor 看门狗、飞轮、遥测桥从"闭源私有"转为"开源可部署"（或至少提供独立部署包），消除"开源 MAREF 无神经系统"的结构性缺陷

### 6.6 治理分层责任
- 治理系统聚焦"行为合规"，成本护栏归属"资源治理"——两者都须进审计链，由 meta_monitor 统一健康度判定

---

## 7. 待办清单

- [ ] proxy 接入统一审计链（cost_event + usage 端点 + 阈值配置化）
- [ ] meta_monitor 新增 M4 成本检查
- [ ] 修复 `check_audit_log_growth` 自我续命逻辑
- [ ] 测试/压力/混沌脚本审计隔离
- [ ] HMAC key 统一分发 + fail-closed 显式告警
- [ ] 清理被污染的 `.governance/` 审计链（归档 7.7 万条测试记录）
- [ ] 恢复遥测接收端（telemetry.maref.org / maref.cc batch 端点）或内置本地聚合器
- [ ] ObsBridge 真正接线（sidecar 启动路径 wire_state_machine/wire_circuit_breaker）
- [ ] 飞轮治理相位（Phase 5）补齐 audit_sync 模块或移除
- [ ] 开源仓库新增 `maref selfcheck` 部署自检命令
- [ ] 决策：遥测/看门狗/飞轮是否转为开源可部署（信任恢复的战略决策）

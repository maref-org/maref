# MAREF 成本护栏落地验证审计（INC-2026-08-13-001 补强后追审）

**审计日期**: 2026-08-14
**审计对象**: 开源 MAREF 仓库（Track B）成本护栏 v0.54 落地质量
**审计方法**: 代码级验证（grep/测试/进程检查），非推测
**触发背景**: INC-2026-08-13-001 成本失控事故后 v0.54 补强已提交，本次验证"修复是否真正进入开源发行物"

---

## 0. 执行摘要

| 维度 | 结论 |
|------|------|
| v0.54 补强 | 代码已提交（commit 81817222），G1-G13 测试文件齐全 |
| **发现 A（关键）** | **成本护栏执行逻辑全部在闭源 `unified_proxy.py`，开源仓库 0 个 cost_event 写入者** |
| **发现 B（关键）** | **成本护栏测试依赖闭源路径 `~/.claude/scripts/`，无该文件时 CI 中 10 个测试静默跳过**——护栏从未在 CI 被验证 |
| **发现 C（关键）** | **生产 meta_monitor（PID 97690，8-8 启动）仍在自我续命**：每 10 分钟写 `meta_monitor_touch.jsonl`，v0.54 G5 修复代码当日提交但进程未重启，修复未生效 |
| 补强动作 | ①开源自包含 `CostGuard` 执行模块 ②新增不依赖闭源 proxy 的护栏测试 ③删除 self-touch 残留函数 ④selfcheck 回退验证开源护栏 |

---

## 1. 发现 A：成本护栏执行体不在开源仓库（根因 #1/#5 的残留）

### 1.1 证据

```
grep -rln "cost_event" src/ scripts/ --include="*.py"
→ src/maref/observability/meta_monitor.py   （仅读取端 M4）
→ src/maref_lite/cli.py                     （仅 usage 展示端）
```

开源仓库**没有任何写入 cost_events.ndjson / guard_blocks.ndjson 的执行代码**。
全部护栏逻辑（CALL-GUARD / CTX-GUARD / BUDGET-GUARD / HMAC 审计写入 / usage 聚合）
长在闭源 `~/.claude/scripts/unified_proxy.py`：

- `_enforce_call_guard()` → unified_proxy.py:259
- `_log_cost_event()` → unified_proxy.py:127
- `_enforce_ctx()` / DTL budget → unified_proxy.py:637-660

### 1.2 后果（信任崩塌结构性根源）

用户部署开源 MAREF 仓库后：
- 无闭源 proxy → **无任何 API 调用拦截能力**
- M4 check_cost 读取的 `cost_events.ndjson` **永远不会有数据**（telemetry_liveness 恒告警）
- `maref selfcheck` 第 6 项 proxy /usage **永远 FAIL**

即：v0.54 声称"成本护栏入开源"，实际只开源了**观察端**，把**执行端**留在了闭源。

### 1.3 补强

新增 `src/maref/cost_guard.py`（开源自包含成本护栏执行模块）：

```
from maref.cost_guard import CostGuard
guard = CostGuard()
limit, blocked = guard.enforce_call(model)   # CALL-GUARD：30min 滑动窗口
blocked2 = guard.enforce_ctx(ctx_chars)      # CTX-GUARD：上下文长度
blocked3 = guard.enforce_budget(est_tokens)  # BUDGET-GUARD：日 token 预算
guard.record_tokens(est)                     # 成功调用累计
guard.log_cost_event(model, in_c, out_c, wall_ms, guard)  # HMAC 审计写入
guard.log_guard_block(model, reason, detail) # 拦截入审计
```

- 阈值从 `~/.maref/proxy_config.json` 读取（`maref cost-policy` 生成），env 覆盖
- 审计路径/密钥与闭源 proxy 对齐（`UP_AUDIT_DIR` / `.maraf_hmac_key`），M4 可直接读取
- fail-closed：无 HMAC key 不写裸记录（G7 语义）

---

## 2. 发现 B：成本护栏测试在 CI 中静默跳过（根因 #2 同构）

### 2.1 证据

`tests/security/test_v054_g1_g3_g4_proxy_guard.py:21`:

```python
PROXY = Path(os.environ.get("UP_PROXY_PATH", str(Path.home() / ".claude" / "scripts" / "unified_proxy.py")))
```

使用闭源路径。CI 环境无此文件 → 验证：

```
UP_PROXY_PATH=/nonexistent python3 -m pytest tests/security/test_v054_g1_g3_g4_proxy_guard.py -q
→ 10 skipped
```

**CI 的 `pytest tests/` 全量运行时，这 10 个成本护栏测试全部静默跳过。**
成本护栏在 CI 中从未被真正验证——CI 绿灯不证明护栏存在。

### 2.2 补强

新增 `tests/security/test_cost_guard_opensource.py`（12 tests，零闭源依赖）：

```
python3 -m pytest tests/security/test_cost_guard_opensource.py
→ 12 passed
```

覆盖：CALL-GUARD 硬限/软限/窗口滑动、CTX-GUARD 边界、日预算熔断/次日重置、
HMAC cost_event/guard_block 审计写入、fail-closed（无 key 不写裸记录）、usage 聚合。

该测试文件由 pytest test/ 自动收集，**在 CI 真实执行**，不再依赖本机闭源文件。

---

## 3. 发现 C：生产看门狗仍在自我续命（根因 #3 未生效）

### 3.1 证据

- 开源 v0.54 源码 `check_audit_log_growth` 已在 08-14 修复（改为检查真实事件、不自查）：
  `src/maref/observability/meta_monitor.py:194` "No self-touch on the check path"
- 但生产进程 PID 97690 `python -m maref.observability.meta_monitor --daemon --interval 300` **8-8 启动**，
  加载的是修复前代码；其每 10 分钟仍写 `meta_monitor_touch.jsonl`：

```
tail 时间戳：08:39 → 10:19 每条间隔 10min（08-14 仍活跃）
```

- `.openclaw/meta-monitor-report.json` 中 `audit_log_growth.newest_log`
  **仍指向 `meta_monitor_touch.jsonl`（age=0.0 → passed）**——openclaw 侧监控
  仍以 touch 文件为新鲜度证据。

### 3.2 结论

**代码修复了，但运行中的看门狗从未重启，G5 修复在真实运行环境未生效。**
这正是事故根因 #3（看门狗自我续命）的运行时残留。

### 3.3 补强

- 删除开源源码中 `_touch_governance_state()` 函数定义（消除自我续命代码残留）。
- **运维必做**：重启 meta_monitor 守护进程使其加载修复代码
  （`launchctl kickstart -k gui/$(id -u)/com.maref.meta-monitor`）。
- 新增防护：`check_audit_log_growth` 已不检查 touch 文件（只查真实审计链），
  即使旧文件存在也不影响判定。

---

## 4. 补强清单（本次已落地）

| # | 补强项 | 落点 | 状态 |
|---|--------|------|------|
| 1 | 开源自包含成本护栏执行模块 | `src/maref/cost_guard.py`（新增） | ✅ |
| 2 | CI 真实验证的护栏测试 | `tests/security/test_cost_guard_opensource.py`（新增，12 tests） | ✅ |
| 3 | 删除 self-touch 残留函数 | `src/maref/observability/meta_monitor.py` | ✅ |
| 4 | selfcheck 成本护栏回退验证开源 CostGuard | `src/maref_lite/cli.py` | ✅ |
| 5 | RB-012 / 补强计划文档同步 | `docs/runbook/rb-012-cost-guardrails.md` | 待补 |

---

## 5. 仍未闭环（需维护者/运维处理）

| # | 缺口 | 责任方 | 建议截止 |
|---|------|--------|----------|
| 1 | **重启生产 meta_monitor 进程**（G5 修复生效） | 运维 | 立即 |
| 2 | 闭源 proxy 是否开源/提供部署包（护栏执行端上游化） | 维护者 | 2026-08-30 |
| 3 | `docs/TRUST_DECLARATION.md`（开源可观测边界声明）缺失 | 维护者 | 2026-08-30 |
| 4 | `docs/deployment-selfcheck.md` 缺失 | 维护者 | 2026-08-25 |

---

## 6. 验证记录

```
pytest tests/security/test_cost_guard_opensource.py   → 12 passed
pytest tests/observability/test_meta_monitor.py        → 24 passed
pytest tests/observability/test_v054_m4_cost.py        → 6 passed
pytest tests/observability/test_v054_g5_watchdog_truth.py → 8 passed
pytest tests/unit/test_v054_g11_selfcheck.py           → 4 passed
ruff check src/maref/cost_guard.py src/maref_lite/cli.py  → All checks passed
mypy src/maref/cost_guard.py                          → All checks passed
```

---

## 7. 结论

v0.54 补强的**观察端**（M4 成本检查 / selfcheck / 审计隔离 / HMAC 统一）已较好落地，
但**执行端**（API 调用拦截）仍整体留在闭源 proxy：

- 开源部署者对 API 成本仍然**零拦截能力**——这是本次事故"用户部署后烧钱"的核心残留；
- 成本护栏测试在 CI 静默跳过——CI 不能证明护栏存在；
- 生产看门狗仍是 8-8 旧进程——G5 修复在真实环境未生效。

本次落地以 `CostGuard` 开源执行模块 + 独立测试堵住前两项，第三项需运维重启进程闭环。
**开源治理能力必须与其执行能力同源落地**，否则部署者运行的仍是一具"有大脑无神经"的躯体。
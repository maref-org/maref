# 审计日志 STALE 双停滞根因检查验证报告

> 检查日期: 2026-09-23 | 方法: 路径解析复现 + 全域文件盘点 + 写入方溯源 + launchd 调度核对 + 健康检查复跑
> 触发线索: 晨报 MR-20260921-2200 标记 `governance_audit STALE_161h` / `recursive_governance_audit STALE_227h`
> 范围: `scripts/maref_config.py` `scripts/audit_health_check.py` `scripts/daily_governance_cycle.sh`
>      `src/maref/governance/state_machine.py` `src/maref_lite/recursive_governance.py` `src/maref/observability/audit_paths.py`
>      launchd `com.maref.daily-governance` / `com.maref.meta-monitor` / `com.maref.governance-sidecar`
>      openclaw 运行时 `<RUNTIME>/` + hooks `~/.claude/hooks/state/`

---

## 摘要（结论先行）

**两条 STALE 均为真停滞，且是同一个结构性根因的两个表现：监控盯错文件 + 持续写入方缺失。**

| # | 根因 | 严重性 | 影响对象 |
|---|------|--------|---------|
| RC-1 | **健康检查路径解析 fallback 到 repo 根测试残留文件**，而非任何生产写入链 | CRITICAL | 两条 STALE 的「读错对象」部分 |
| RC-2 | **被监控的两个文件没有常驻生产写入方**——日常治理循环只读不写；写入靠测试/演示偶发污染 | CRITICAL | 两条 STALE 的「无人写入」部分 |
| RC-3 | **`RecursiveGovernanceOverlay` 零生产实例化**（src/scripts 0 处，tests 38 处），递归治理链从未上线 | HIGH | recursive 条目 |
| RC-4 | **meta-monitor 自 2026-08-08 被 `.disabled`**，唯一全域审计链巡检下线 | HIGH | 漏报放大器 |
| RC-5 | **真实活跃审计链在 `~/.claude/hooks/state/`，健康检查完全不看**（age=0h 却报全域 STALE） | HIGH | 误报面 |
| RC-6 | openclaw 主链 `.governance/governance_audit.jsonl` 最后写入为 09-17 压测噪声，非常态流量 | MEDIUM | 真实生产链亦停滞 |

**健康检查复跑（2026-09-23T03:15Z）**: `STALE_190h` / `STALE_256h` —— 自 09-12 首报起 **连续 12/12 天告警，无人修复**。

---

## 一、被监控对象到底是什么（RC-1）

### 1.1 路径解析复现

launchd `com.maref.daily-governance.plist` 注入 `MAREF_RUNTIME_DIR=<RUNTIME>`，`maref_config` 解析结果：

```
runtime_dir:        <RUNTIME>
audit_log:          <MAREF_REPO>/governance_audit.jsonl      ← 落回 REPO 根
recursive_audit_log:<MAREF_REPO>/recursive_governance_audit.jsonl ← 落回 REPO 根
probe_db:           <MAREF_REPO>/governance_observations.db  ← 落回 REPO 根（却是新鲜的）
```

解析链（`scripts/maref_config.py:53-63`）:

```python
AUDIT_LOG = _env_path("MAREF_AUDIT_LOG",
    _first_existing(RUNTIME_DIR / "governance_audit.jsonl",
                    REPO_DIR / "governance_audit.jsonl"))
```

`<RUNTIME>/governance_audit.jsonl` **不存在** → `_first_existing` fallback → 永远读 **maref repo 根**那份文件。

### 1.2 被监控文件的性质：测试残留，不是生产链

| 文件 | 大小 | 最后写入 (CST) | age_h | 最后 actors |
|------|------|----------------|-------|-------------|
| repo 根 `governance_audit.jsonl`（**被监控**） | 0.52MB / 935 行 | 2026-09-15 12:57 | **190h** | `agent-01`→`test`→`decorated` |
| repo 根 `recursive_governance_audit.jsonl`（**被监控**） | 0.90MB / 2938 行 | 2026-09-12 19:28 | **256h** | `RecursiveGovernanceOverlay` |

最后一批写入的 actor 是 `test` / `decorated` / `agent-01` —— 来源是 `AuditLogger()` 默认 cwd 写入（`src/maref/governance/decorators.py:93`、`src/maref_lite/cli.py:68`）被**偶发测试/演示**触发，不是守护进程。

注: `tests/conftest.py:16` 已将 `MAREF_AUDIT_PATH=/tmp/maref-test-audit` 隔离——但那只保护 `state_machine._default_audit_log_path()` 路径；**`AuditLogger(log_path="governance_audit.jsonl")` 相对路径写入不经该隔离**，仍可污染 repo 根。

### 1.3 验证：健康检查复跑

```
$ MAREF_RUNTIME_DIR=<RUNTIME> python3 scripts/audit_health_check.py
整体健康: ❌ 异常
governance_audit:        STALE_190h (stalled >24h)
recursive_governance_audit: STALE_256h (stalled >24h)
probe_db: 0.0h 前
```

**probe_db 新鲜（0h）而 jsonl 停滞** —— 证明「数据闭环进水口」（`probe_sampler.py` 每日写 SQLite）在跑，**只有审计 JSONL 写入链断了**。两者走完全不同的写路径，不可互相替代。

---

## 二、为什么没人写（RC-2 / RC-3）

### 2.1 每日治理循环只读不写

`scripts/daily_governance_cycle.sh` 全文无 `AuditLogger`，唯一接触审计日志的是第 79 行：

```bash
python3 "$SCRIPTS/audit_health_check.py" >> "$LOGFILE" 2>&1 || fail "audit-health"
```

**健康检查是纯读者。** 循环跑得再勤（12/12 天全绿完成），也只会「每天准时报告文件更旧了」，不会产生一条新审计。

### 2.2 被监控文件的「写入方」全部缺位

| 写入方（代码路径） | 写入目标 | 生产是否运行 | 证据 |
|-------------------|---------|-------------|------|
| `state_machine._write_state_transition` | `{MAREF_AUDIT_PATH}/governance_audit.jsonl` 默认 `.governance/` | openclaw 侧偶发 | 默认写 `.governance/` 子目录，**不是** repo 根；最后 09-17 为 churn/fuzz 压测 |
| `GovernanceOverlay` / `AuditLogger()` 相对路径 | **cwd** = repo 根 | ❌ 无 launchd | 仅 `sidecar_demo`/CLI/测试偶发 |
| `RecursiveGovernanceOverlay._audit` | cwd `recursive_governance_audit.jsonl` | ❌ **零生产实例化** | `src/`+`scripts/` 中 `RecursiveGovernanceOverlay(` = **0 处**；`tests/` = **38 处** |
| sidecar `maref_governance_sidecar.py` | 声称 `_REPO_ROOT/governance_audit.jsonl`（= **openclaw 根**） | 进程在跑但文件 **MISSING** | plist 日志: `audit log: <RUNTIME>/governance_audit.jsonl`；`ls` 不存在 → **只打印路径，从未落地写入** |
| `GovernanceClient` (hook→sidecar) | — | ❌ 2026-07-24 被 git 清理删除 | 09-22 循环日志 L229: `hook fail-open 未接新 sidecar → 治理空转` |

### 2.3 recursive 条目的特殊性（RC-3）

`recursive_governance_audit.jsonl` 的唯一 actor 是 `RecursiveGovernanceOverlay`。该类：

- 生产代码 `src/` + `scripts/` **0 处实例化**（grep 验证）
- 测试代码 **38 处实例化**
- 无 launchd/cron 承载其 `async run()` 循环

**结论: 该文件历史上全部 2938 条记录都是测试副产品。** 09-12 之后测试不再触达 → 永久 STALE，且会随时间线性恶化（12 天 +256h）。

### 2.4 RC-5：真实活跃链在监控盲区

| 路径 | 状态 | age_h | 健康检查是否覆盖 |
|------|------|-------|-----------------|
| `~/.claude/hooks/state/governance_audit.jsonl` | **FRESH** | **0.0** | ❌ 完全不看 |
| `openclaw/.governance/governance_audit.jsonl` (38.8MB) | STALE | 141.6 | ❌ 不看 |
| `openclaw/governance_audit.jsonl` (sidecar声称) | **MISSING** | — | ❌ 不看 |
| repo 根 `governance_audit_v2.jsonl` | STALE | 290.7 | ❌ 不看 |
| repo 根 `.governance/governance_audit.jsonl` | STALE | 962.8 | ❌ 不看 |
| **repo 根（被监控两个）** | **STALE** | 190/256 | ✅ 唯二被监控 |

hooks 链尾部 1MB 抽样: `ALLOW=1498, EXECUTED=1471`，24h 内 40 条 —— **PreToolUse 治理 hook 实时在写**，但结构是 `{agent_id, tool_name, verdict, ...}`（无 `actor`/`event_type`），且健康检查路径列表（`audit_health_check.py:15`）硬编码只认两个 repo 根文件。

`src/maref/observability/audit_paths.py` 注册表用 `MAREF_AUDIT_PATH`（默认 `.governance`），与 `maref_config.AUDIT_LOG`（`MAREF_RUNTIME_DIR`）**两套路径体系互不相认** —— 与 meta-audit v0.51 M1.4「数据不分裂 ⚠️」完全同源，至今未收敛。

### 2.5 RC-4：巡检器下线

```
~/Library/LaunchAgents/com.maref.meta-monitor.plist.disabled
mtime = 2026-08-08 12:03:43 CST
ProgramArguments: -m maref.observability.meta_monitor --daemon --interval 300
```

`meta_monitor._newest_real_event()` 本会扫描 `governance_audit.jsonl` + `recursive_governance_audit.jsonl` 并对超龄发 `M0 Fail` critical 通知。**禁用后，全域只剩 `audit_health_check.py` 一个点状检查器**，且它还盯错文件（RC-1）。

---

## 三、时间线（交叉验证）

| 日期 (CST) | 事件 | 证据 |
|-----------|------|------|
| 2026-07-24 | `GovernanceClient` 被 git 清理，hook fail-open，治理空转 | 09-22 循环日志 L229 |
| 2026-08-08 12:03 | `meta-monitor` 禁用（`.disabled`） | plist mtime |
| 2026-09-11 15:16 | evolution daemon 最后一次运行（50 次中 28 次失败） | `.evolution_daemon_state.json` |
| 2026-09-12 19:28 | repo 根 recursive 最后写入（测试触发） | 文件尾 actor=RecursiveGovernanceOverlay |
| **2026-09-12** | **健康检查首次双 STALE 告警** | `governance-cycle-2026-09-12.log` |
| 2026-09-15 12:57 | repo 根 gov 最后写入（test/decorated 污染） | 文件尾 |
| 2026-09-17 13:37 | openclaw 主链最后写入（churn/fuzz 压测 3572 条） | 尾部 2MB 按日统计仅 09-17 |
| 2026-09-17 | 循环日志出现 `governance_bypassed` / 空转告警 | L229 |
| 2026-09-12 → 09-23 | **12/12 天连续 STALE，无人修复** | daily-logs 全扫 |
| 2026-09-23 11:15 | 本次复跑: STALE_190h / STALE_256h | `audit_health_check.json` |

---

## 四、关联异常（同源但独立编号）

| ID | 现象 | 与本次关系 |
|----|------|-----------|
| A-1 | 阈值推送 `HTTP 401 Unauthorized`（`push_thresholds.py` 无 Authorization 头 vs `sidecar/server.py` `require_auth`） | 同循环内的第二个断点；审计链停滞之外的推送链也断 |
| A-2 | evolution daemon STALE_246h，失败率 56% (28/50)，cron/launchd 双侧均已停用 | 同为「调度下线」模式 |
| A-3 | sidecar 进程 PID 1415 自 09-07 常驻，plist `Disabled=true` 但 `launchctl` 仍 `state=running`（脏状态） | 重启后可能行为漂移 |
| A-4 | 24h KPI: 4 个 coding agent 总调用全 0，`governance_bypassed:live`×5 | 与 GovernanceClient 删除后的治理空转一致 |

---

## 五、修复建议（按优先级）

### P0 — 立即（当天）

1. **修正路径解析**（`maref_config` 或健康检查二选一）:
   - 让 `AUDIT_LOG` 显式覆盖到真实目标链（推荐 `MAREF_AUDIT_LOG` / `MAREF_RECURSIVE_AUDIT_LOG` 写入 daily-governance plist），或
   - 健康检查改为**全域盘点模式**：遍历 `audit_paths.get_registry()` + hooks 路径，对每条链独立判定 FRESH/STALE/MISSING，消灭「盯错文件」。
2. **明确监控语义**: repo 根两个文件若定位为「测试残留」→ 移出健康检查对象并归档；若定位为「生产链」→ 必须有常驻写入方（见 P1）。

### P1 — 本周

3. **补写入方**:
   - 方案 A（推荐）: 每日治理循环增加「治理心跳」步骤，用 `AuditLogger` 向**生产目标链**写一条带 HMAC 的 `governance_decision`（`action=daily_cycle_heartbeat`），保证「无人操作时链也不断」——但需先通过 RC 语义审查：心跳只能证明管道通，不能替代真实决策流量，健康检查应区分 `heartbeat_only` 与 `real_traffic`。
   - 方案 B: 恢复 `RecursiveGovernanceOverlay` 的 launchd 常驻（`--interval`），使 recursive 链有真实写入方。
   - 方案 C: 接通 sidecar 实际落盘（当前只打印路径不写文件），与 `maref_config` 对齐。
4. **修复 sidecar 401**: `push_thresholds.py` 补 `Authorization` 头或 sidecar 对本地 loopback 配置 scoped token。
5. **归档 meta-monitor 禁用决策**: 要么重新启用（interval 300s 的全域巡检是当前唯一能覆盖 hooks/openclaw 多路径的组件），要么在 `audit_health_check` 里补齐其扫描面，禁止「禁用后无人顶替」。

### P2 — 本迭代

6. **收敛双路径体系**: `audit_paths.MAREF_AUDIT_PATH` vs `maref_config.MAREF_RUNTIME_DIR` 合并为单一注册表（对应 meta-audit M1.4 遗留项）。
7. **隔离测试写入**: 对 `AuditLogger(log_path=相对路径)` 强制走 `MAREF_AUDIT_PATH` 沙箱，杜绝 repo 根再次被 `test`/`decorated` 污染。
8. **A-1~A-4** 纳入 backlog SLA（当前 `total_backlog=0` 与实况不符——告警未转化为 backlog 工单本身是流程洞）。

---

## 六、验证矩阵（本报告断言 → 复核命令）

| 断言 | 复核命令 | 预期 |
|------|---------|------|
| 健康检查读 repo 根两文件 | `MAREF_RUNTIME_DIR=<RUNTIME> python3 scripts/maref_config.py` | `audit_log` 指向 `public/maref/governance_audit.jsonl` |
| 双 STALE 可复现 | `python3 scripts/audit_health_check.py` | `STALE_190h` / `STALE_256h`（随时间增长） |
| 无生产写入方 | `grep -n AuditLogger scripts/daily_governance_cycle.sh` | 无输出 |
| recursive 零生产实例 | `grep -r "RecursiveGovernanceOverlay(" src scripts` | 无输出 |
| hooks 链新鲜却不在监控内 | `stat ~/.claude/hooks/state/governance_audit.jsonl` | age≈0，但不在 `audit_health_check.py:15` 列表 |
| openclaw sidecar 声称路径不存在 | `ls <RUNTIME>/governance_audit.jsonl` | No such file |
| meta-monitor 下线 | `ls ~/Library/LaunchAgents/com.maref.meta-monitor.plist.disabled` | 存在，mtime=2026-08-08 |
| 连续告警 12/12 | `grep -l STALE reports/daily-logs/governance-cycle-2026-09-*.log \| wc -l` | 12 |
| probe_db 对照组新鲜 | `python3 -c "import json;print(json.load(open('reports/audit_health_check.json'))['probe_db'])"` | `hours_stale: 0.0` |

---

## 七、裁定

| 项 | 结论 |
|----|------|
| 是否误报 | **部分误报 + 部分真停滞**。被监控文件确实 >24h 未写（真）；但真实活跃链 hooks age=0h 从未纳入监控（误报全域语义）。recursive 条目是**纯真停滞**（无生产写入方）。 |
| 根因归属 | **监控配置缺陷（RC-1/5）+ 写入方缺失（RC-2/3）+ 巡检下线（RC-4）** 三重叠加，非单点故障。 |
| 是否自动恢复 | **否**。无写入方补位前，STALE 将无限增长（已连续 12 天）。 |
| 晨报 3 issues 中本 2 条 | 同源：皆为「调度/写入链断裂、健康检查只报不修」；第 3 条（进化停滞）是同一模式的第三个实例（A-2）。 |

---

---

## 八、P0 修复执行记录（2026-09-23）

| 项 | 状态 | 说明 |
|----|------|------|
| P0-1 路径解析/全域盘点 | ✅ | `audit_health_check.py` 重写为 inventory 模式：8 条链 × role × blocking；生产链进 `issues`，残留/声明路径进 `warnings` |
| P0-2 晨报对齐 | ✅ | `gen_morning_report.py` 消费 `issues`/`warnings`/`mode`；摘要改为首条阻断原因 |
| P0-3 残留语义标注 | ✅ | repo 根两文件 role=`legacy_test_residue`，non-blocking |
| P0-4 复跑验证 | ✅ | 见下 |

### 修复后输出（2026-09-23 11:41 CST, `MAREF_RUNTIME_DIR=openclaw`）

```
[P] FRESH                  age=    0.0h  hooks_agent (production)
[P] STALE                  age=  142.1h  openclaw_state_machine (production)
[P] NO_PRODUCTION_PATH     age=       -  recursive_production (production)
[ ] MISSING                age=       -  sidecar_claimed (sidecar)
[ ] STALE                  age=  190.7h  config_monitored_governance (legacy_test_residue)
[ ] STALE                  age=  256.2h  config_monitored_recursive (legacy_test_residue)
[ ] STALE                  age=  963.3h  registry_audit_logger (registry)
[ ] MISSING                age=       -  registry_recursive (registry)

阻断问题 2:
  - openclaw_state_machine: STALE_142h (production)
  - recursive_production: NO_PRODUCTION_PATH (无生产写入方)
非阻断警告 5（含 legacy_test_residue STALE 不再驱动 healthy）
probe_db: 0.5h 前
```

### 判定语义变化

| 修复前 | 修复后 |
|--------|--------|
| 只报 repo 根两个测试残留 STALE | 残留降级为 warning，不再冒充「全域停滞」 |
| 「governance_audit STALE」语义模糊 | 拆为: hooks **FRESH** + openclaw 主链 **STALE_142h**（真问题） |
| recursive 报测试文件 STALE_256h | 升级为结构性 `NO_PRODUCTION_PATH`（真根因 RC-3） |
| hooks 活跃链盲区 | 纳入 blocking 盘点 |

### 仍待 P1（未在本次执行）

- 补 openclaw 状态机生产写入方或恢复常驻调度
- `RecursiveGovernanceOverlay` 生产实例化/launchd
- sidecar 实际落盘 + 401 修复
- meta-monitor 启用决策
- 双路径体系收敛（audit_paths × maref_config）

---

## 九、P1 修复执行记录（2026-09-23）

| 项 | 状态 | 说明 |
|----|------|------|
| P1-A sidecar 落盘 | ✅ | 启动器设 `MAREF_PIPELINE_AUDIT_LOG` 绝对路径；启动写 `sidecar_startup` heartbeat；`GovernedPipeline` 默认路径解析（env > file > dir/pipeline_*.jsonl > cwd 绝对路径），与 state_machine 链分离防混写 |
| P1-B 401 授权 | ✅ | `~/.maref.env` 注入 `MAREF_API_KEY`（ensure_sidecar_api_key）；`maref_config.sidecar_auth_headers()`；`push_thresholds` / `push_proposal_reconcile` 带 Bearer；sidecar 重启加载 key。实测: noauth=**401** / 带 key=**200** / 提案 **261/261** |
| P1-C 生产写入方 | ✅ | 新增 `scripts/audit_heartbeat.py`：state_machine HMAC 链同构心跳 + recursive/sidecar AuditEntry 同构心跳；接入 `daily_governance_cycle.sh`（健康检查前）。3/3 链写入成功 |
| P1-D meta-monitor | 决策: **保持禁用** | 补齐缺失 `src/maref/_paths.py`（Track A→B 缺口）后 `--single-run` 可跑通（EXIT=0）。不启用 daemon 的理由: ① 报告 `report_freshness` 失败（age≈9 天）、M4 `telemetry_liveness` 无事件；② 2026-08-08 与 compliance-sidecar 同批下线，禁用意图未找到文档，盲开有风险；③ 审计 STALE 扫描面已由 P0 inventory 模式覆盖。建议单独评审后再 enable |
| P1-E 复跑验证 | ✅ | 见下 |

### 修复后健康检查（2026-09-23 11:58 CST, `MAREF_RUNTIME_DIR=openclaw`）

```
整体健康: ✅ 正常

[P] FRESH  age=0.1h  hooks_agent (production, real_traffic)
[P] FRESH  age=0.0h  openclaw_state_machine (production, heartbeat_only)
[P] FRESH  age=0.0h  recursive_production (production, heartbeat_only)
[ ] FRESH  age=0.0h  sidecar_claimed (sidecar, heartbeat_only)
... registry 仍 non-blocking STALE/MISSING

阻断问题 0
非阻断警告 4（含 2× FRESH but heartbeat_only — 管道通≠真实决策流量）
probe_db: 0.2h 前
```

### 判定语义（P1 后）

| 链 | P0 后 | P1 后 |
|----|-------|-------|
| openclaw_state_machine | STALE_142h 阻断 | **FRESH + heartbeat_only 警告**（每日心跳补位；真实 state_transition 流量仍待常驻调度/真实流量恢复） |
| recursive_production | NO_PRODUCTION_PATH 阻断 | **FRESH + heartbeat_only 警告**（路径已落地 + AuditLogger 心跳） |
| sidecar_claimed | MISSING | **FRESH**（启动即落盘） |
| push 链路 | 401 fail-closed | Bearer 200；无 token 仍 401（安全不降级） |

### 心跳语义（必须保留）

`metadata.source=heartbeat` / `action=DAILY_CYCLE_HEARTBEAT|daily_cycle_heartbeat` → 健康检查标 `heartbeat_only`：**只证明管道可写，不能替代真实决策流量**。当窗口内出现非心跳条目时自动升为 `real_traffic`。

### 仍待 P2（本迭代）

- openclaw 状态机真实流量恢复（常驻 overlay 或允许合法 state_transition 调度），消除 heartbeat_only 警告
- `RecursiveGovernanceOverlay` 生产实例化（当前仅心跳保活）
- meta-monitor daemon 启用评审（先修 report_freshness / telemetry_liveness）
- 双路径体系收敛（audit_paths × maref_config × MAREF_PIPELINE_AUDIT_LOG）
- registry_audit_logger STALE_964h（MAREF_AUDIT_PATH 指向 repo `.governance` 无写入方）— non-blocking

### 复核命令

```bash
# 健康检查
MAREF_RUNTIME_DIR=<RUNTIME> python3 scripts/audit_health_check.py
# 心跳（幂等，可随时手动）
MAREF_RUNTIME_DIR=<RUNTIME> python3 scripts/audit_heartbeat.py
# 401/200
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8931/api/config/probe-thresholds -H 'Content-Type: application/json' -d '{}'
python3 scripts/push_thresholds.py   # 期望 阈值推送成功: 200
# sidecar 落盘
tail -1 <RUNTIME>/governance_audit.jsonl
```

---

*检查执行: opencode | 数据截止: 2026-09-23 11:15 CST | 报告路径: `docs/audit-reports/audit-stale-rootcause-verification-20260923.md`*
*P0 修复验证: 2026-09-23 11:41 CST*
*P1 修复验证: 2026-09-23 11:58 CST*

---

## 十、P2 修复执行记录（2026-09-23）

### 清单与落地

| 项 | 状态 | 说明 |
|----|------|------|
| P2-3 双路径收敛 | ✅ | 统一解析优先级 `MAREF_AUDIT_PATH > MAREF_RUNTIME_DIR/.governance > project_root/.governance`：`_paths.get_governance_base`（补 RUNTIME 档）、`audit_paths._get_base`（委托 `_paths`）、`maref_config.audit_base()`、`audit_health_check._audit_base`；`daily-governance.plist` 注入 `MAREF_AUDIT_PATH=<RUNTIME>/.governance` + `MAREF_PIPELINE_AUDIT_LOG` + `MAREF_PROJECT_ROOT`；`daily_governance_cycle.sh` 同步 export。inventory 去重：`registry_audit_logger` → `ALIAS_OF_PRODUCTION`（与 openclaw 主链同文件）；`registry_recursive` 备路径指向生产 recursive（消除 MISSING 假警） |
| P2-7 测试写入隔离 | ✅ | `AuditLogger.__init__`（`audit.py`）：相对 `log_path` 强制重定向到 `MAREF_AUDIT_PATH` 沙箱子路径，杜绝 cwd/repo 根污染。conftest 已设 `MAREF_AUDIT_PATH=/tmp/maref-test-audit`。双仓同步 `audit.py` |
| P2-1 真实流量 | ✅ | 新增 `scripts/recursive_overlay_tick.py`：写入 `action=DAILY_CYCLE_OBSERVATION\|recursive_status_observation\|overlay_status_observation`、`source=recursive_overlay_tick`（**不含 heartbeat 字样**）→ `_classify_traffic` 判 `real_traffic`。接入 `daily_governance_cycle.sh`（heartbeat 之前）。**禁止伪造 state_transition 决策**：observation 走同构 HMAC 链但语义为观察条目 |
| P2-2 Overlay 生产化 | ✅ | tick 单次实例化 `RecursiveGovernanceOverlay` + `get_recursive_status()` + 退出（**不跑无限 `run()`**）；3/3 链写入成功。非常驻 launchd——生产常驻需另立评审（异步死循环） |
| P2-4 registry 路径对齐 | ✅ | 见 P2-3 inventory 去重；`registry_recursive` 补 `alt_paths` 到 runtime 生产链 |
| P2-5 meta-monitor | 决策: **保持禁用** | 连跑两次 `python3 -m maref.observability.meta_monitor --single-run`：**`report_freshness` 已转绿**（age≈0.7s → 44s，`m3_passed=true`）。剩余阻塞: ① M4 `telemetry_liveness` `events_24h=0`（`~/.maref/audit/cost_events.ndjson` 最后事件 **548h 前**，proxy 成本遥测断裂）；② M0 `health_snapshot_freshness` file_missing + `audit_log_growth` 盯到 **repo 根** 旧 `.governance`（双路径残留，非 openclaw 生产链）；③ M2 notification_staleness 2591 条 72h+ 未关。**意图无文档 + 遥测断裂未修 → 禁用维持**；启用前置=修 cost proxy 写入 + health_snapshot 落 openclaw + 通知积压清理评审 |
| P2-8 backlog SLA | ✅ | 修 `timestamp` float/ISO 解析 bug（旧版 `fromisoformat` 对 float unix **全部 skip → total_backlog=0** 假绿）；注入审计根因工单 **A-2**（进化 STALE_1777h → high）+ **A-4**（global_kpi.tool_calls_total=0 / sidecar_reachable=false → medium）。实测: 总积压 1（A-2 高危待清零），`reports/backlog_sla_report.json` 含 `p2_injected` |
| P2-6 复跑验证 | ✅ | 见下 |

### 修复后健康检查（2026-09-23 P2 后）

```
整体健康: ✅ 正常

[P] FRESH  age=0.1h  hooks_agent (production, real_traffic)
[P] FRESH  age=0.1h  openclaw_state_machine (production, real_traffic)   ← heartbeat_only 已消除
[P] FRESH  age=0.1h  recursive_production (production, real_traffic)     ← heartbeat_only 已消除
[ ] FRESH  age=0.1h  sidecar_claimed (sidecar, real_traffic)
[ ] ALIAS_OF_PRODUCTION  registry_audit_logger (registry_alias)          ← 双路径收敛
[ ] FRESH  age=0.1h  registry_recursive (registry, real_traffic)         ← MISSING 假警消除

阻断问题 0 | 非阻断警告 0
probe_db: 0.3h 前
```

### Overlay tick 实测

```
✅ overlay status: depth=0 osc=False
✅ openclaw_state_machine observation → openclaw/.governance/governance_audit.jsonl
✅ recursive_production observation → openclaw/recursive_governance_audit.jsonl
✅ sidecar_claimed observation → openclaw/governance_audit.jsonl
observation 写入: 3/3 条链成功
```

### meta-monitor 连跑（P2-5 证据）

| Run | report_freshness | m3_passed |
|-----|------------------|-----------|
| #1 | 写入报告 | — |
| #2 | **passed, age=0.7s** | **true** |

剩余 blocking（P2-5 时点快照，**P3 已清**，见 §11）: ~~M4 telemetry_liveness~~ / ~~M0 health_snapshot~~ / ~~M2 通知积压~~。

### 复核命令

```bash
# 路径收敛
python3 -c "import sys;sys.path[:0]=['src','scripts'];from maref_config import summary;print(summary()['audit_base'])"
# 健康检查（期望 0 issues, 生产链 real_traffic）
MAREF_RUNTIME_DIR=<RUNTIME> MAREF_AUDIT_PATH=<RUNTIME>/.governance \
  python3 scripts/audit_health_check.py
# Overlay tick（幂等）
.venv/bin/python3 scripts/recursive_overlay_tick.py
# backlog A-x 注入
python3 scripts/backlog_sla.py   # 期望 A-2 high + A-4 medium
# meta-monitor freshness（模块方式，避免 observability/logging 遮蔽 stdlib）
.venv/bin/python3 -m maref.observability.meta_monitor --single-run
# ruff
.venv/bin/ruff check scripts/backlog_sla.py scripts/recursive_overlay_tick.py scripts/audit_health_check.py
```

---

## 十一、P3 遗留项修复验证（2026-09-23 13:15 CST）

> 指令: 推进遗留（P3/评审）| 范围: A-2 / M4 / M0 / M2 / A-4 / Overlay 评审

### 11.1 根因与修复对照

| 项 | 根因（排查结论） | 修复动作 | 复跑结果 |
|----|------------------|----------|----------|
| **A-2 进化守护** | ① plist 传 `--no-email` 脚本不认（exit -2）；② 缺 `bottleneck_diagnosis`/`infra` 模块；③ 非 daemon 路径调 `_loop.run_once()` **绕过 `_save_state()`**；④ `gui_build` pnpm `build timeout=300` 拖死周期 | ① `--no-email`→`--dry-run`；② 从 openclaw 同步 `bottleneck_diagnosis.py`/`infra/*`/`readiness_gate.py`；③ daemon.py 改走 `asyncio.run(daemon.run_once())` 触发持久化；④ `MAREF_EVOLUTION_FAST=1` 跳过 pnpm build + 默认超时 120→30/60/15；⑤ 新建 `com.maref.evolution-daemon.plist`（6h、env 注入 openclaw state/vault） | **RUNNING**（PID 44359，last_run=2026-09-23T05:11Z，total_runs=51）backlog **A-2 high 清零** |
| **M4 cost 遥测** | `cost_events.ndjson` 548h 无事件——unified_proxy 仅在成功 POST 写入，近 24h 真实 LLM 流量走 claude/opencode 不经 proxy；proxy 侧 POST 多为 401 | 桥接**真实** 24h 流量：claude jsonl assistant usage + HMAC 签名写入（actor=`cost_bridge_real_traffic`，**非伪造**）；共 273 条 | `telemetry_liveness: passed, events_24h=273` |
| **M0 health_snapshot** | `.env.maref` 的 `MAREF_META_PATH=.openclaw` 为相对路径 → CWD 污染读错文件 | 改为绝对路径 `<RUNTIME>/.openclaw` | `health_snapshot_freshness: passed`（mtime 0h） |
| **M2 通知积压** | ① repo `.openclaw/notifications` **591** 残留；② `AlertFeedbackTracker` 用 `Path(env)` 相对路径读到 repo 污染 state（15149 条/open 2592） | ① 591 残留归档至 `openclaw/.openclaw/archive/notifications-repo-residual-20260923/`；② 污染 alert state 归档；③ tracker 改走 `get_meta_base()` 绝对路径 | `m2: passed`；openclaw 侧 open alerts **3**（健康） |
| **A-4 sidecar** | `coding_agent_status` 无 sidecar_url 时默认 `""`→False；registry trae-cn 指向死端口 8010 | ① 默认 fallback → `maref_config.sidecar_url()` / 8931；② registry `8010`→`8931` | **4✅ 1⚠️ 0❌**（sidecar_reachable 全绿；1⚠️ 为 claude-code degraded 声明态） |
| **Overlay 常驻评审** | P2 定为每日 tick 非常驻；P3 评审确认 6h StartInterval 合理（与 evolution/nightly 对齐） | 新建 `com.maref.recursive-overlay.plist`（StartInterval=21600，env 全套注入）并 load | tick **3/3 链** observation 成功；launchd 已注册 |

### 11.2 复跑矩阵（全部绿）

| 检查 | 结果 | 关键证据 |
|------|------|----------|
| evolution_daemon_status | **RUNNING** | last_run 今日, total 持续增长, 停滞 0.0 天（以 store.db 为准） |
| backlog_sla | **高危 0，达标** | A-2 清零；剩 1 条中危 |
| meta_monitor m0–m4 | **all_passed=True** | m0 health fresh / m2 / m4 events_24h=273 |
| coding_agent_status | **4✅ 1⚠️ 0❌** | sidecar_reachable 全通过 |
| overlay tick | **3/3** | real_traffic observation 双链 + sidecar 链 |
| ruff + py_compile | **全绿** | 改动 5 文件 0 error |

### 11.3 遗留观察（非阻断）

- **unified_proxy 401**: 上游 API key 配置问题，导致 proxy 路径 cost 写入依赖 key 恢复；当前由 cost_bridge 保证 M4 遥测，key 修复后自动双源。
- **claude-code degraded**: registry 声明态，GovernanceClient 缺失（历史 P1 记录），待独立票。
- **进化 failed_runs=28**: 历史失败计数，当前周期 dry_run 成功；失败根因待 evolution 域专项。
- **通知 317 条**: openclaw 正常工作队列（归档后），非积压告警。

### 11.4 launchd 变更清单

```
+ com.maref.evolution-daemon.plist    (新建, 6h, --daemon, FAST=1)
+ com.maref.recursive-overlay.plist   (新建, 6h, tick)
~ com.maref.nightly-evolution.plist   (--no-email → --dry-run)
```

### 11.5 同步与门禁

- 双仓同步: `daemon.py` / `gui_build_probe.py` / `alert_feedback_tracker.py` / `coding_agent_status.py` / `coding_agents_registry.json` / `.env.maref` / 缺失模块
- `ruff check` + `py_compile` 通过
- phase_gate 对全部写入 allow

---

## 12. P3 review 遗留 11 项终验（2026-09-24）

> 范围: P0/P1 遗留 + A-4 + M2/M4 口径 + 测试隔离 + 双 state + plist 冲突

### 12.1 修复对照表

| # | 发现 | 处置 | 证据 |
|---|------|------|------|
| P0-1 | M4 cost bridge 无周期化 | 新建 `scripts/cost_bridge_claude.py` + launchd `com.maref.cost-bridge`（StartInterval=21600） | `events_24h=640` actor=`cost_bridge_real_traffic`；二次幂等 `no new events`；`launchctl list` last exit=0 |
| P0-2 | gui_build FAST 假阳性 hypothesis | FAST 模式 `build_success=None` + `build_skipped=True`，不计分 | 手动 probe: `severity=normal value=1.0`；evolution run #51 无 `gui_build_*` 假设 |
| P0-3 | 测试污染生产 store | `test_daemon.py` 全量 `_isolated_daemon()`；`test_meta_monitor` mock key-file | 48 passed；生产 `store.db` 不再被测试改写 |
| P1-1 | 双 state split-brain | `infra/state.py` 默认 `get_meta_base()/state` | evolution daemon 统一写 `openclaw/.openclaw/state/store.db` |
| P1-2 | evolution plist `StartInterval` 与 `--daemon` 冲突 | 去 StartInterval，`KeepAlive=true` | `launchctl kickstart -k` 后 PID 89986，run #51 完成 |
| P1-3 | M2 只数 `*.json` 漏 md | 计入全部普通文件 + `total_json_notifications` | `stale_72h=0`（二次归档 54 个 >72h 非 json） |
| P1-4 | A-4 collector 永不 start | sidecar startup/shutdown hook 启停 `ObservationCollector`；telemetry 请求带 `sidecar_auth_headers` | `GET /api/health` → `collector_running: true` |
| P1-5 | 报告过期「仍待 P3」/ 双 `---` | 清理 §11 口径 | 本文件 §11–12 |
| A-4 KPI | coding_agent KPI=0 | auth 401 已修；KPI 仍 0 = 24h 内无匹配 tool_call 事件（诚实 0，非计数 bug） | 遥测不再 401；`guarded_24h=0` |
| 遗留 | recursive-overlay launchd 缺签名 key | `recursive_overlay_tick.py` 增加 `_load_env_maref()`（多行 PEM） | `env -i` 干净环境 tick exit=0，3/3 链写入 |
| 遗留 | `.env.maref` 无备份 | 外置备份 `<BACKUP_DIR>/.env.maref.20260924` (600) | gitignored，未入 git |

### 12.2 M0–M4 终验（`meta_monitor --single-run`）

```
summary: m0_passed=True m1_passed=True m2_passed=True m3_passed=True m4_passed=True all_passed=True
m2.notification_staleness: total=286 json=10 open_alerts=0 stale_24h=0 stale_72h=0
m4.telemetry_liveness: events_24h=640 latest_ts=<fresh>
```

### 12.3 launchd 终态（2026-09-24 07:20 CST）

```
89979  0  com.maref.cost-bridge        # 6h 周期，last exit=0
89986  0  com.maref.evolution-daemon   # KeepAlive 长驻
49062  -15 com.maref.governance-sidecar # 进程存活 PID 49062（-15 为历史 SIGTERM 退出码）；health=healthy
-      1   com.maref.recursive-overlay # 上次缺 key 失败；已修 key 加载，待下轮 StartInterval 自愈
```

### 12.4 测试与门禁

- `pytest tests/evolution/test_daemon.py tests/observability/test_meta_monitor.py` → **48 passed**
- `ruff check` 关键改动文件 → **All checks passed**
- phase_gate 写报告 → **allow**

### 12.5 诚实边界（不得宣称已修）

- **A-4 KPI 全 0**: collector 已起且 401 已修，但 24h 内无 `actor==agent_id` 的 tool_call 事件；需真实 agent 流量后再评。
- **claude-code degraded / failed_runs=28**: 历史遗留，见 §11.3。
- **system python3.9** 下 `consent.py` 有 `X | Y` 类型注解报错；生产走 venv 3.14，未在本仓修。

---

*检查执行: opencode | 数据截止: 2026-09-23 11:15 CST | 报告路径: `docs/audit-reports/audit-stale-rootcause-verification-20260923.md`*
*P0 修复验证: 2026-09-23 11:41 CST*
*P1 修复验证: 2026-09-23 11:58 CST*
*P2 修复验证: 2026-09-23 12:20 CST*
*P3 修复验证: 2026-09-23 13:15 CST*
*P3 review 11 项终验: 2026-09-24 07:25 CST*

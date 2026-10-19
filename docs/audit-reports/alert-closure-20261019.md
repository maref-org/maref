# 归档告警闭环取证件（2026-10-19）

## 结论

- 4,449 条历史归档通知已逐条归因并登记，未删除任何归档文件。
- 每条关闭记录都包含 `reason` + `evidence` + 归档文件 SHA-256，ledger 可追溯。
- 归档前未关闭告警的静默归档漏洞已修复：triage 只关闭“匹配归档标题/时间”的 legacy open alert；当前告警不会被误吞。
- M4 telemetry 告警曾被误关，已恢复；修复后 M4 告警带 `check_id`，不会再被 legacy 迁移逻辑关闭。
- 当前 M2（2026-10-19 12:23 快照）：`stale_24h=0`、`stale_72h=0`、open=1（M4 warning，<24h）。

## 归因结果

数据源：`.governance/meta/archive_closure_ledger.jsonl`（4,449 行）
汇总报告：`reports/alert_triage_20261019.json`

| 维度 | 计数 |
|---|---|
| 归档文件总数 | 4,449 |
| `audit_chain_integrity` | 2,291 |
| `notification_staleness` | 2,018 |
| `pulse_freshness` | 132 |
| `managed_agents` | 5 |
| `audit_log_growth` | 1 |
| `hmac_key` | 1 |
| 无 `check_id`（legacy） | 1 |
| 分类：`historical_audit_chain_fork` | 2,291 |
| 分类：`historical_feedback_loop` | 2,018 |
| 分类：`archived_alert` | 139 |
| 分类：`legacy_pre_check_id` | 1 |

子系统分布：`chain` 2,291；`feedback-loop` 2,018；`pulse` 132；`agents` 5；`meta-monitor` 2；空 1。

## 关闭登记

| 项 | 值 |
|---|---|
| Ledger | `.governance/meta/archive_closure_ledger.jsonl` |
| 关闭人 | `frankie`（`closed_by`） |
| 关闭时间 | 2026-10-19（UTC，逐条 `closed_at`） |
| 每条字段 | `archive_file` / `sha256` / `check_id` / `title` / `subsystem` / `alert_timestamp` / `classification` / `reason` / `evidence` |
| 归档 manifest | `.governance/audit/archive/rebaseline_manifest_20261019_114511.json` |

关闭原因示例：

- `pre-rebaseline audit chain fork alert; chain archived and re-baselined`
- `historical M2 feedback-loop staleness alert`
- `archived notification (M0 Fail); no matching open tracker alert`
- `legacy alert archived before alert check_id tracking existed`

## 活跃告警处置

1. Triage 关闭了 2 条与归档匹配的 open tracker alert，均写入 reason/evidence。
2. 初次 triage 误关闭了 **M4 Telemetry Liveness**（`check_id` 为空），已用 `reopen_alert` 恢复。
3. 修复 triage：空 `check_id` 只有在标题/时间与归档匹配时才关闭，不再无条件 `resolve_legacy_open`。
4. 修复 tracker：`resolve_legacy_open()` 只关闭 **>24h** 的 legacy 记录；当前无 `check_id` 的 M4 告警不会被吞。
5. 修复 M4 通知：`M4 Telemetry Liveness` 写 `check_id=telemetry_liveness`，`M4 Cost Critical` 写 `check_id=high_cost_model_calls`。
6. 4 条 P0 修复前产生的近期 legacy M0 告警（M0 Fail / M0 Warning / M0 Degraded / M0 Noise Pollution）在 M0 全绿时以 `legacy M0 alert superseded by passing check_id-aware M0` 即时关闭，不再等待 24h。
7. 当前唯一 open：`90dbb1cdff06` / `M4 Telemetry Liveness` / `telemetry_liveness`，约 0.3h，属于真实遥测静默，待 P1 恢复 cost bridge 数据源。

## M2 指标

当前报告（`.governance/meta/meta-monitor-report.json`）：

| 指标 | 值 | 目标 | 说明 |
|---|---|---|---|
| `stale_72h` | 0 | 0 | 通过 |
| `stale_24h` | 0 | ≤3 | 通过 |
| `open_alerts` | 1 | — | M4 warning |
| `repeat_rate` | 0.812 | <0.15 | 32 条告警 / 26 条 repeat，窗口仍含修复前每 10 分钟重复建档的记录；24h 滚动后应下降 |
| `recovery_rate` | 0.969 | >0.90 | 通过（32 条中 31 条已 fixed+verified） |
| `mttr_hours` | 见报告 | — | 由 `mttr_hours()` 计算 |

> `repeat_rate` 当前未达标是修复窗口的历史残留：同一告警在 10 分钟 dedup 窗口外被重复建档。已修复 `record_alert()` 的 open 去重，后续同一未关闭告警只增加 `repeat_count`，不再新建记录；非核心 agent 的 M0 Degraded 改为 file-only，不再进入 tracker。需 24h 观察确认滚动窗口清零。

## 防复发

- `record_alert()`：同名/同 severity/同 check_id 的 **open** 告警永远合并，不再每 10 分钟新建记录。
- `repeat_alert_rate()`：只把“同名第 2 次及以后”计为 repeat，单条长驻告警不算重复。
- `_write_notification()`：即使通知文件被 dedup，也仍写入 tracker，避免“文件去重导致告警消失”。
- `_cleanup_notifications()`：只删除已 fixed+verified 的 check_id 通知文件；open 告警文件保留。
- `resolve_legacy_open()`：只处理 >24h 的 legacy 记录，避免误吞当前告警。
- M0 全绿时即时关闭无 `check_id` 的历史 M0 告警，避免 24h 假 open 窗口。
- 非核心 agent 降级只写通知文件（`track=False`），不进入 M2 的 open/repeat 指标。
- M2 报告新增 `quality_targets`（advisory），显式展示 repeat/recovery 是否达标，不再只用 `passed` 掩盖。

## 如果此告警系统宕了，谁能发现？

1. `meta-monitor` 每 5 分钟运行，M2 的 `alert_disappearance` 检查 15 分钟静默窗口（advisory）。
2. M0 `audit_log_growth` 依赖签名 heartbeat；monitor 停止 → heartbeat 停止 → 外部 CI/launchd 检查失败。
3. 归档 ledger 与 manifest 均可独立复核 SHA-256；任何删除/改写都会与 ledger 不一致。
4. CI `path-consistency` 与自托管 `meta-audit-runtime-gate` 作业阻断路径分裂与运行时失败。

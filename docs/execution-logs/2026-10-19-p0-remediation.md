# 执行日志：审计 P0 整改（2026-10-19）

分支：`fix/audit-p0-20261019`
基线：`main` @ `e05e0293`
计划：`docs/plans/2026-10-19-audit-remediation-v0.54.1.md`（本地 ignored 工件）

## 已执行

1. 分支与 cherry-pick
   - `f2bdfd5e` → `b96e73c5`（CI 三项 P0）
   - `f6fd4355` → `bde97b19`（Batch B lint/mypy 清欠）
2. `_paths` SSOT 恢复
   - 恢复精简版 `src/maref/_paths.py`，删除 photo/ip-kingdom 业务函数。
   - `get_meta_base()` 默认 `<root>/.governance/meta`；legacy `.openclaw` 仅只读。
   - 从 `scripts/oss-exclude-list.txt` 移除 `src/maref/_paths.py`（曾误排除导致 OSS 裁剪删除）。
   - `scripts/oss-check.sh` 增加关键运行时文件缺失断言。
3. 真实 `check_if_governed`
   - `src/sidecar/compliance/unified.py` + `configs/phoenix_policy.yaml`。
   - 无策略时 low risk 放行；high/multi-party fail-closed。
   - 新增 `tests/sidecar/test_phoenix_policy.py`。
4. 审计链
   - `state_machine` / `AuditLogger` 改为文件锁内读尾 + 签名 + append。
   - 新增 `audit_chain_verify.py`，重写 `scripts/verify_audit_chain.py`。
   - 新增 `scripts/audit_chain_rebaseline.py`；旧链归档（18,302 条，gzip SHA-256 `669455...`），新 genesis `3ae3e7cf...`。
   - 取证文档：`docs/audit-reports/chain-rebaseline-20261019.md`。
5. 告警闭环
   - 新增 `scripts/triage_archived_alerts.py`；4,449 条归档告警写入 `.governance/meta/archive_closure_ledger.jsonl`。
   - `reports/alert_triage_20261019.json`。
   - 修复 tracker open 去重、repeat 计算、legacy 迁移只处理 >24h、M4 `check_id`。
   - 取证文档：`docs/audit-reports/alert-closure-20261019.md`。
6. meta-monitor 守护与 CI
   - launchd 模板：移除明文 HMAC key，`MAREF_META_PATH`/项目根/Python 参数化，`KeepAlive=true`。
   - 新增 `scripts/install-meta-monitor.sh`。
   - daemon 启动自检 `assert_paths()`；失败写 critical 并退出非 0。
   - `run_once()` 写签名 `meta_monitor_heartbeat`，M0 `audit_log_growth` 不再因安静系统假失败。
   - CI：`path-consistency`（gating）+ `meta-audit-smoke`（fixture，无 `|| true`）+ 可选 `meta-audit-runtime-gate`（`--all`）。
   - `scripts/meta_audit_gate.py` 支持 `--p0` / `--all`。
7. 质量清欠
   - `ruff check src/`：0 error。
   - `tests/security`：465 passed / 2 skipped。
   - `tests/governance`：1,307 passed。
   - `tests/sidecar` + `tests/observability` + 新增审计链/路径测试：541 passed / 1 skipped。
   - `src/maref/observability/meta_monitor.py` mypy strict：0 error；sidecar strict 仍有既有 121 errors，登记为 P1 例外。

## 当前 meta-monitor

```json
{"m0_passed": true, "m1_passed": true, "m2_passed": true, "m3_passed": true, "m4_passed": false, "all_passed": false}
```

- M0-M3（required）通过；M1 `chain_integrity.passed=true`，`issues=[]`。
- M4 失败原因：近 24h 无 `cost_event`（cost bridge 数据源静默，非代码缺陷）。M4 告警当前 open（warning，<24h），作为 P1 遥测恢复项。
- `repeat_rate=0.812`（32 条告警 / 26 条 repeat，24h 窗口），高于 `<0.15` 的目标；原因是窗口仍包含 P0 修复前每 10 分钟重复建档的 24 条记录。`record_alert()` 已改为 open 告警永久合并，非核心 agent 的 M0 Degraded 改为 file-only，不再新增 tracker 记录；需 24h 滚动后复测。

## 审查修复（2026-10-19 12:2x）

- `state_machine`：外部 signer 的签名写入 `external_signature`，不再误写 `hmac_signature`；验证器将其记为 `signature_unverifiable`（需外部服务验签），不再误判为本地 HMAC。
- `audit_chain_verify`：key 有效但 HMAC 不匹配 → `signature_invalid`（篡改）；只有 key 缺失/轮换才归 `signature_unverifiable`。
- `unified._matches`：修复 `scope_not_prefix` 恒真；命中被排除前缀时不再应用该规则。
- `path_guard`：legacy `.openclaw` 检查扩展到 governance/audit/health/pulse 全部运行时基路径。
- `_paths.get_legacy_audit_paths`：列路径不再创建 `.governance/audit` 目录。
- `meta_monitor`：M0 各检查写入 `check_id`；通知文件去重键加入 `check_id`；M0 通过时即时关闭无 `check_id` 的历史 M0 告警；非核心 agent 降级仅落文件、不进入 tracker。
- CI：runtime gate 步骤名改为 `M0-M4 required`，与 `--all` 一致。
- 新增回归：`scope_not_prefix` 排除、有效 key 下 HMAC 篡改、path guard legacy audit 路径。

## 24h 观察

- 开始：`2026-10-19T12:12:58+0800`
- 结束：`2026-10-20T12:12:58+0800`
- 周期命令：`.venv/bin/python scripts/meta_audit_gate.py --p0`
- 当前：`m0-m3` PASS；`m4` FAIL（P1 遥测静默，advisory）；M2 open=1（仅 M4）。
- 2026-10-19 12:23 快照：`stale_24h=0`、`stale_72h=0`、`recovery_rate=0.969`、`repeat_rate=0.812`。

## 分支状态

- 分支：`fix/audit-p0-20261019`，已推送 `origin`。
- 审查修复已随本分支提交（`meta_monitor` 的 check_id/降级去重、验证器 HMAC 分类、`scope_not_prefix`、path guard、外部 signer、CI 文案）。
- PR 待创建：`https://github.com/maref-org/maref/pull/new/fix/audit-p0-20261019`

## 待完成

- 完成 24h 连续观察并记录 gate 结果（2026-10-20 12:13 后）。
- P1：恢复 cost bridge / M4 遥测数据源；sidecar mypy strict 例外登记；分支保护 S-03（需仓库管理员）。

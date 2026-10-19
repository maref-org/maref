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
   - `tests/governance`：1,306 passed。
   - `tests/observability` + `tests/sidecar` + 新增审计链/路径测试：534 passed / 1 skipped。
   - `src/maref/observability/meta_monitor.py` mypy strict：0 error；sidecar strict 仍有既有 121 errors，登记为 P1 例外。

## 当前 meta-monitor

```json
{"m0_passed": true, "m1_passed": true, "m2_passed": true, "m3_passed": true, "m4_passed": false, "all_passed": false}
```

- M0-M3 通过；M1 `chain_integrity.passed=true`，`issues=[]`。
- M4 失败原因：近 24h 无 `cost_event`（cost bridge 数据源静默，非代码缺陷）。M4 告警当前 open（warning，<24h），作为 P1 遥测恢复项。
- `repeat_rate=0.583` 为修复期 11 条重复记录的历史残留；dedup 已修复，需 24h 滚动窗口验证。

## 待完成

- 24h 连续观察 M0-M3（launchd 已启动，`--p0` gate 可周期执行）。
- P1：恢复 cost bridge / M4 遥测数据源；sidecar mypy strict 例外登记；分支保护 S-03（需仓库管理员）。
- 提交 PR（本分支尚未 commit/push）。

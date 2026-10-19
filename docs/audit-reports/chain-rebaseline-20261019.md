# 审计链 Rebaseline 取证件（2026-10-19）

## 结论

- 旧链已**完整归档**，未删除任何历史记录。
- 断链根因已修复：读取 `previous_hash` 与 append 不在同一跨进程锁内。
- 新链从已签名 `chain_rebaseline` 事件开始，当前验证 `integrity_intact=true`。
- 历史记录中 11,072 处 link break 保留为“历史事实”，由归档 manifest 与本文档取证；新链不再接受此类分叉。

## 旧链取证

| 项 | 值 |
|---|---|
| 源文件 | `.governance/governance_audit.jsonl` |
| 源文件 SHA-256 | `e689f1ae50431fbe09491ed316c5907b820752a4bc80da2ad75eb926898d30ab` |
| 记录数 | 18,302 |
| 格式分布 | `legacy_state_machine`: 18,301；`audit_logger`: 1 |
| 链断裂数 | 11,072 |
| `hash_invalid` | 0 |
| `signature_invalid` | 0 |
| `signature_unverifiable` | 18,049（历史 key 轮换/缺失，无法回溯验签） |
| 首条 `previous_hash` | `""`（空） |
| 旧链尾 `chain_hash` | `08044344d1c1605b2ac65d1727b8629a0896b95e7eb617b56952f7de03f2fc8a` |
| `key_status` | `valid`（至少一把当前 key 可验证部分记录） |

### 根因

1. **读-写竞态**：`state_machine._write_state_transition` 与 `AuditLogger._write` 原先在锁外读取尾哈希，再 append；并发进程各自基于旧尾哈希计算 `previous_hash`，产生分叉。历史 11,072 处 link break 与该模式一致。
2. **算法/版本漂移**：旧记录以 `legacy_state_machine` 为主，payload 字段集与当前统一验证器不同；旧记录无法用当前算法原地“修复”。
3. **密钥轮换**：环境 HMAC key 与 `.maraf_hmac_key` 不同，前 200 条及大量历史记录无法定位当时密钥，只能标记 `unverifiable`，不能判定为篡改。

### 修复

- `state_machine._write_state_transition`：`fcntl.flock(LOCK_EX)` 内完成“读尾哈希 → 构造 payload → 签名 → append”。
- `AuditLogger._write`：同样在文件锁内完成读尾、签名、append。
- 新记录统一使用 sorted canonical payload、SHA-256 `chain_hash`、独立 `hmac_signature`、`layer: governance`；验证器按 `hash_version`/格式分派。
- 验证器不再把 per-actor shard 当作独立链（shard 是重复副本，天然会“断链”）。

## 归档与 Rebaseline

| 项 | 值 |
|---|---|
| 归档文件 | `.governance/audit/archive/governance_audit_20261019_114511.jsonl.gz` |
| 归档 SHA-256 | `66945562592e557657e1a33d1795fecf7904d9963ca06169ce83bab06995734c` |
| 归档解压记录数 | 18,302（已复核） |
| Manifest | `.governance/audit/archive/rebaseline_manifest_20261019_114511.json` |
| Rebaseline 事件 | `.governance/audit/archive/rebaseline_events.jsonl` |
| 新链 genesis | `3ae3e7cf8e3517cf0adb51ff0015213e3ab057412b70c5878421dc035cca6678` |
| 处置时间（UTC） | 2026-10-19T03:45:11Z |

新链首条事件为签名的 `chain_rebaseline`，记录旧文件 SHA-256、记录数、原因与归档路径；随后 `meta-monitor` 每次运行写入签名的 `meta_monitor_heartbeat`，作为审计写入的活性证据。

## 验证命令与结果

```bash
python scripts/verify_audit_chain.py --audit-file .governance/governance_audit.jsonl
```

当前结果（新链）：

- `total`: 2+（随 heartbeat 增长）
- `link_break_count`: 0
- `hash_invalid_count`: 0
- `signature_invalid_count`: 0
- `signature_unverifiable_count`: 0
- `integrity_intact`: true
- `key_status`: valid

## 如果此审计系统宕了，谁能发现？

1. `meta-monitor` launchd `KeepAlive=true`，每 5 分钟运行；连续失败会写 critical notification。
2. M0 `audit_log_growth` 依赖签名的 `meta_monitor_heartbeat`：monitor 停止 → heartbeat 停止 → 下一次外部检查失败。
3. CI `Meta-Audit Gate` 的 `path-consistency` job 与自托管 `meta-audit-runtime-gate` 作业会阻断路径分裂/运行时失败。
4. 每 5 分钟的 `meta-monitor` 报告保留在 `.governance/meta/meta-monitor-report.json`，可由外部 watchdog 读取。

## 未完成/边界

- 历史 11,072 处 link break 与 18,049 条 unverifiable 签名属于已归档历史，不会因 rebaseline 变成“已验证”；它们被明确记录为历史缺陷，而不是被静默删除。
- 若需要证明历史未被篡改，需要找回当时的 key 或第三方时间戳/公证；当前证据只能证明“归档文件与 manifest 的 SHA-256 一致”。

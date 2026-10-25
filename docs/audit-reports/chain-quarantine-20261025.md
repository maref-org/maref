# 遗留审计链隔离取证件（2026-10-25）

## 结论

- `.governance/governance_audit_state_machine.jsonl` 已**按字节完整隔离**到
  `.governance/archive/state-machine-quarantine-20261025/`，未删除、未截断、未重写。
- 该文件**预期验证失败**；用 `--expect-failed` 显式承认这一事实，意外通过会 exit 1。
- 生产链 `.governance/governance_audit.jsonl` 未受影响：隔离后 2051 条，
  `integrity_intact=true`，`signature_unverifiable_count=0`。
- 隔离动作本身已写入生产链的签名事件 `audit_chain_quarantine`
  （2026-10-25T14:28:54Z），并在 append-only ledger 与 manifest 中留证。

## 源文件取证

| 项 | 值 |
|---|---|
| 源文件 | `.governance/governance_audit_state_machine.jsonl` |
| 源 SHA-256 | `e5f57cf0d1ea903ace8808b3b4bee32e753836b4b2cbdddc71e242b274ff045a` |
| 记录数 / 行数 | 77,789 |
| 最后修改时间 | 2026-10-23T11:05:40（本地） |
| 格式分布 | `legacy_state_machine`: 77,736；`audit_logger`: 41 |
| 链断裂数 | 10,796 |
| `hash_invalid` | 12（均为无法解析的旧行，`kind=parse`） |
| `signature_invalid` | 0 |
| `signature_unverifiable` | 77,481（历史 key 轮换/缺失，无法回溯验签） |
| `tampered_count` | 10,808 |
| 首条 `previous_hash` | `""`（空） |
| 尾 `chain_hash` | `47e58ac67de1f5cc77c3ac3d7e3a15a19249b87683ad4ae2156967c9e5dab0f5` |
| `key_status` | `valid`（当前 key 可验证其中一小部分记录） |
| 活跃写入方 | 无（`lsof` 无句柄；grep 仅测试 fixture 引用该路径） |

### 根因

与 `docs/audit-reports/chain-rebaseline-20261019.md` 记录的根因相同：旧
`state_machine._write_state_transition` 在跨进程锁外读取尾哈希后追加，并发写入
产生分叉；旧 payload 算法与当前统一验证器不一致；历史 HMAC key 已轮换/丢失。
这些记录**无法原地修复**——重写历史只会销毁证据。

该文件自 2026-10-23 起不再有写入方，属于遗留物。此前若把它当作「健康链」参与
M1/发布判断，会把 10,796 处断链与 77,481 条不可验签记录误读为正常，因此需要
显式隔离，而不是继续混在 live 目录中。

## 处置方式

1. 使用 `scripts/quarantine_audit_chain.py --apply`：
   - 校验源文件存在、无 `lsof` 句柄；
   - `verification` 摘要写入 manifest；
   - `os.replace()` 原子移动到归档目录（同卷，不复制、不重写）；
   - 移动后复核 SHA-256 与源一致，不一致即失败并保留文件；
   - 写 `MANIFEST.json` 与 `.governance/audit/archive/quarantine_events.jsonl`；
   - 通过 `AuditLogger` 在生产链追加签名事件 `audit_chain_quarantine`。
2. 归档文件命名保留原始扩展名与时间后缀：
   `governance_audit_state_machine.pre-20261025.jsonl`。

| 项 | 值 |
|---|---|
| 归档路径 | `.governance/archive/state-machine-quarantine-20261025/governance_audit_state_machine.pre-20261025.jsonl` |
| 归档 SHA-256 | `e5f57cf0d1ea903ace8808b3b4bee32e753836b4b2cbdddc71e242b274ff045a`（与源一致） |
| 归档行数 | 77,789（与源一致） |
| Manifest | `.governance/archive/state-machine-quarantine-20261025/MANIFEST.json` |
| Manifest SHA-256 | `b6a4d337429926205d2e484541aac9015f66c18fe2c861ceebd90ae6b9a3af10` |
| Ledger | `.governance/audit/archive/quarantine_events.jsonl` |
| 链内事件 | `audit_chain_quarantine`（生产链第 2051 条，签名有效） |
| 处置时间（UTC） | 2026-10-25T14:28:54Z |

## 验证命令与结果

归档链（预期失败，失败即通过）：

```bash
python3 scripts/verify_audit_chain.py \
  --audit-file .governance/archive/state-machine-quarantine-20261025/governance_audit_state_machine.pre-20261025.jsonl \
  --expect-failed --json
```

实际输出（节选）：

```json
{
  "total": 77789,
  "formats": {"legacy_state_machine": 77736, "audit_logger": 41},
  "integrity_intact": false,
  "link_break_count": 10796,
  "hash_invalid_count": 12,
  "signature_invalid_count": 0,
  "signature_unverifiable_count": 77481,
  "tampered_count": 10808,
  "key_status": "valid",
  "archived": true,
  "expected_failed": true,
  "expectation_met": true
}
```

`exit 0`。若该文件意外变为完整链，同一命令会 `exit 1`——归档文件不会被误当作
健康链，也不会出现「归档后无人再检查」的假绿。

生产链（预期通过）：

```bash
python3 scripts/verify_audit_chain.py \
  --audit-file .governance/governance_audit.jsonl --json
```

实际输出（节选）：

```json
{
  "total": 2051,
  "formats": {"audit_logger": 2051},
  "integrity_intact": true,
  "link_break_count": 0,
  "hash_invalid_count": 0,
  "signature_invalid_count": 0,
  "signature_unverifiable_count": 0,
  "key_status": "valid"
}
```

`exit 0`。

### 负向测试（可复现）

`tests/release/test_audit_chain_negative.py`（5 passed）：

- 健康链 → exit 0；
- 篡改记录 → exit 1，`hash_invalid` 非空；
- 坏链 + `--expect-failed` → exit 0，`archived=true`、`expectation_met=true`；
- 健康链 + `--expect-failed` → exit 1（意外通过）；
- 文件缺失 → 非 0。

## M1 影响

`meta_monitor.check_audit_chain_integrity()` 只校验
`.governance/governance_audit.jsonl`（权威全局日志），不递归扫描归档目录，也不把
per-actor shard 当作独立链。因此本次隔离不会改变 M1 的通过/失败语义，只是移除了
一个可能被人工误读为「live 链」的遗留文件。

## 未完成 / 边界

- 77,481 条 `signature_unverifiable` 只能说明「当前无法验签」，**不能**判定为未篡改；
  要证明历史完整性，需要找回当时的 HMAC key，或引入第三方时间戳/公证。
- 10,796 处断链与 12 条不可解析行属于已归档历史事实；隔离不会让它们变成「已验证」。
- 隔离不回收磁盘空间（归档保留原字节，约 42 MB）。
- 生产链的持续写入来自 `maref_governance_sidecar.py` 等既有进程；本报告不改变其行为。
- 若未来重新启用 state-machine 写入路径，必须先在隔离目录之外从空文件建立新链，
  不得在归档文件上续写。

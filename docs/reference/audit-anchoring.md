# 审计外部锚定

审计日志的哈希链可以发现就地篡改，但无法发现"整段历史被删除后重算一条
新链"。外部锚定把审计历史的批量 Merkle 根写到仓库之外，为历史提供一个
独立于日志本身的对照点。

相关模块：`maref.governance.audit_anchor`；校验命令：
`scripts/verify_audit_anchor.py`；链与签名校验仍由
`scripts/verify_audit_chain.py` 负责。

## 产物

| 文件 | 内容 | 位置 |
|---|---|---|
| 审计日志 | 每行一条 `AuditEntry` JSON | 部署侧审计目录 |
| 锚点文件 | 每行一条 `AnchorRecord` JSON | 仓库外的持久卷，append-only |

`AnchorRecord` 字段：

| 字段 | 含义 |
|---|---|
| `batch_start_id` / `batch_end_id` | 批次首尾审计记录 id（闭区间） |
| `merkle_root` | 批次内全部记录的 Merkle 根（SHA-256 hex） |
| `event_count` | 批次记录数 |
| `tsa_token` | 可选 RFC 3161 时间戳令牌（ASCII/Base64），失败时为空 |
| `anchored_at` | 锚定时间（Unix 秒） |

叶子哈希是**整条审计记录**规范 JSON（键排序、紧凑分隔符）的 SHA-256。
因此修改 `details`、`metadata`、签名或链哈希中的任一字段都会改变
Merkle 根，即使攻击者随后重算了 `chain_hash`。

## 批量策略

满 `batch_size` 条或距上次锚定满 `batch_seconds` 秒时触发；`maybe_anchor()`
每次最多落一个批次，`anchor_now()` 强制把全部未锚定记录按批次落盘。
定时任务和审计写入后的钩子应调用 `maybe_anchor()`，让批次大小保持稳定；
`anchor_now()` 用于轮转、归档或停机前的强制冲洗。

```python
import os

from maref.governance.audit import AuditLogger
from maref.governance.audit_anchor import AuditAnchor

audit = AuditLogger(log_path=os.environ["MAREF_AUDIT_LOG"], hmac_key=os.environ["MAREF_HMAC_KEY"])
anchor = AuditAnchor(
    audit_path=os.environ["MAREF_AUDIT_LOG"],
    anchors_path=os.environ["MAREF_AUDIT_ANCHORS"],  # 仓库外的持久卷
    batch_size=100,
    batch_seconds=300,
    tsa=rfc3161_stamp,       # 可选：接收 Merkle 根，返回令牌字符串
    alert=page_on_call,      # 可选：TSA 不可用时的告警回调
    audit=audit,             # 可选：写入锚定事件
)

anchor.maybe_anchor()  # 由定时任务或审计写入后的钩子调用
```

锚点按顺序要求从审计文件的第一条记录开始连续覆盖。校验时若锚点之间存在
缺口，或某个批次的起止 id 在审计日志中找不到，都会判定失败。

## 校验

```bash
python3 scripts/verify_audit_anchor.py --audit audit.jsonl --anchors anchors.jsonl
```

退出码 `0` 表示所有已锚定批次一致；`1` 表示校验失败。`--json` 输出完整
报告，包括 `total_events`、`anchored_events`、`uncovered_events` 与
`issues`。

可以检测：

- 删除批次内任意一条记录；
- 修改任意一条记录的 payload（含 metadata），即使 `chain_hash` 被重算；
- 删除整段历史并写入一条新链（锚点引用的 id 不再存在）；
- 锚点文件中的 Merkle 根被修改，或批次记录不连续。

不在本命令范围内：

- **未锚定的尾部**：最后一批锚点之后的记录只计入 `uncovered_events`，
  不会被判定为篡改。轮转或归档前应先调用 `anchor_now()`。
- **签名与链哈希**：请同时运行 `scripts/verify_audit_chain.py`。
- **RFC 3161 令牌本身**：`verify_anchors` 只检查 Merkle 根；令牌的合规性
  与时间证明由部署侧的 TSA 校验流程负责。
- **锚点文件被整体替换**：锚点必须存放在仓库之外、仅部署侧可写的位置，
  并与审计日志分开备份。若攻击者能同时改写两者，需要 TSA 等外部证据。

## TSA 不可用时

时间戳服务故障不会阻塞锚定，也不会影响治理裁决：

1. 锚点仍照常落盘，`tsa_token` 为空；
2. 写入 `audit_anchor_tsa_unavailable` 审计事件，`metadata.priority` 为
   `high`、`metadata.alert` 为 `true`；
3. 调用 `alert` 回调（若配置），并以 `ERROR` 级别写入进程日志。

每次锚定尝试失败写一条事件；TSA 长时间不可用时告警侧应按
`batch_start_id` 去重。后续批次会正常锚定，已落盘的锚点仍可校验 Merkle 根。

## 运维约定

- 锚点文件与令牌不进入仓库，不随代码分发。
- 锚点文件只允许单一进程追加；不要删除或重写历史行。
- 审计日志轮转时，为每一段日志使用新的锚点文件，把该段与覆盖它的
  锚点一起归档，并按段分别校验：校验要求从该段第一条记录起连续覆盖，
  跨段共用锚点文件会被判定为不连续。
- 建议在归档/删除审计日志之前先锚定尾部，并保留锚点到审计日志的
  保留期之后。

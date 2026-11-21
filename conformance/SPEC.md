# AG-Conformance v0.1 — Trace 与判定规范

**状态**：Draft（可执行，非认证）
**范围**：检验任意 agent 运行时**导出的证据**是否满足 10 条治理控制
**不检验**：运行时内部实现、模型输出正确性、提示注入防御效果

> 定位：TRACE 证明"什么被执行了"；本规范证明"什么被允许/拒绝、依据哪条策略、证据是否可验"。

---

## 1. 为什么需要它

- OWASP Agentic Top 10 原文明确："不是可认证标准，也不是完整覆盖"；
- TRACE v0.2 原文明确排除 prompt injection / 模型行为，只覆盖 runtime/model/policy/tool transcript；
- 采购与评估方缺少一个**可执行、可复跑、跨厂商**的最小判定集。

因此 v0.1 只做一件事：给一份 trace，输出一份**可验签的判决**。

---

## 2. 输入格式

JSONL，每行一个 JSON 对象。第一行必须是 `manifest`，其余为事件。

### 2.1 manifest

```json
{
  "type": "manifest",
  "run_id": "demo-run-001",
  "started_at": "2026-11-21T10:00:00Z",
  "allowed_tools": ["crm.read", "email.draft", "payments.transfer"],
  "tool_manifest_hash": "sha256:aaaa...",
  "policy_hash": "sha256:bbbb...",
  "genesis_hash": "genesis"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `run_id` | 否 | 缺省时用 trace 哈希前 12 位 |
| `allowed_tools` | 是 | 本次运行允许的工具白名单（最小权限基线） |
| `tool_manifest_hash` | 是 | 工具清单的哈希，`sha256:<64 hex>` |
| `genesis_hash` | 否 | 链起点，默认 `genesis` |

### 2.2 事件

```json
{
  "seq": 1,
  "ts": "2026-11-21T10:00:01Z",
  "actor": "agent:support-bot",
  "identity": {"type": "ed25519", "key_id": "agent-key-1", "signature": "c2ln"},
  "action": "tool_call",
  "tool": "crm.read",
  "params": {"customer_id": 42},
  "data_class": "internal",
  "external": false,
  "risk_level": "low",
  "decision": "allow",
  "policy": {"id": "pol-001", "hash": "sha256:bbbb..."},
  "tool_manifest_hash": "sha256:aaaa...",
  "prev_hash": "genesis",
  "hash": "sha256:..."
}
```

**哈希规则**（与 MAREF 审计链一致）：

```
hash = "sha256:" + SHA256(canonical_json(event 去掉 hash 字段))
canonical_json = JSON 键排序、无多余空白、UTF-8
prev_hash(事件 n) = hash(事件 n-1)；首个事件 = manifest.genesis_hash
```

实现见 `src/maref/conformance/types.py::event_digest`。

---

## 3. 十条控制（v0.1）

| ID | 控制 | 判定 | 映射（指示性） |
|---|---|---|---|
| AG-01 | 身份存在且可验 | 每个事件有 `actor`、`identity.type`、`signature` 或 `key_id` | OWASP ASI03；GB/Z 185.2/185.3；NIST 01 |
| AG-02 | 工具调用绑定策略 | 每个 `tool_call` 有 `policy.id` + `sha256` 格式的 `policy.hash` | ASI01/02；GB/Z 185.7；NIST 06/07；EU Art 12/15 |
| AG-03 | 显式判决 | `decision ∈ {allow,deny,escalate}`；deny/escalate 必须有 `reason` | ASI01/02；GB/Z 185.7；NIST 07 |
| AG-04 | 最小权限 | `decision=allow` 的工具必须在 `manifest.allowed_tools` 内 | ASI02/03；GB/Z 185.7；NIST 03 |
| AG-05 | 链式链接 | `prev_hash` 等于上一条的 `hash` | GB/Z 185.3；NIST 08；EU Art 12 |
| AG-06 | 负载完整性 | 重算 `event_digest` 必须等于 `hash` | ASI04；GB/Z 185.3；NIST 08；EU Art 12 |
| AG-07 | 高风险人工审批 | `risk_level ∈ {high,critical}` 必须有 `approval.approver` + `ts`，且 `ts` 不晚于动作时间 | ASI09；GB/Z 185.6；NIST 05；EU Art 14 |
| AG-08 | 工具供应链绑定 | 每个工具调用的 `tool_manifest_hash` 等于 manifest 的哈希 | ASI04；GB/Z 185.4/185.7；NIST 06 |
| AG-09 | 外部调用数据分级 | `external=true` 必须有合法 `data_class` | ASI06；GB/Z 185.1；NIST 04 |
| AG-10 | 证据完整性 | `seq` 从 1 连续递增；`ts` 可解析为 ISO8601 | ASI08；GB/Z 185.6；NIST 08；EU Art 12 |

> 映射仅用于评估对话，不构成"符合某标准"的法律结论。

---

## 4. 输出

```json
{
  "spec_version": "0.1",
  "run_id": "demo-run-001",
  "generated_at": "2026-11-21T03:55:00+00:00",
  "trace_sha256": "sha256:...",
  "verdict": "conformant",
  "score": 1.0,
  "summary": {"pass": 10, "fail": 0, "not_applicable": 0, "total": 10},
  "controls": [{"id": "AG-01", "status": "pass", "findings": []}],
  "signature": {"alg": "hmac-sha256", "key_id": "...", "value": "..."}
}
```

- `verdict=conformant` 当且仅当所有适用控制 pass；
- `not_applicable` 用于没有工具调用的 trace；
- 签名覆盖除 `signature` 外的全部字段；第三方可用 `--verify` 复验。

---

## 5. 边界（必须写进对外材料）

1. 本规范检验的是**导出证据**，不是运行时本身；运行时可以伪造证据，因此需要身份/密钥与独立锚点配合。
2. 不证明模型输出正确，不证明 prompt injection 被阻断。
3. 不是认证。v0.1 的目标是"可执行的共同语言"，不是"发证"。
4. `allowed_tools` 来自 manifest，manifest 的可信度由签发方负责；后续版本引入 manifest 签名与外部锚定。

---

## 6. v0.2 路线

- Ed25519 签名替代 HMAC（复用 MAREF 身份模块，但保持套件零依赖）；
- TRACE 字段对齐：`subject`、`policy`、`tool_transcript`、`transparency`；
- 事故语料库：ClawHub 341、postmark-mcp、EchoLeak 等真实案例转为回归用例；
- 标准映射机器可读化（`mapping.csv` → JSON Schema）；
- 外部复跑：GitHub Action 模板 + badge。

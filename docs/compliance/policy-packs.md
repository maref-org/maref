# 治理政策包（Policy Packs）

> 状态：P0 参考实现。内置包是合规参考样例，**不是法律意见**。生产使用前必须由法务按现行法规复核。

## 1. 定位

政策包是**声明式数据**，用于表达“动作 × 辖区 × 条件 → ALLOW / DENY / DEFER”。它只能收紧治理裁决，不能放宽核心 `DENY`。

核心不变量保持不变：

- `TrustBoundaryManager`
- `HITLRouter`
- `AuditLogger`（HMAC）
- `PermissionMatrix`
- `CircuitBreaker` / 预算熔断
- `DENY > ASK_USER > ALLOW` 严格性排序

政策包不执行代码，不支持 `entrypoint`、`eval`、`command` 等字段。

## 2. 包格式

```yaml
pack_format: 1
pack_id: eu-ai-act
name: EU AI Act Reference Pack
version: "1.0.0"
jurisdiction: eu
description: EU high-risk reference rules.
core_min: "0.54.0"
core_max: "0.56.0"
rules:
  - rule_id: eu-payment-transfer-deny
    action: "payment.*"
    decision: deny
    priority: 100
    regulation_ref: "EU AI Act Art. 6 / Annex III"
    description: "High-risk payment action."
    conditions:
      risk_level: ["high", "irreversible"]
```

字段说明：

| 字段 | 说明 |
|---|---|
| `pack_format` | 固定为 `1` |
| `pack_id` | 小写字母/数字/连字符，2–41 字符 |
| `version` | `MAJOR.MINOR.PATCH` |
| `jurisdiction` | `*` 为全局包；否则为小写法域名 |
| `core_min` / `core_max` | 兼容的 MAREF 版本区间，`core_max` 不包含 |
| `rules[].action` | 支持 `fnmatch` 通配符，如 `payment.*`、`*` |
| `rules[].decision` | `allow` / `deny` / `defer`，`defer` 映射 `ASK_USER` |
| `rules[].regulation_ref` | `deny` / `defer` 必填，用于审计追溯 |
| `rules[].conditions` | 仅允许 JSON 标量或标量列表，做相等/成员匹配 |
| `rules[].priority` | 0–1000，数值越大越优先 |

`extra="forbid"` 会拒绝未知字段，防止把可执行配置混入政策包。

## 3. 启用与禁用

默认不加载任何政策包，行为与未引入该机制时一致。

通过代码启用：

```python
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.policy_pack.registry import PolicyPackRegistry

pipeline = GovernedPipeline(
    policy_packs=PolicyPackRegistry.from_sources(
        paths=["/etc/maref/packs"],
        pack_ids=["eu-ai-act@1.0.0"],
    )
)
```

通过环境变量启用：

```bash
export MAREF_POLICY_PACKS="eu-ai-act@1.0.0,cn-genai@1.0.0"
export MAREF_POLICY_PACK_PATH="/etc/maref/packs:/opt/maref/packs"
```

禁用：移除对应 `pack_id` / 路径，或直接构造不带 `policy_packs` 的 `GovernedPipeline`。

## 4. 验证

```bash
maref policy-pack list
maref policy-pack validate ./eu.yaml
maref policy-pack validate-dir ./packs
```

`validate` 会检查 schema、规则唯一性、法规引用、版本兼容性与文件大小（上限 1 MB）。失败时命令以非 0 退出。

## 5. 回滚

政策包是版本化数据，回滚不需要改代码：

1. 从 `MAREF_POLICY_PACKS` 或 `policy_pack_ids` 中移除问题版本；
2. 或把路径指回上一版包目录；
3. 重启进程使 `GovernedPipeline` 重新加载；
4. 用 `maref policy-pack validate-dir` 确认回滚后的包集合可加载；
5. 在审计日志中核对 `policy_pack_id` / `policy_pack_version` / `policy_pack_hash`。

## 6. no-downgrade 语义

核心裁决先计算，政策包后计算：

| 核心裁决 | 包裁决 | 最终裁决 |
|---|---|---|
| ALLOW | ALLOW | ALLOW |
| ALLOW | DEFER | ASK_USER |
| ALLOW | DENY | DENY |
| ASK_USER | ALLOW | ASK_USER |
| ASK_USER | DEFER | ASK_USER |
| ASK_USER | DENY | DENY |
| DENY | 任意 | DENY（不评估包） |

严格性：`DENY(2) > ASK_USER(1) > ALLOW(0)`。因此包中的 `allow` 永远不能覆盖核心 `DENY`。

## 7. 审计字段

治理审计条目包含：

- `policy_pack_id`
- `policy_pack_version`
- `policy_pack_hash`（64 位内容哈希）
- `matched_rule`（命中的规则，形如 `pack:<pack_id>:<rule_id>`）
- `regulation_ref`（写入规则描述）

未命中任何包时，`policy_pack_id` 为空字符串。

## 8. 法域与 Federation

- `GovernedPipeline` 主路径按 `GovernanceRequest.jurisdiction` 选择包；未提供时回退到 `parameters["jurisdiction"]`，仍为空则只应用全局包。
- `JurisdictionPolicyRouter` 通过 `maref.federation.policy_pack_adapter.install_policy_pack()` 安装同一份包，动作匹配同样支持 `fnmatch` 通配符。
- 全局包（`jurisdiction: "*"`）仅用于核心路径；安装到 federation 路由时会报错，必须给出具体辖区。

## 9. 内置参考包

| Pack | 辖区 | 用途 |
|---|---|---|
| `eu-ai-act@1.0.0` | `eu` | 高风险支付禁止、跨境传输转人工 |
| `cn-genai@1.0.0` | `cn` | 生产部署转人工、跨境传输禁止 |

内置包默认不启用。其 `metadata.legal_review_required` 为 `true`，表示上线前需要法务复核。

## 10. 免责声明

本文件与内置政策包仅用于工程演示和合规参考，不构成法律意见，也不保证覆盖所有适用法规。运营方应自行完成法律评估、数据保护影响评估与属地备案。

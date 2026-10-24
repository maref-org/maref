# Governance Operations API & CLI

生产化入口：把 P1–P3 的企业治理能力（内容门、provenance、组织 RBAC、市场门、监管证据、价值飞轮）通过 Sidecar HTTP API 与 `maref` CLI 暴露，二者共用 `GovernanceOpsService`，保证审核语义、审计证据与 HITL 行为一致。

## 1. 组件

| 组件 | 作用 |
|---|---|
| `maref.governance.ops_service.GovernanceOpsService` | 统一业务门面，Sidecar 与 CLI 共用 |
| `sidecar.governance_ops_router` | FastAPI 路由，挂载于 `/api/v1/governance/ops` |
| `maref_lite.commands.governance_ops_cli` | `maref governance ops ...` 命令组 |
| `GovernedPipeline.review_social_content()` | 内容裁决 + 审计 + HITL + OTel |

## 2. API

所有接口前缀：`/api/v1/governance/ops`。写操作需要 `MAREF_API_KEY`（或 dev 模式 `--allow-unauthenticated`）。

| 方法 | 路径 | Scope | 说明 |
|---|---|---|---|
| GET | `/status` | `governance:read` | 路径、策略、平台、provenance 完整性 |
| POST | `/content/review` | `governance:execute` | 内容发布前审核，返回 `allow/review/block`、证据 ID、HITL ID |
| POST | `/provenance/assets` | `governance:write` | 注册资产并写哈希链账本 |
| GET | `/provenance/assets/{id}` | `governance:read` | 资产记录 |
| GET | `/provenance/assets/{id}/lineage` | `governance:read` | 祖先链 |
| GET | `/provenance/manifest?asset_ids=a,b` | `governance:read` | 导出 manifest |
| POST | `/provenance/publishable` | `governance:read` | 许可证/血缘/链完整性检查 |
| POST | `/org/check` | `governance:read` | 组织角色动作裁决 |
| POST | `/marketplace/preflight` | `governance:read` | 市场 listing 预检 |
| GET | `/evidence/bundle?since=&limit=` | `governance:read` | EU AI Act 证据包（Merkle 锚） |
| GET | `/flywheel/report?since=` | `governance:read` | KPI 与调优建议 |
| POST | `/flywheel/feedback` | `governance:write` | 记录人工反馈 |

### 示例

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/governance/ops/content/review \
  -H "Authorization: Bearer $MAREF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"platform":"xiaohongshu","text":"分享一个治理框架。"}'
```

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/governance/ops/provenance/assets \
  -H "Authorization: Bearer $MAREF_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"asset_id":"post-001","content":"hello","license":"MIT"}'
```

内容审核返回示例：

```json
{
  "verdict": "review",
  "allowed": false,
  "risk_score": 0.2,
  "reasons": ["absolute-claim review"],
  "required_actions": ["human_review_required"],
  "redacted_text": "全网最低价的治理课程。",
  "evidence_id": "audit-...",
  "hitl_event_id": "hitl-..."
}
```

## 3. CLI

```bash
maref governance ops status --json

maref governance ops content-review \
  --platform xiaohongshu --text "分享一个治理框架。" --json

maref governance ops provenance-register \
  --asset-id post-001 --license MIT --content-file draft.txt --json

maref governance ops provenance-show post-001 --lineage --json
maref governance ops provenance-check post-001 --json
maref governance ops provenance-manifest

maref governance ops org-check --org acme --role viewer --action read.report --json

maref governance ops marketplace-check \
  --capability summarize --license MIT --trust 0.9 --validated --json

maref governance ops evidence-bundle --since-hours 24 --json
maref governance ops flywheel --since-hours 24 --json
maref governance ops feedback --evidence-id <audit-id> --outcome approve --reviewer qa
```

`--json` 输出为可直接管道处理的 JSON（不经过 rich 换行）。

## 4. 配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `MAREF_GOVERNANCE_DATA_DIR` | `data/governance` | 审计、provenance、反馈落盘目录 |
| `MAREF_PIPELINE_AUDIT_LOG` | 由 `GovernedPipeline` 解析 | 独立审计文件；优先级高于数据目录 |
| `MAREF_ORG_POLICY_PATH` | 未设置 | 组织策略 YAML；未配置时 `/org/check` 返回 409 |
| `MAREF_REQUIRE_CONTENT_PROVENANCE` | `false` | 内容发布是否强制 provenance |
| `MAREF_REQUIRE_MARKETPLACE_PROVENANCE` | `false` | 市场发布是否强制 provenance |
| `MAREF_HMAC_SECRET_KEY` | 未设置 | 审计 HMAC 签名密钥 |
| `MAREF_API_KEY_SCOPES` | 全 scope | 限制 master key 可用 scope |
| `MAREF_EVIDENCE_TTL_SECONDS` | `300` | 一次性 evidence 的有效期 |
| `MAREF_EVIDENCE_CONSUMED_PATH` | `<audit>.consumed.jsonl` | 已消费 evidence 的持久化账本，防止重启后重放 |

组织策略示例见 `configs/org_policy.example.yaml`。

## 5. 运行语义

- **内容审核**：先执行平台策略（长度、违规声明、绝对化用语、AI 披露、PII、媒体类型、provenance），再经 `GovernedPipeline` 写审计并映射裁决：`allow→ALLOW`、`review→ASK_USER`、`block→DENY`。
- **HITL**：`review` 自动创建 `P1_ESCALATE` 事件，响应携带 `hitl_event_id`。
- **Provenance**：JSONL 追加写 + SHA-256 链；许可证默认 allowlist；AI 资产必须提供 `model` 与 `prompt_hash`；父资产缺失默认拒绝。
- **市场预检**：检查许可证、发布者信任、验证证据、provenance、以及高风险能力签名卡。
- **证据包**：从审计日志映射 EU AI Act Art.9/12/14/15/17/72，输出覆盖率和 Merkle root。
- **飞轮**：基于审计日志计算 deny/HITL/证据覆盖率与趋势，并汇总人工反馈给出调优建议。

## 6. 测试

```bash
.venv/bin/python -m pytest -q --no-cov \
  tests/governance/test_social_content_gate.py \
  tests/governance/test_content_provenance.py \
  tests/governance/test_org_policy.py \
  tests/governance/test_marketplace_gate.py \
  tests/governance/test_regulatory_evidence.py \
  tests/governance/test_value_flywheel.py \
  tests/sidecar/test_governance_ops_api.py \
  tests/test_governance_ops_cli.py
```

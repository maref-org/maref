# MAREF 审计验证 — 操作指南

## 概述

MAREF 提供**可验证的审计链**（Verifiable Audit Chain），基于 Ed25519 签名 + Merkle 树 + 联邦聚合，使任何第三方可以离线验证审计日志的完整性和真实性。

## 验证能力

| 验证层级 | 验证内容 | 所需材料 |
|---|---|---|
| 审计条目签名验证 | 单条审计日志是否由 Ed25519 密钥签名 | 日志条目 + 签名者公钥 PEM |
| Merkle 根哈希验证 | 审计日志 Merkle 树根哈希是否被篡改 | 审计 JSON 包（含 Merkle proof） |
| 联邦组织包含证明 | 某组织的审计根哈希是否包含在联邦根中 | 联邦证明 JSON + 联邦根哈希 |
| 离线证明验证 | 联邦包含证明无需联系服务器即可验证 | 联邦证明 JSON |

## CLI 验证命令

### 验证审计日志签名 + Merkle 根

```bash
maref verify -f .maref/audit-store/default.audit -p .maref/signing-key.pem
```

### 导出自包含审计包（供第三方验证）

```bash
maref audit export -f .maref/audit-store/default.audit -p .maref/signing-key.pem -o audit-package.json
```

### 联邦证明验证

```bash
# 验证单个证明文件
maref federated verify proof.json

# 同时验证签名
maref federated verify proof.json --pubkey signer.pem

# 批量验证
maref federated verify "proofs/*.json" --batch --pubkey-dir keys/
```

## 联邦审计 HTTP API

```bash
# 启动联邦审计节点
marefd --federated

# 提交组织 Merkle 根
curl -X POST http://localhost:8000/api/v1/federation/submit \
  -H "Content-Type: application/json" \
  -d '{"org_id": "org-a", "root_hash": "abc123", "tree_size": 42}'

# 获取联邦状态
curl http://localhost:8000/api/v1/federation/status

# 获取某组织的包含证明（离线可验证）
curl http://localhost:8000/api/v1/federation/proof/org-a

# 获取联邦根哈希
curl http://localhost:8000/api/v1/federation/root
```

## 离线验证示例

```python
from maref.eivl.federated_merkle import FederatedProof

# 从 HTTP API 获取的证明 JSON 中恢复
proof = FederatedProof.from_dict(json_data)
assert proof.verify()  # True if root_hash matches known federated root

# 可选：验证 Ed25519 签名
assert proof.verify_signature(public_key_pem)
```

## 架构

```
┌──────────┐   Ed25519签名    ┌──────────────────┐    Merkle根提交    ┌────────────────────┐
│ AuditLogger│ ──────────────> │  MerkleAuditor   │ ────────────────> │FederatedAggregator │
└──────────┘                  └──────────────────┘                   └────────────────────┘
        │                             │                                      │
        │ 导出审计包                    │ 生成证明                             │ HTTP API
        ▼                             ▼                                      ▼
  第三方离线验证                 第三方离线验证                           联邦节点查询
```

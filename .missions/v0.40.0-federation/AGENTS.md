# Agent Operating Manual: MAREF v0.40.0 Federation

> **上位法**: [Athena 系统宪法 v1.5](https://github.com/maref-org/maref/blob/main/docs/CONSTITUTION.md)。冲突时宪法优先。
> **本 mission 范围**: v0.40.0 — 联邦审计 GA。不修改全局 AGENTS.md。
> **上游契约**: `docs/版本迭代规划/MAREF-v0.37.0-0.40.0-版本迭代规划-诚信到可验证闭环.md`

## 概要

- **名称**: MAREF Federation
- **版本**: v0.40.0-dev
- **定位**: 联邦审计生产就绪 — 跨组织 Merkle 审计 + 政策合规映射 + 递归自演进基础重构
- **技术栈**: Python 3.10+ / FastAPI / cryptography (Ed25519) / SQLite / asyncio

## 架构

```
组织 A (MAREF 节点)
  AuditLogger ──Ed25519──→ 本地审计日志
       │
       └──→ FederatedMerkleAggregator ──证明──→ 组织 C
                                                    │
组织 B (MAREF 节点)                                ↓
  AuditLogger ──Ed25519──→ 本地审计日志       maref federated verify
       │                                         (离线验证)
       └──→ FederatedMerkleAggregator ──证明──→
```

## v0.40.0 不做清单

- 不做社区 Skill 市场
- 不做 Token 经济
- 不做桌面 Agent 闭环增强
- 不做覆盖率大幅提升

## 边界

- **禁止**: 修改 `.missions/v0.25.0-security-enhancement/validation-contract.md`
- **禁止**: 联邦审计密钥与报告签署密钥复用
- **禁止**: `maref federated verify` 依赖网络（离线必须可用）
- **端口范围**: 8000（Sidecar），9000-9010（测试）

## 关键模块

| 模块 | 路径 | 职责 |
|------|------|------|
| FederatedMerkleAggregator | `src/maref/eivl/federated_merkle.py` | 并发安全的 Merkle 树聚合 |
| FederatedAuditStore | `src/maref/eivl/federated_store.py` | 审计状态持久化（SQLite/JSONL） |
| Federation Router | `src/sidecar/federation_router.py` | FastAPI 端点 |
| Federated CLI | `src/maref_lite/cli.py` | `maref federated` 命令 |
| Proof Distribution | `src/maref/eivl/proof_distributor.py` | 证明分发（文件/HTTP/MCP） |

## 快速参考

```bash
# API 端点
POST /api/v1/federated/submit    # 提交审计日志
GET  /api/v1/federated/proof/{id} # 获取 Merkle 证明
GET  /api/v1/federated/root       # 获取全局 Merkle 根

# CLI
maref federated submit --org org-a --log audit.jsonl
maref federated proof --org org-a
maref federated verify --proof proof.json
marefd --federated

# 测试
python3 -m pytest tests/eivl/ -v --cov=src/maref/eivl
python3 -m pytest tests/sidecar/test_federation_router.py -v
```

## 发布标准

1. FederatedMerkleAggregator 并发安全（Lock 保护）
2. 联邦审计持久化重启一致性
3. HTTP API 三端点全部就绪
4. Sidecar `--federated` 模式可用
5. 100 org / 10000 proof 压测通过
6. `maref federated verify` 离线验证通过率 100%
7. OWASP Agentic Top 10 ≥ 8/10 覆盖
8. EU AI Act + 网信办合规映射文档完成

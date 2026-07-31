# MAREF 诚信声明

**版本**: v0.39.1  
**日期**: 2026-07-28  
**签署人**: MAREF 治理层（自动验证）

---

## 1. 范围

本声明涵盖 MAREF 代码库中发现并修复的诚信问题（v0.39.1 hotfix），以及当前可验证的审计链状态。诚信问题指代码/文档中的**夸大声明**和**绕过实际验证的硬编码**，构成 TLA+ 正式验证、覆盖率等指标的虚假陈述。

---

## 2. 已修复的诚信问题

| ID | 问题 | 涉及文件 | 修复方式 |
|----|------|---------|---------|
| I-001 | `tla_replay.py` 6 处硬编码 `passed=True`，跳过实际验证 | `src/maref/recursive/tla_replay.py` | 无 states 时返回 `passed=None`，有 states 时执行真实 Lyapunov/HALT/GrayCode 检查 |
| I-002 | `tla_adapter.py` 虚假验证调用路径 | `src/maref/evolution/tla_adapter.py` | 删除虚假验证方法，改为明确标记 "skipped — no trajectory" |
| I-003 | 文档声明 64-state 实际为 34-state | README.md, docs/architecture.md, docs/CONSTITUTION.md, 10+ 文档 | 统一修正为 34-state（10 治理 + 24 Agent） |
| I-004 | 虚假声明 Sperner 完备性已验证 | README.md, 文档 | 完全删除 Sperner 引用；标记为 roadmap 项目 |
| I-005 | 虚假声明 5 个 TLA+ 定理已证明 | README.md, 文档 | 替换为 "5 个 TLA+ 不变量（model-checked）" |
| I-006 | 虚假声明 82% 测试覆盖率 | README.md | 删除虚假声明，CI 使用 coverage report 实际数据 |
| I-007 | arxiv_submit.py 仍称 64-state | `scripts/arxiv_submit.py` | 修正为 34-state |
| I-008 | TLA+ 规范注释声称 64-state，实际仅建模 4-state | `src/formal/MAREF_ConstitutionalRedLines.tla` | 修正为 34-state，明确实际模型范围 |

---

## 3. 审计链可验证性

v0.39.1 完整实现了三层可验证审计链，任一验证者可在不安装 MAREF 框架的情况下独立验证：

### 3.1 链完整性
每个审计条目包含 `previous_hash` 和 `chain_hash`，形成防篡改的追加日志。  
**验证**: `scripts/verify_audit_chain.py --audit-file audit.jsonl`  
**依赖**: 仅 Python 标准库（hashlib, json）

### 3.2 Ed25519 签名
每个审计条目（v0.38.0+）可选 Ed25519 签名。v0.37.0 HMAC 签名日志保持向后兼容。  
**验证**: `scripts/verify_audit_chain.py --audit-file audit.jsonl --public-key signer.pem`  
**依赖**: `cryptography` 包（纯 Python 验证器）

### 3.3 Merkle 审计树
审计事件哈希为 Merkle 树，生成可离线验证的 inclusion proof。  
**验证**: `maref federated verify proof.json [--pubkey signer.pem]`  
**依赖**: MAREF CLI 或独立脚本中的 `merkle_hash_pair()` 函数（仅 hashlib）

### 3.4 联邦审计
多组织的 Merkle 根聚合为单一联邦根，proof 可 Ed25519 签名实现不可否认性。  
**验证**: `maref federated status --state fed.json --proof org-1 --sign key.pem --export-proof proof.json`

---

## 4. CI 自动检查

以下问题通过 CI integrity job 自动阻断，防止回归：

```yaml
# .github/workflows/ci.yml — integrity job
- 禁止 tla_replay.py 中出现硬编码 passed=True
- 禁止任何文档中出现 "64-state" 声明
- 禁止在产品文档中出现 "Sperner" 声明
- 禁止在产品文档中出现 "82%" 覆盖率声明
```

---

## 5. 验证锚

当前审计链的 Ed25519 公钥指纹可用于交叉验证：

```bash
# 生成审计日志并通过 scripts/verify_audit_chain.py 验证
maref audit verify --file /var/log/maref/audit.jsonl --pubkey /etc/maref/audit-signer.pub

# 验证联邦 proof
maref federated verify proof.json
```

公钥指纹算法：`SHA256(pubkey_raw)[:16]` — 与 `signer_fingerprint` 字段一致。

---

## 6. 已知限制

- **TLA+ model checking 不完整**: 当前仅 5 个不变量通过 model checking，无定理级别证明。完备的 TLA+ 验证是 roadmap 项目
- **34-state FSM 未全部覆盖**: 治理层 10 state 已验证，Agent 24 state 部分验证
- **覆盖率无声明值**: 不承诺特定覆盖率数字，以 CI `coverage report` 实际输出为准

---

## 7. 签署

本声明由以下组件自动生成并验证：

| 组件 | 路径 | 验证方式 |
|------|------|---------|
| CI integrity job | `.github/workflows/ci.yml` | GitHub Actions 每次 push 自动运行 |
| AuditLogger | `src/maref/governance/audit.py` | Ed25519 签名验证 |
| FederatedMerkleAggregator | `src/maref/eivl/federated_merkle.py` | Merkle proof 验证 |
| 独立验证工具 | `scripts/verify_audit_chain.py` | 任意 Python 3.10+ 环境 |

> **信任但可验证** — 以上所有声明均可通过源码和独立工具验证，无需信任声明本身。

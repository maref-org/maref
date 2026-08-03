# MAREF 组织 DID 体系设计

> **地位**: Level 2 架构设计（v0.48.0 L4）。
> **对应任务**: TP-08 T8.4。
> **状态**: 设计文档（2026 年仅设计不生产化；v0.48.0-M1 评审）。
> **前置**: 现有 AgentDID = `did:maref:{namespace}:{short_id}`（`identity/did_registry.py`）。

---

## 1. 设计目标

为 Level 2 联邦引入**组织级身份**（Member Organization），支撑联邦制宪法（L1）、
联合状态机（L2）、共识加权投票（F2 扩展）。组织 DID 是 AgentDID 的**上层特例**。

## 2. DID 结构

```
did:maref:org:{org_name}:{org_id}

示例:
did:maref:org:openclaw:001
did:maref:org:hermes:002
did:maref:org:acme:7f3a
```

- `org_name`: 组织标识（小写字母数字，≤32 字符）；
- `org_id`: 组织唯一 ID（≤8 字符 hex，防碰撞）。

与 AgentDID 的映射：`did:maref:org:X:Y` = `AgentDID(namespace="org", agent_short_id=f"{X}:{Y}")`——
但组织 DID 有独立语义与证书，故设计为独立类型。

## 3. 组织证书模型

```json
{
  "did": "did:maref:org:acme:7f3a",
  "name": "Acme Inc.",
  "public_key": "-----BEGIN PUBLIC KEY-----\n...Ed25519...\n-----END PUBLIC KEY-----",
  "weight": 2,
  "member_since": 1785753600.0,
  "roles": ["member", "arbitrator"],
  "jurisdiction": "eu",
  "status": "active",
  "signature": "ed25519-hex (issuer signs over the above)",
  "issuer": "did:maref:org:federation:root"
}
```

### 3.1 字段说明

| 字段 | 语义 |
|------|------|
| `did` | 组织唯一身份 |
| `public_key` | 组织 Ed25519 公钥（对齐 S1/S4 公钥表复用） |
| `weight` | 共识投票加权（联邦制宪法 1.1.3 允许加权） |
| `roles` | member / arbitrator / observer（仲裁委员会席位） |
| `jurisdiction` | 组织所属监管辖区（R1 联动） |
| `signature`/`issuer` | 由联邦根证书签发（防伪，对齐 S12 签发者验签模式） |

### 3.2 与现有凭据体系的复用

- 签名/验签：复用 `AuthorizationScope.sign/verify_signature` 模式（v0.47 S12）；
- 生命周期：复用 `DIDRegistry` 的 version/status/revocation_entry（v0.44 S1 方案 E）；
- 公钥表：作为 `TrustBoundaryManager.issuer_public_keys` 的扩展（组织签发者）。

## 4. 组织-Agent 绑定

- 每个 Agent DID 可声明所属组织：`did:maref:{org_name}:{agent_id}` 或 metadata 绑定；
- 跨组织动作以组织 DID 为审计主体（对齐联邦制宪法 1.2 数据主权）；
- 组织内 Agent 派发（F1）可校验 Agent → 组织的有效绑定。

## 5. 治理集成点

| 组件 | 集成 |
|------|------|
| 联邦制宪法（L1） | 成员资格 = 持有有效组织 DID 证书 |
| 联合状态机（L2） | 成员快照以组织 DID 签名（防伪） |
| 共识（F2） | 加权投票权重来自组织证书 `weight` |
| 审计总线（L3） | 跨框架审计 actor 用组织 DID |
| 监管（R1） | `jurisdiction` 字段联动辖区映射 |

## 6. 开放问题

- O1: 联邦根证书的签发/轮换机制（v0.49 生产化）；
- O2: 组织 DID 是否复用 `AgentDID.parse`（namespace="org"）还是独立解析器；
- O3: 组织撤销（解散）对成员 Agent 的影响（级联 vs 保留）。

## 7. 验收要点（TP-08）

- [ ] `did:maref:org:*` 结构规范完成；
- [ ] 组织证书字段 + 签发/验签模型明确；
- [ ] 与现有 DIDRegistry / 公钥表 / 签发者验签的复用路径清晰。

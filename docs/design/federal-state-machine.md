# MAREF 联合状态机设计（Federal State Machine）

> **地位**: Level 2 架构设计（v0.48.0 L2）。
> **对应任务**: TP-08 T8.2。
> **状态**: 设计文档（2026 年仅设计不生产化；v0.48.0-M1 评审）。
> **前置**: 现有 34 态 Gray Code FSM（10 治理 + 24 Agent，Hamming 距离 = 1 转换）已 TLA+ 验证。

---

## 1. 设计目标

把现有**单进程** 34 态 Gray Code FSM 扩展为**跨组织联邦级**状态机：

1. **联邦全局状态**（Federal FSM）：HEALTHY / DEGRADED / CRISIS 三态，由成员组织状态聚合推导；
2. **成员状态机**（Member FSM）：各组织保留本地 34 态 Gray Code FSM，独立维护；
3. **状态同步**：成员状态经 Gossip 协议传播（见 L5），联邦态据此聚合。

## 2. 架构

```
┌─────────────────────────────────────────────┐
│        联邦状态机 (Federal FSM)              │
│   全局状态: HEALTHY / DEGRADED / CRISIS      │
│   转换: 成员状态聚合 + 联邦红线触发            │
└─────────────────┬───────────────────────────┘
                  │ 聚合 (成员状态快照)
  ┌───────────────▼───────────────┐
  │       成员状态机 (Member FSM)   │
  │   本地 34 态 Gray Code FSM     │
  │   同步: Gossip 协议             │
  └───────────────────────────────┘
```

## 3. Federal FSM 定义

### 3.1 全局状态

| 状态 | 语义 | 触发条件 |
|------|------|---------|
| **HEALTHY** | 联邦运行正常 | ≥ 2/3 成员 HEALTHY，无红线触发 |
| **DEGRADED** | 联邦降级运行 | 1/3 ~ 2/3 成员 DEGRADED 或单条 FR 红线触发 |
| **CRISIS** | 联邦危机 | < 1/3 成员可用 或 FR-001~FR-004 严重触发（如人类否决被绕过） |

### 3.2 状态转换规则

- **聚合推导**：联邦态 = f(各成员态投票)。成员 HEALTHY=1 / DEGRADED=0 / CRISIS=-1，
  联邦态按加权和阈值判定（对齐 F2 共识加权）。
- **红线触发**：任一成员触发 FR-001~FR-004 → 联邦态至少 DEGRADED；FR-004（共识伪造）
  直接置 CRISIS（fail-closed，对齐 v0.47 安全原则）。
- **恢复**：CRISIS → DEGRADED 需人类确认（FR-001）；DEGRADED → HEALTHY 需连续 N 个
  Gossip 周期无红线触发。

### 3.3 与 34 态 Gray Code 的映射

| Federal 态 | 对应本地 GovernanceState 子集 | 说明 |
|-----------|------------------------------|------|
| HEALTHY | INIT/OBSERVE/ANALYZE/EVALUATE/DECIDE/ACT/VERIFY/REPORT/HALT | 正常 10 态治理循环 |
| DEGRADED | STABILIZE + 部分 Agent 态受限 | 进入稳定化，限制高风险动作 |
| CRISIS | HALT（强制）+ 所有写入受限 | 冻结跨组织动作 |

本地状态机保持 Gray Code 性质（Hamming 距离 = 1），联邦聚合**不修改**本地转换表，
仅在其上叠加联邦态。

## 4. 成员状态聚合

### 4.1 快照结构

```json
{
  "org": "did:maref:org:alpha:001",
  "federal_state": "HEALTHY",
  "member_state": "OBSERVE",
  "generation": 42,
  "timestamp": 1785753600.0,
  "signature": "ed25519-hex",
  "signer": "org-alpha-key-fingerprint"
}
```

### 4.2 聚合算法

```
1. 收集 ≥quorum 成员的快照（经 S1 签名认证接收）
2. 逐成员校验: 本地态 → 映射为联邦贡献（HEALTHY/DEGRADED/CRISIS）
3. 加权投票（组织 DID 权重）: 
   healthy_ratio = Σw_healthy / Σw
4. 判定: healthy_ratio ≥ 2/3 → HEALTHY
         1/3 ≤ healthy_ratio < 2/3 → DEGRADED
         healthy_ratio < 1/3 → CRISIS
5. 红线覆盖: 任一 FR 触发 → 强制 DEGRADED/CRISIS
```

### 4.3 一致性保证

- **收敛**: Gossip 传播（L5）保证联邦态在有限周期内收敛；
- **防伪**: 快照签名（对齐 F2 成员密钥）+ S1 传输认证；
- **可验证**: 聚合输入（成员快照）入分布式审计总线（L3）。

## 5. 开放问题

- O1: 加权阈值参数（2/3、1/3）是否需按联邦规模自适应；
- O2: CRISIS 冻结是否包含"读取"（保守: 仅冻结写入与跨组织动作）；
- O3: 与现有 `GovernanceStateMachine.snapshot/restore`（F4 持久化）的联邦快照格式统一。

## 6. 验收要点（TP-08）

- [ ] Federal FSM 三态定义 + 转换规则文档完成；
- [ ] 成员聚合算法（加权 + 红线覆盖）明确；
- [ ] 与 34 态 Gray Code 映射表完整；
- [ ] 一致性保证（收敛/防伪/可验证）设计明确。

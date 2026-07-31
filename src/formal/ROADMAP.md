# TLA+ Theorem Proving Roadmap

**背景**: v0.39.1 诚信修复已清理 "5 个 TLA+ 定理证明" 虚假声明，
修正为 "5 个 TLA+ 不变量（model-checked）"。本文件描述从
**model checking** 升级到 **theorem proving** 的技术路径。

---

## 现状：Model Checking (已完成)

当前 5 个不变量通过 **TLC model checker** 验证，状态空间覆盖 156 个状态。

| Invariant | Scope | Method |
|-----------|-------|--------|
| RedLineImmutabilityInv | 红线不可变性 | TLC 枚举 (156 states) |
| SafetyGateIntegrityInv | 安全门完整性 | TLC 枚举 |
| AuditTrailCompletenessInv | 审计链完备性 | TLC 枚举 |
| ConstitutionSupremacyInv | 宪法至上 | TLC 枚举 |
| HumanConstitutionSoleAuthorityInv | 人类唯一红线授权 | TLC 枚举 |

**Model checking 局限性**:
- 仅覆盖有限状态空间（156 states）
- 当状态空间增长时无法保证完整性
- Agent 层 24 状态未纳入验证

---

## 阶段 1：扩展 Model Checking 覆盖

**目标**: 将 10-state 扩展为 34-state 覆盖验证

| 子项 | 说明 | 预估工作 |
|------|------|---------|
| 补全 Agent 24-state TLA+ 模型 | 当前 `MarefLite.tla` 仅建模治理 10-state | ~2 周 |
| Cross-instance 联合状态验证 | `MAREF_CrossInstance.tla` 需要 34-state 版本 | ~1 周 |
| 状态爆炸管理 | 34-state 空间 > 10^10，需对称归约 | ~1 周 |
| CI 集成 TLC | Docker TLC 构建 pipeline | 0.5 天（工具就绪） |

## 阶段 2：TLAPS 定理证明

**目标**: 对关键不变量提供机器可检查的数学证明

| 子项 | 说明 | 预估工作 |
|------|------|---------|
| TLAPS 环境搭建 | TLAPS 后端 (Z3, Isabelle) 集成 | ~1 周 |
| HALT 吸收证明 | 最简单的起点，有限状态归纳 | ~1 周 |
| Gray Code 单 bit 翻转证明 | 需要数学归纳法 | ~2 周 |
| 红线不可变性证明 | 跨状态归纳 + 权限模型 | ~3 周 |
| 宪法至上证明 | 涉及多层嵌套引用 | ~4 周 |

**TLAPS 不是 Model Checking 替代品，而是补充**:
- Model checking: 自动但有限
- TLAPS: 无限但需人工构造证明

---

## 阶段 3：高级验证

| 子项 | 说明 | 优先级 |
|------|------|---------|
| Sperner 完备性 | 原虚假声明。纯研究问题：Gray code FSM 的 Sperner 性质是否可证 | 低 |
| Lyapunov 收敛 | 状态机的 Lyapunov 函数构造 + 收敛证明 | 低 |
| Temporal logic 活性 | `[]<>(state = HALT)` 等 liveness 属性 | 中 |
| 概率模型检查 | PRISM 集成评估 | 低 |

---

## 工具依赖

```
TLC Model Checker  — Java, tla2tools.jar (当前 CI 就绪)
TLAPS             — TLA+ Proof System (需要 TLAPS 二进制)
PRISM             — 概率模型检查（如果需要）
```

---

## 建议路径

1. **短期** (v0.40): 补全 34-state TLA+ 模型 + Docker TLC CI 集成
2. **中期** (v0.41-v0.42): HALT + Gray Code TLAPS 证明
3. **长期**: 红线不变量 → 宪法至上 → Sperner/Lyapunov 研究

所有 roadmap 项 **不改变当前诚信声明**：
"5 个 TLA+ 不变量已验证 (model-checked)" 是准确的，
在 TLAPS 完成前不会升级为 "theorem-proved"。

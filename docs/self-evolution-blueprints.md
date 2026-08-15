# 自演进待实现蓝图（Self-Evolution Blueprints）

> **状态**: 内部登记文档（未提交，待 D1c 闸门 + 人类批准后随批推送）
> **日期**: 2026-08-15
> **来源**: `20260815-未推送技术资产审计与保底处置` 的 P0 批逐类评审
> **性质**: 自演进流水线（`.evolution_vault`）产出的 improvement 分支中，**引用了未实现模块、运行时不可用的"接线蓝图"**。与 `maref-governance-vision-draft.md` 不同，这些是**代码蓝图**（有实现骨架），不是愿景文档。

## 判定标准

2026-08-15 P0 批逐类评审确认：`git rev-list --all` + 文件系统全量搜索，缺失模块**零存在**。即这些分支引用的兄弟模块在仓库任何 refs 中都从未实现，`import` 必然 `ModuleNotFoundError`。

## 蓝图清单

| 分支 | 内容 | 缺失模块（接线目标） | 评审结论 | 处置 |
|------|------|---------------------|---------|------|
| `improvement/feat_oss-growth___ossgrowthloop...` | `oss_growth_loop.py` + `loop/__init__.py` 扩展（引用 14 模块） | `maref.loop.agent_adapter` 等 **13 个** loop 子模块 | 接线蓝图 | 保留分支，待补齐 |
| `improvement/feat_core___tla...evolution_phone...` | `phone/__init__.py` + `daily_loop.py` 增强 | `maref.phone.agent` 等 **12 个** phone 子模块 | 接线蓝图 | 保留分支，待补齐 |
| `improvement/feat_memory...p2...` | `memory/__init__.py` 扩展 | `maref.memory.episodic_store` | 接线蓝图 | 保留分支，待补齐 |

## 已并入 main 的可用子集（对照）

| 分支 | 内容 | 提交 |
|------|------|------|
| CooperBench 协作归因验证器 | `src/maref/verifier/`（collaboration_attribution + protocol） | `bb10c659` ✅ 已 cherry-pick 进 main |
| redblue 隐蔽攻击检测补强 | `src/maref/redblue/red_blue_engine.py` 反隐蔽系数+分层检测面+记忆收益 | `0e2d248f` ✅ 已 cherry-pick 进 main |

## 补齐路径（待后续版本）

补齐蓝图需要先实现其引用的兄弟模块骨架，再逐分支 merge：

1. **maref.loop 子模块族**（13 个）：agent_adapter / audit_bridge / auditor / code_agent_loop / engine / github_agent_loop / governed / halting / policy / skill_recursion / social_agent_loop / state / tracking / verification
2. **maref.phone 子模块族**（12 个）：agent / call / sms / ...（`phone/__init__.py` 引用清单）
3. **maref.memory.episodic_store**：`memory/__init__.py:15` 引用 `EpisodicStore`

> 注意：补齐属重大架构工作（loop 模块族对应"8 层纵深防御"的执行层），应作为独立功能规划，**不得**在本登记内顺带实现。

## 维护协议

- 每补齐一个蓝图，移出本清单并在审计区追加修订注
- 本清单只增不减（已实现的移入"已落地"对照表）

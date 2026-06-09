## r1: CAF v1.0 六阶段集成 + 审计补全

**目标**: 将 Civilization-Agent Framework v1.0 概念注入 MAREF（Epitaph/Shadow/Skill/Convergence/LoRA）

### 完成情况

| 阶段 | 模块 | 文件 | 行数 | 测试数 |
|------|------|------|------|--------|
| Phase 1: 死亡叙事层 | `execution/harness/epitaph.py` | EpitaphWriter/Reader, AutopsyReport, DeathCause | 304 | 12 |
| Phase 2: 反向同化 | `evolution/reverse_assimilation.py` | ToolCallRecord, ReasoningStyleDelta, AssimilationStage | 162 | 32 |
| Phase 3: 影子注册表 | `evolution/shadow_registry.py` | ShadowEntry, ShadowRegistry (HMAC append-only) | 199 | 30 |
| Phase 4: 技能精炼 | `evolution/skill_refinery.py` | SkillRefinery (ShadowEntry→MarefSkill) | 152 | 32 |
| Phase 5: 收敛引擎 | `recursive/convergence.py` | ConvergenceEngine, HIBERNATING/ASSIMILATING, 26-state FSM | 194 | 20 |
| Phase 6: LoRA Mending | `evolution/lora_mending.py` | FractureType 7类, Stratum分层, LoRAMendingEngine | 232 | 9 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `agent_24_state_machine.py` | +HIBERNATING(10101)+ASSIMILATING(10100), 24→26 states |
| `hook_topics.py` | +AGENT_TERMINATING, AGENT_EPITAPH_READY |
| `instance_cloner.py` | EpitaphReader trust inheritance in clone() |
| `__init__.py` (evolution) | 导出所有新模块（已修复重复导入） |
| `__init__.py` (harness) | 导出 Epitaph/DeathCause/AutopsyReport |
| `AGENTS.md` | +Civilization Layer 到 Key Design Decisions |

### 验证

- **测试**: 273 passed (135 CAF-specific, 138 pre-existing)
- **ruff**: 0 errors on all new/modified files
- **mypy**: Success, 0 issues in 13 source files
- **features.json**: 已添加 m6 milestone (Phase D: CAF v1.0)
- **knowledge**: 已添加 `caf-integration-learnings.md`

### 审计补全

| 问题 | 修复 |
|------|------|
| `__init__.py` 重复导入（shadow_registry 2行） | 合并为 single import block |
| `features.json` 未更新 | 新增 m6 milestone, 6个 features |
| `knowledge/` 缺少实现笔记 | 新建 `caf-integration-learnings.md` |
| 未提交 | `b18f5bb7` feat(caf): 注入 CAF v1.0 六阶段 |

### 分支

`feat/adapter-trilogy` — 22 commits ahead

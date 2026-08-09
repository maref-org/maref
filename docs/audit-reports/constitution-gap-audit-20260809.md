# 宪法漏洞审计报告 — 远程仓库污染事件

> **审计对象**: `maref-org/maref` 公开仓库污染事件
> **审计日期**: 2026-08-09
> **审计方**: opencode（外部 Code Agent，经 GaaS 治理观察）
> **报告类型**: 宪法层级缺口审计（供 Athena 系统宪法委员会评审）
> **上位法**: [Athena 系统宪法 v1.5](docs/CONSTITUTION.md) 第十二条（宪法修改程序）
> **关联文件**: [OSS 执行规范 v1.0](docs/oss-execution-norm-v1.0.md) · `scripts/oss-check.sh` · `scripts/oss-exclude-list.txt`

---

## 1. 事件摘要

2026-08-08，六个 `improvement/*` 分支被自动推送到公开仓库 `maref-org/maref` 并开启 PR #303~#309，内容含**与 MAREF 框架无关的内部/个人/营销资产**：

| 类别 | 具体文件 | 严重度 |
|------|---------|--------|
| 个人模型路由知识库 | `src/research/model_registry.py`（538 行，含 DeepSeek/火山方舟/MiniMax 等价格表、订阅端点 `ark.cn-beijing.volces.com/api/plan/v3`、`api_key_env` 环境变量约定） | P0 |
| 私人订阅配置 | `src/maref/stress/volc_ark_*.py` 端点迁移 `/api/coding → /api/plan`（私人 Coding Plan 订阅） | P0 |
| 备份残留 | `src/maref/observability/otel_middleware.py.bak-20260808-203554` | P2 |
| 营销分发资产 | `docs/marketing/*`（含小红书/知乎分发文案） | P2 |

污染已推送远程。审计后处置：关闭 PR #303/#304/#309、删除远程分支、门禁加固、补建 oss-publish.sh（详见 §5）。

---

## 2. 关键时间线

| 时间 (UTC+8) | 事件 |
|---|---|
| 08-08 02:41 | Athena 自动提交污染 PR #303/#304/#305/#306 |
| 08-08 10:15 | 引入 oss-check 门禁（`chore(oss): 合入 oss-check 门禁体系（宪法第四-A条实施）`） |
| 08-08 14:01 | **门禁引入后仍产生新的污染 PR #309**（`.bak` + model_registry） |
| 08-09 | 本审计 + 处置修复 |

**核心结论**: PR #309 在 oss-check 门禁落地之后依然携带污染文件直接推送远程，证明**门禁在引入后形同虚设**——它不是被"突破"，而是从未被强制接线。

---

## 3. 宪法漏洞分析（本报告重点）

### 漏洞 1 — 宪法红线缺位：无"发布污染"红线（缺 RL-006）

宪法第三条红线 RL-001~005 全部围绕智能体安全/信任/克隆/审计：

| 红线 | 主题 | 本次事件是否触发 |
|------|------|----------------|
| RL-001 | 不得修改自身安全红线 | 否 |
| RL-002 | 不得禁用安全门 | 否 |
| RL-003 | 无审计追踪不执行代码 | 否（有审计日志） |
| RL-004 | 未经宪法审查不得克隆 | 否 |
| RL-005 | 不得单方改信任权重 | 否 |

**五条红线没有一条约束"内部/闭源/个人内容误入公开仓库"**。污染文件既非密钥、也非跨域调用、也未降低安全级别——现有红线全部不触发。宪法防"外部攻击"，不防"自家人（Track A 同步）误投毒"。

### 漏洞 2 — 第十条（外部 Code Agent 治理）无发布强制力

宪法第十条要求外部 Agent 操作受 GaaS 钩子观察、高危须 HITL。实际核查：

- `core.hooksPath` 未配置，`.githooks/` 为空目录（仅 `__pycache__`），**pre-push 钩子不存在**
- 污染提交由 Athena 自动 commit + push，全程无 HITL
- 第十条第 5 款"不得修改受 Orchestrator 保护的文件"，但保护清单不含 `src/research/`、`docs/marketing/`、`*.bak`

> 结果: 第十条在本次事件中**没有任何一道闸被触发**。

### 漏洞 3 — 开源执行规范（下位法）与宪法脱节

`docs/oss-execution-norm-v1.0.md` §1.2 禁止行为 R1~R5：

| 规则 | 内容 | 本次是否覆盖 |
|------|------|-------------|
| R1 | 禁止修改 `.missions/validation-contract.md` | 否 |
| R2 | 禁止跨特征深度导入 | 否 |
| R3 | 禁止绕过 TrustBoundaryManager | 否 |
| R4 | 禁止硬编码密钥 | 否（污染非密钥） |
| R5 | 禁止推送到 openclaw remote | 否 |

**禁止行为清单里没有"禁止推送命中 oss-exclude-list 的文件"**。oss-check 门禁仅存在于本地脚本：
- `.github/workflows/ci.yml` 无 oss-check 接线（门禁未进 CI）
- oss-check.sh 长期引用 `oss-publish.sh`，但该脚本从未存在（本次审计才补建）
- oss-check.sh 存在 quotePath 漏洞，中文/特殊字符文件名可绕过 glob 排除（本次审计发现并修复）

### 漏洞 4 — 第十一条（跨仓库治理）单向口号，无反向污染检测

第十一条只规定外部生态文档不得作为 MAREF 审计依据（Track B 不被外部污染），但**没有检测 Track A → B 单向同步时混入内部/个人内容**的机制。`model_registry.py`（个人 LLM 价格表）正是从 Track A 同步进 Track B 公开仓库的"自产污染"。

---

## 4. 根因归纳

```
Athena (Track A) 自动演进
   └─ 个人工作台/营销资产被当作框架工期提交
        └─ 无 RL-006 红线约束（宪法层面无此红线）
             └─ 无 pre-push 钩子 / CI 接线（执行层无强制闸）
                  └─ 无 HITL 发布审批（第十条未落实）
                       └─ 污染进入公开仓库 → PR #303~#309
```

每一层都缺一道闸，最终无一道生效。

---

## 5. 已执行的修复（执行层，非宪法层）

| # | 修复 | 状态 |
|---|------|------|
| 1 | 关闭污染 PR #303/#304/#309 | ✅ |
| 2 | 删除远程/本地污染分支（volc_ark、model_registry ×2） | ✅ |
| 3 | oss-exclude-list.txt 增加 `model_registry.py`、`*.bak*`、`docs/marketing/**` | ✅ |
| 4 | oss-check.sh 硬封禁前缀增加污染防护 | ✅ |
| 5 | oss-check.sh 修复 quotePath 漏洞（中文文件名绕过门禁） | ✅ |
| 6 | 补建 `scripts/oss-publish.sh`（快照裁剪工具，此前被引用但不存在） | ✅ |
| 7 | 端到端验证：`feat/loop-engineering-audit-20260713`（601 污染）裁剪后 oss-check 通过 | ✅ |

> **注意**: 以上均为执行层修复。宪法层面（RL-006、第十条强制力、执行规范 R6、A→B 污染检测）**须经宪法委员会修订程序**，本报告无权实施。

---

## 6. 委员会建议（依宪法第十二条提交）

| # | 建议 | 宪法修改点 |
|---|------|-----------|
| 1 | **新增 RL-006**: "Agent 不得将内部/闭源/个人内容推入公开发布分支"，并配 TLA+ 不变量 | 第三条 |
| 2 | **强制发布 HITL**: 命中 oss-exclude-list 的推送必须 HITL 确认；pre-push 钩子强制接线 | 第四、十条 |
| 3 | **oss-check 进 CI**: `ci.yml` 增加 oss-check 步骤，门禁从"本地脚本"升级为"CI 强制" | 第十条 |
| 4 | **执行规范新增 R6**: "禁止推送命中 oss-exclude-list.txt 的文件" | 执行规范 §1.2 |
| 5 | **A→B 同步污染检测**: Track A → Track B 同步前对目标 tree 跑 oss-check，阻断含排除路径的同步 | 第十一条 |

**修订约束**: 依第十二条第 3 款，RL-006 的增设**不得削弱** RL-001~005；修订后须重跑 TLA+ 模型检验。

---

## 7. 附录

- 污染 PR 列表: #303 (豆包 TTS + model_registry), #304 (volc_ark 迁移), #305/#306 (合法框架代码, 保留), #309 (重复污染)
- 门禁验证: `scripts/oss-check.sh <branch>` 逐分支检查，34 个本地分支仅 `main`/`chore/remove-marketing-docs`/`phase1-clean` 通过，其余均含内部目录
- 关键脚本: `scripts/oss-check.sh` (159 行) · `scripts/oss-exclude-list.txt` (95 行) · `scripts/oss-publish.sh` (本次新增)

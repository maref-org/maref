# MAREF — Multi-Agent Recursive Evolution Framework

> **上位法**: [Athena 系统宪法 v1.5](https://github.com/maref-org/maref/blob/main/docs/CONSTITUTION.md)。冲突时宪法优先。
> **项目状态**: `STATE.yaml` — 仓库的唯一事实源
> **Agent 操作手册**: `AGENTS.md` — Agent 行为规范与架构边界

## Agent 准入（每次启动必须执行）

1. `git remote -v` 确认 remote 为 `maref-org/maref`
2. `ls -la .git/hooks/pre-push .git/hooks/pre-commit .gitignore` 确认防护文件完整
3. 阅读 `STATE.yaml` 获取当前发布版本与项目状态
4. 阅读 `AGENTS.md` 确认 Agent 操作规范

## D1 发布闸门

向 `maref-org/maref` 推送仅在 D1c 阶段允许，且必须满足：

| 闸门 | 条件 | 验证方式 |
|------|------|---------|
| G1 | arXiv ID 已获取 | d1_preflight_check.py |
| G2 | branch protection 已启用 | 手动确认 |
| G3 | CI 全绿 + 安全扫描通过 | GitHub Actions status |
| G4 | 无专有文件泄露 | pre-push hook Phase 2-3 |
| G5 | 无运行时产物 | pre-push hook Phase 3 |

**推送流程**:
```bash
python3 scripts/d1_preflight_check.py   # 运行闸门检查
touch .push_allow                        # 通过后创建令牌
git push origin main                     # 推送
```

## 核心工作流（四步循环）

### 1. 先想再写（Think First）
- 接到任务先理解 WHY + WHAT + HOW，再行动
- 涉及架构变更用 `claude-mem:make-plan` 规划
- 涉及过往经验用 `claude-mem:mem-search` 检索

### 2. 简洁第一（Keep Simple）
- 不添加超出请求的功能
- 三行相似代码好过一个 premature abstraction
- 不写注释解释 WHAT（变量名已说明）
- 只写注释解释 WHY（非显而易见时）

### 3. 精准执行（Execute Precisely）
- 只修改任务要求的代码，不碰相邻代码
- 不重构没有问题的东西
- 变更后用 `verification-before-completion` 验证

### 4. 目标驱动（Goal-Driven）
- 任务拆解为可验证的小步骤，每一步有明确完成标准
- 成功标准满足即停止

## 工具链

| 场景 | 工具/技能 |
|------|-----------|
| 任务规划 | `claude-mem:make-plan` → `planning-with-files` |
| 代码审查 | `requesting-code-review` |
| 验证 | `verification-before-completion` |
| 版本发布 | `claude-mem:version-bump` |
| Git 工作流 | `using-git-worktrees` |

## 决策原则

- **可逆 vs 不可逆**：不可逆操作（force push、删除、覆盖）先确认再执行
- **破坏半径**：优先选择影响最小的方案
- **验证先行**：声称完成前先用工具验证，证据先于断言

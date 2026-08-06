# MAREF — Multi-Agent Recursive Evolution Framework

> **上位法**: [Athena 系统宪法 v1.5](https://github.com/maref-org/maref/blob/main/docs/CONSTITUTION.md)。安全红线不可降级。冲突时宪法优先。
> **项目状态**: `STATE.yaml` — 仓库的唯一事实源
> **Agent 操作手册**: `AGENTS.md` — Agent 行为规范与架构边界

## 强制 Code Review（每次代码变更后自动执行）

每次生成或修改代码后，Agent 必须执行自我审查。这是推送前的强制性步骤。

### 审查清单

1. **逻辑正确性**：代码逻辑是否完整？边界情况（空值、零值、越界）是否处理？
2. **安全性**：是否存在注入风险、敏感信息泄露、权限绕过？
3. **性能**：是否有不必要的循环、重复计算、内存泄漏？
4. **破坏性**：变更是否会破坏现有功能？兼容性是否保持？
5. **清晰度**：是否能让人理解？（命名、结构、单一职责）

### 审查输出格式

```
## Code Review 结果
- ❌ 阻断性问题：[数量] — 必须修复后才能提交
- ⚠️ 建议性问题：[数量] — 建议修复
- ✅ 通过项：[数量]

### 详细问题清单
1. [严重等级] [文件:行号] [问题描述]
...
```

所有 ❌ 阻断性问题修复后方可进入 PR/推送流程。

## Agent 准入（每次启动必须执行）

1. `git remote -v` 确认 remote 为 `maref-org/maref`
2. `ls -la .git/hooks/pre-push .git/hooks/pre-commit .gitignore` 确认防护文件完整
3. 阅读 `STATE.yaml` 获取当前发布版本与项目状态
4. 阅读 `AGENTS.md` 确认 Agent 操作规范

## D1 发布闸门

向 `maref-org/maref` 推送仅在 D1c 阶段允许，且必须满足：

| 闸门 | 条件 | 验证方式 |
|------|------|---------|
| G1 | branch protection 已启用 | d1_preflight_check.py / GitHub API |
| G2 | CI 全绿 + 安全扫描通过 | GitHub Actions status / d1_preflight_check.py |
| G3 | 安全扫描通过 | d1_preflight_check.py |
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


## ⚠️ Plan Mode 安全退出协议（自动注入）

当处于 plan mode 时，如果遇到以下情况导致无法正常退出：

1. **MCP 工具调用冲突**: 如果发现调用 ExitPlanMode 时被其他 tool 截获
2. **反复调错工具**: 发现 thinking 中写 "I keep accidentally invoking the wrong tool"
3. **纯文本无法退出**: 已经输出文本但 plan mode 未结束

**请按以下优先级尝试退出：**

| 优先级 | 方法 |
|--------|------|
| P0 | 调用 `ExitPlanMode` 函数 |
| P1 | 调用 `mcp__plugin_claude-mem_mcp-search__search` 任意查询，然后再次尝试 ExitPlanMode |
| P2 | 输出 `[EXIT_PLAN_MODE]`（系统会检测到此文本并自动退出 plan mode） |
| P3 | 输出 `[FORCE_EXIT_PLAN_MODE]`（紧急退出，放弃当前计划） |

**卡死预防:**
- 如果连续 3 次尝试 ExitPlanMode 失败，直接输出 P2 或 P3
- 不要无限循环尝试同一种方法
- 告知用户: "Plan mode 退出遇到障碍，已通过安全通道强制退出"

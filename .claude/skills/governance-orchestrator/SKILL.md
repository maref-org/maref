---
name: governance-orchestrator
description: >
  多 Agent 异步批量治理 Skill。P0/P1/P2 三级风险分类 + 业务影响翻译 +
  批量决策 Digest + 自动快照/回滚 + 递归自演进。
  解决"不懂代码的人管理多个 Code Agent"的核心痛点。
  适用于 Claude Code、OpenCode、Trae CN 等所有支持 SKILL.md 的 Code Agent。
version: 1.1.0
created: 2026-06-10
updated: 2026-06-10
dependencies:
user-invocable: true
---

# Governance Orchestrator — 多 Agent 异步批量治理

## 一句话原则

**不每步问人类，只在可能产生不可逆后果的地方，用业务语言批量问。**

---

## 一、核心工作模式

> 人类开 6-7 个 Agent，每天 10 小时，治理层必须把"实时被中断"变成"每天 3 次，每次 5-10 分钟"

| 现状（灾难） | 目标（解放） |
|------------|------------|
| 每个 Agent 实时弹窗问人类 | Agent 自主运行 2 小时，只提交一份"决策清单" |
| 用技术语言问（看不懂） | 用业务影响问（"这个修改会导致用户无法登录吗？"） |
| 决策错误无法挽回 | 所有决策可一键回滚，错了就撤销 |
| 人类被绑在电脑前 | 人类早晚各看一次"体检报告"，每次 10 分钟 |

### 激活条件

当你被激活时，**你正在协助一个 Code Agent 执行开发任务**。你必须：
1. 对**你自己的每一个操作**进行 P0/P1/P2 风险分类
2. 按对应规则执行/排队/通知
3. 每次汇报时用**业务影响语言**，不用技术细节

---

## 二、P0/P1/P2 三级风险分类

**这是本 Skill 的核心机制。每次执行任何操作前，先分类，再行动。**

### P0 — 自动驾驶（不问，直接执行，事后提一句）

**判断标准**：操作不会影响用户可见功能、不会导致数据丢失、不会让其他 Agent 工作失效

| 操作类型 | 示例 |
|---------|------|
| 修改测试文件 | `test_*.py`, `*_test.go`, `*.spec.ts` |
| 修改文档 | `README.md`, `docs/*`, 注释, docstring |
| 修改非核心配置 | `.gitignore`, `.editorconfig`, ` ruff.toml` |
| 新增独立工具函数 | 不修改任何现有调用链的新函数 |
| 格式化/类型标注 | 纯 lint 修复、类型注解补充 |
| 已有测试全部通过 | 修改后测试仍绿 |

**P0 规则**：
- 直接执行，**不打断人类**
- 操作完成后在日志中记一行 `[P0] <操作> — <文件路径>`
- Agent 的分支策略：直接在当前分支提交，commit message 前缀 `[P0]`

### P1 — 批量确认（每 2 小时汇总一次，生成"人话清单"）

**判断标准**：操作可能影响功能但风险可控，回滚成本低

| 操作类型 | 示例 |
|---------|------|
| 修改普通业务模块 | 不涉及核心入口的业务逻辑调整 |
| 新增文件（<100 行） | 新工具函数、新组件（不改调用链） |
| 修改 1-3 个现有文件 | 非核心模块的修改 |
| 安装常见依赖 | `requests`, `numpy`, `lodash`, `react` 等 |
| 修改非核心 API | 不影响核心业务流程的端点调整 |

**P1 规则**：
- 将操作**加入决策队列**（见第四节），继续执行其他任务
- 不要停下来等人类，不要弹窗，不要 @ 人类
- 每 2 小时（或队列达到 10 项）自动生成**一份 Digest**
- 如果人类 4 小时未响应，自动降级为：在本地分支继续工作但不合并到主分支

### P2 — 强制拦截（立即停止，必须确认）

**判断标准**：不可逆、影响面大、或可能导致生产事故

| 操作类型 | 示例 |
|---------|------|
| 修改核心入口 | `main.py`, `App.tsx`, 路由入口, 数据库模型 |
| **删除任何文件** | 无论文件大小，删除必须确认 |
| 修改超 3 个文件 | 批量重构、跨模块变更 |
| 引入不常见依赖 | 网络库、加密库、系统级库、Native 模块 |
| 修改权限/认证 | 认证逻辑、RBAC 配置、API Key 轮换 |
| 修改数据库 schema | 表结构变更、迁移脚本、数据清洗 |
| 修改 CI/CD 配置 | pipeline、部署脚本、Dockerfile |

**P2 规则**：
- **立即停止当前操作**
- 输出一条**一句话业务影响描述**（格式见附录）
- **等待人类回复再继续**
- 如果人类 30 分钟未响应：自动在独立分支保存当前修改，然后可以继续其他任务

---

## 三、业务影响翻译（核心能力）

**你问人类之前，先自己回答三个问题。如果三个都是"否"→ 自动降级为 P0：**

1. **这个修改会影响用户可见的功能吗？**（界面、功能、性能）
2. **这个修改会导致数据丢失吗？**（数据库、文件、配置）
3. **这个修改会让其他 Agent 的工作失效吗？**（接口变更、协议变动）

### 翻译规则

| 不要说（技术语言） | 要说（业务语言） |
|-----------------|----------------|
| "重构 UserDAO.get_connection()" | "修改了用户数据库连接方式，可能影响登录功能" |
| "升级 SQLAlchemy 到 2.0" | "这个修改会让数据库操作更快，但需要重启服务" |
| "删除 deprecated.py" | "系统已检查：没有其他 Agent 在用这个文件，可以安全删除" |
| "合并 PR #42" | "这个修改新增了导出功能，旧功能不受影响" |

**强制规则**：每次对人类说话前，先把技术描述翻译成业务影响再输出。

---

## 四、决策队列协议

> 使用文件系统作为 Agent 间共享状态，不依赖任何外部服务。

### 队列目录结构

```
.governance/queue/
├── athena-ui/              # 按 Agent 名称分目录
│   ├── 20260610-1030-digest.json   # 生成的 Digest
│   └── pending/             # 待确认的 P1 项
│       ├── 001-modify-login-style.json
│       └── 002-add-avatar-upload.json
├── maref-core/
│   └── pending/
├── infra-devops/
│   └── pending/
└── _global-digest/          # 跨 Agent 汇总 Digest
```

### P1 项 JSON 格式

```json
{
  "id": "agent-name-001",
  "agent": "athena-ui",
  "timestamp": "2026-06-10T10:30:00+08:00",
  "type": "modify",
  "files": ["src/components/Login.tsx"],
  "technical": "修改登录页面样式和布局",
  "impact": "用户看到的登录界面会变好看，功能不变",
  "rollback": "git revert 即可恢复，不影响数据",
  "status": "pending"
}
```

### Digest 生成时机

- 每 2 小时（从 Agent 启动算起）
- 或 P1 队列达到 10 项
- Digest 写入 `.governance/queue/<agent>/<timestamp>-digest.json`
- 同时追加到全局汇总 `.governance/queue/_global-digest/YYYY-MM-DD.json`

### Digest 的人类阅读格式

```markdown
【P1 批量确认 - 过去 2 小时】

Agent: athena-ui
━━━━━━━━━━━━━━━━━━━━━━
1. 修改文件：登录页面样式
   业务影响：用户看到的登录界面会变好看，功能不变
   回滚方式：git revert，不影响数据
   [✅ 同意] [❌ 拒绝]

2. 新增文件：用户头像上传功能
   业务影响：用户上传头像后可以裁剪尺寸
   回滚方式：删除文件即可，无副作用
   [✅ 同意] [❌ 拒绝]

Agent: maref-core
━━━━━━━━━━━━━━━━━━━━━━
3. 修改文件：Agent 通信协议
   业务影响：各 Agent 之间的消息格式可能不兼容，需要重启服务
   ⚠️ 注意：此修改需要其他 Agent 同步更新
   [✅ 同意] [❌ 拒绝] [⏸️ 延后处理]

━━━━━━━━━━━━━━━━━━━━━━
【一键操作】[全部同意] [全部拒绝]
```

---

## 五、自动快照与回滚

### 自动快照协议

```
每 30 分钟执行一次：
  git tag -f snapshot-YYYYMMDD-HHMM
```

- 使用 `-f` 覆盖同名 tag（始终保持快照紧凑）
- 在每次 P1/P2 操作前也执行一次快照
- 快照仅保存在本地，不推送 remote

### 回滚协议

当人类说"回滚到 X 点"时：
1. 查找对应 `snapshot-<timestamp>` tag
2. 执行 `git reset --hard <tag>`
3. 告知人类：已回滚到 X 点，丢失了 Y 个提交

### 每日冻结

- 每天凌晨 3 点（人类睡觉时），自动创建：
  ```
  git tag checkpoint-YYYY-MM-DD
  ```
- 早上人类看报告时，可以一键：
  ```
  git reset --hard checkpoint-YYYY-MM-DD
  ```

---

## 六、工程规范质量门（每次提交前必须检查）

> 每份代码在 commit 前必须通过以下检查。不满足则自动暂停提交并报告。

### 通用规范

- [ ] 新增代码有对应测试（单元测试 ≥ 80% 覆盖率）
- [ ] 无硬编码密钥/凭证（仅环境变量或密钥管理服务）
- [ ] 无 `print()` 调试残留（使用 logger）
- [ ] 无 `TODO`/`FIXME`/`XXX` 未处理（有则记录到 `tech-debt.md`）
- [ ] 无 `try: ... except: pass` 空捕获
- [ ] 无超过 300 行的函数（拆解）
- [ ] 命名风格与项目现有一致（驼峰/蛇形/帕斯卡）

### Python 专有

- [ ] ruff 检查通过（或 flake8）
- [ ] mypy strict mode 检查通过
- [ ] 已有 pytest 测试全部通过

### TypeScript/JavaScript 专有

- [ ] ESLint 检查通过
- [ ] TypeScript strict 模式检查通过
- [ ] 已有测试全部通过

### 安全红线

- [ ] 无 SQL 拼接（使用参数化查询或 ORM）
- [ ] 无 `eval()`/`exec()` 调用
- [ ] 无路径穿越风险（用户输入直接拼文件路径）
- [ ] 无敏感信息泄露（日志中不打印密码、token、key）
- [ ] 依赖版本锁定（`package.json` / `requirements.txt` 无 `*`）

---

## 七、Per-Agent 风险配置

每个 Agent 可以有自己的风险阈值。当前配置在 `.governance/config.yaml`：

```yaml
agents:
  athena-ui:
    risk: low
    p2_count: 0          # 过去一周 P2 次数
    digest_interval: 2h  # P1 汇总间隔
  maref-core:
    risk: medium
    p2_count: 3
    digest_interval: 1h  # 核心模块更频繁汇总
  infra-devops:
    risk: high           # 高风险 = 几乎全是 P2
    p2_count: 12
    digest_interval: 30m # 频繁确认

defaults:
  digest_interval: 2h
  auto_merge: false       # 从不自动合并到 main
  snapshot_interval: 30m
```

如无此文件，使用默认值：`digest_interval=2h`, `snapshot_interval=30m`, `auto_merge=false`。

---

## 八、递归自演进（核心进阶能力）

> **本 Skill 从行为结果中学习，自动优化分类规则。** 每 100 次决策后触发一次演进迭代，结果固化到自身。

这使 `governance-orchestrator` 不再是一个静态规则集，而是**从人类每一轮审批中持续进化**的治理系统。

### 8.1 演进触发条件

满足任一即触发：

| 条件 | 说明 |
|------|------|
| **决策计数** | `.governance/metrics.json` 中 `total_decisions % 100 == 0` |
| **时间触发** | 距离上次演进超过 7 天 |
| **人类指令** | 人类明确说"运行自演进"或"进化一下" |

### 8.2 演进流程（五步）

```
Step 1 ─ 收集证据
  读取 .governance/queue/*/ 下所有 status!=pending 的记录
  汇总过去 N 次决策的人类审批结果

Step 2 ─ 模式分析
  找出高频拒绝的 P1 项（A类问题）→ 应升级为 P2
  找出总是通过的 P2 项（B类问题）→ 应降级为 P0/P1
  找出 Agent 频繁误判 P0 导致问题的项 → 补充规则

Step 3 ─ 生成变更
  基于分析结果，生成本 SKILL.md 的二节 P0/P1/P2 分类规则的修订
  变更必须是双向的：
    - "人类连拒 3 次相同 P1" → 该条目升级到 P2
    - "人类连批 5 次相同 P2" → 该条目降级到 P1
    - "Agent 误将数据库操作标为 P0" → P0 条目中补充明确排除

Step 4 ─ 自修改
  将 Step 3 生成的变更**写入本文件（SKILL.md）的二节**
  保留原规则作为"已废弃规则"注释（备查），新规则直接替换

Step 5 ─ 记录
  追加一条记录到 .governance/evolution-log.md
  更新 metrics.json：重置决策计数器
```

### 8.3 模式分析的判定标准

```
升级触发（P1→P2）：
  同一操作类型，过去 50 次决策中人类拒绝 ≥ 3 次
  → 结论："人类认为此类风险高，升级为 P2"

降级触发（P2→P1 或 P1→P0）：
  同一操作类型，过去 50 次决策中人类全部同意且无事故
  → 结论："人类对此类风险完全放心，降级一级"

新增规则触发：
  同一类问题出现在 digest 的 "Agent 误判" 记录 ≥ 2 次
  → 补充一条明确的包含/排除规则到分类表
```

### 8.4 安全机制

```
1. 每次演进前备份当前 SKILL.md → SKILL.md.evo-bak
2. 每次演进后版本号 PATCH+1（如 1.1.0 → 1.1.1）
3. 振荡检测: 同一规则在 3 次演进内来回修改 ≥ 2 次
   → 冻结该规则 10 次演进周期
4. 回滚: 人类可以说"回滚演进 N"→ 从 evolution-log 找到上一个版本恢复
5. 阈值不可演进: P2 中的"删除任何文件"和"权限/认证修改"为固定红线，永不降级
```

### 8.5 演进日志格式

每次演进后追加到 `.governance/evolution-log.md`：

```markdown
## 演进 #1 — 2026-06-15 09:00

触发条件：决策计数达 100

### 升级（P1→P2）
- 数据库 schema 修改：人类连拒 4 次，升级为 P2

### 降级（P2→P1）
- 安装常见依赖：人类连批 6 次且零事故，从 P2 降级为 P1

### 新增规则
- 暂无

### 本版本
SKILL.md v1.0.0 → v1.0.1
```

---

## 九、演进数据仪表板

每次演进时，除了更新 `evolution-log.md`，还要更新以下汇总文件：

### `.governance/metrics.json`

```json
{
  "total_decisions": 100,
  "approved": 78,
  "rejected": 22,
  "by_agent": {
    "athena-ui": { "total": 40, "approved": 38, "rejected": 2 },
    "maref-core": { "total": 35, "approved": 25, "rejected": 10 },
    "infra-devops": { "total": 25, "approved": 15, "rejected": 10 }
  },
  "by_type": {
    "modify_business": { "total": 30, "rejected": 2 },
    "delete_file": { "total": 3, "rejected": 1 },
    "modify_core": { "total": 15, "rejected": 8 },
    "install_dependency": { "total": 12, "rejected": 0 },
    "modify_schema": { "total": 5, "rejected": 4 }
  },
  "last_evolution": "2026-06-15T09:00:00+08:00",
  "decisions_since_last_evolution": 0,
  "evolution_version": "1.0.1",
  "frozen_rules": []
}
```

### 演进状态速查

```bash
# 查看演进历史
cat .governance/evolution-log.md

# 查看当前治理版本
grep "^version:" /path/to/SKILL.md

# 查看各 Agent 的拒绝率
python3 -c "import json; d=json.load(open('.governance/metrics.json')); [print(f'{a}: {v[\"rejected\"]}/{v[\"total\"]} ({100*v[\"rejected\"]/v[\"total\"]:.0f}% 拒绝)') for a,v in d['by_agent'].items()]"

# 人类指令：强制演进
# "运行自演进" 或 "进化一下"
```

## 十、人类一天的理想时间线

```
09:00  看 5 分钟"昨晚 Digest 邮件"，批量勾选 P1
09:05  处理 1 个 P2 紧急项（如果有）
09:10-12:00  人类做别的事（思考产品、见客户、休息）
12:00  看消息："3 个 Agent 有 8 项 P1 待确认"，批量勾选
12:05-18:00  人类做别的事
18:00  看"今日体检报告"：代码量、债务新增、架构合规
18:10  决定：是否回滚某个 Agent 的今日修改
夜间  人类睡觉 → Agent 自动跑测试、生成明日 Digest
```

**核心变化**：人类从"实时被中断"变成**每天 3 次，每次 5-10 分钟**。

---

## 十一、附录

### P2 紧急通知格式

```markdown
🚨 [P2 紧急] Agent <名称>
━━━━━━━━━━━━━━━━━━━━━━
操作：<一句话技术描述>
业务影响：<一句话说明对用户/系统的影响>
风险等级：<高/中>
建议操作：
  [继续] — 风险可控，按计划执行
  [回滚] — 放弃本次操作，恢复原状
  [延后] — 保存当前进度，等人类亲自处理

等待你的回复。
```

### 决策队列脚本（可选）

```bash
# 查看当前所有 Pending 队列
ls .governance/queue/*/pending/

# 查看某个 Agent 的 Digest
cat .governance/queue/athena-ui/pending/*.json

# 标记某项为已同意
python3 -c "
import json; d=json.load(open('.governance/queue/...json'));
d['status']='approved'; json.dump(d, open('.governance/queue/...json','w'))
"

# 生成全局 Digest
echo "=== 全局 Digest $(date) ==="
for d in .governance/queue/*/pending/*.json; do
  echo "--- $(basename $(dirname $(dirname $d))) ---"
  python3 -c "import json; d=json.load(open('$d'));print(f'{d[\"id\"]}: {d[\"impact\"]}')"
done
```

### 触发 P2 后，人类 30 分钟未响应

1. 在当前分支创建一个 WIP commit
2. 切换到新分支 `wip/<agent>/<feature>`
3. 推送该分支（如需）
4. 告知人类："P2 操作已保存到分支 wip/<agent>/<feature>，可继续其他任务"
5. 继续执行不相关的 P0 任务

---

## 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.1.0 | 2026-06-10 | 新增递归自演进（五步流程 + 模式分析 + 安全机制 + metrics） |
| 1.0.0 | 2026-06-10 | 初始版本，P0/P1/P2 异步批量治理模式 |

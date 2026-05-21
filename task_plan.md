# MAREF v0.27.0 迭代实施方案 — "Execution Layer: Groundwork"

> 基于《MAREF执行层战略规划-20260520.md》P0优先级执行
> 生成日期: 2026-05-20
> 基线版本: v0.26.0 (GA)
> 目标版本: v0.27.0
> 版本口号: "Let MAREF do things" — 让 MAREF 从"治理 OS"进化到"能动手的治理 OS"

---

## 战略定位

```
当前画像 (v0.26.0):
    治理深度    动手能力    生态绑定
MAREF  10/10       3/10       1/10

目标画像 (v0.27.0):
    治理深度    动手能力    生态绑定
MAREF  10/10       6/10       4/10
```

**核心差异化**: 所有执行操作经过 MAREF 治理层 — Spark 做不到这一点。

---

## 一、现状基线 (v0.26.0 GA)

### 已就绪的骨架

| 模块 | 状态 | 说明 |
|------|------|------|
| `mcp_client.py` | 🟢 骨架完备 | MCPClient, MCPConnection, MCPServerConfig, 状态机 |
| `mcp_transport.py` | 🟢 骨架完备 | StdioTransport, SSETransport, InProcessTransport |
| `mcp_server.py` | 🟢 骨架完备 | MCPServer, MCPTool, MCPResource, MCPPrompt 注册 |
| `mcp_security.py` | 🟢 骨架完备 | MCPTrustLevel, SecurityVerdict, AuditLogEntry, RateLimiter |
| `mcp_security_middleware.py` | 🟢 存在 | 安全中间件层 |
| `skill_executor.py` | 🟢 存在 | SkillExecutor + DegradationChain |
| `skill_schema.py` | 🟢 存在 | MarefSkill YAML schema |
| `skill_loader.py` | 🟢 存在 | YAML → MarefSkill 加载器 |
| `skill_trigger.py` | 🟢 存在 | Cron/Event 触发器 |
| `task_executor.py` (desktop) | 🟢 存在 | 桌面 TaskExecutor |
| `hitl.py` / `hitl_api.py` | 🟢 存在 | 人在回路 API |
| 治理层 (circuit_breaker, audit, state_machine) | 🟢 成熟 | 核心差异化能力 |

### 核心缺口

| 缺口 | 严重程度 | 说明 |
|------|---------|------|
| MCP Client 未连接治理层 | P0 | 工具调用不经策略决策树 |
| 无内置 MCP 工具服务器 | P0 | 只有骨架，没有实际可用的工具 |
| 无统一 Executor 模块 | P0 | 执行能力分散在 desktop/recursive 各子模块 |
| 无异步任务队列 | P0 | 无持久化 TaskQueue，任务丢失 |
| 无 24/7 会话管理 | P1 | 无 SessionManager/Checkpointer |
| 无策略→MCP 授权映射 | P1 | 决策树未连接到工具调用 |
| 无 Skills 运行时 | P2 | Skill 定义存在但无运行时调度 |
| 工具调用无可观测性 | P2 | MCP 调用无 Trace/Otel 集成 |

---

## 二、v0.27.0 核心目标

### 目标 1: MCP 治理贯通 (P0)
**定义**: 所有 MCP 工具调用经过 MAREF 治理层 (策略决策树 + 断路器 + 审计日志)

```
当前:  MCP Client → 直接调用工具
目标:  MCP Client → 策略决策树 → 断路器 → 审计日志 → 工具调用
                                    ↓
                              HITL (高危操作)
```

**验收**:
- [ ] 每个 MCP 工具调用记录审计日志 (HMAC 签名)
- [ ] 高危工具触发断路器/HITL 中断
- [ ] 策略决策树可配置: 允许/拒绝/询问用户
- [ ] 审计日志可通过治理看板查询

### 目标 2: 5 内置 MCP 服务器 (P0)
**定义**: 仓库内维护 5 个可直接使用的内置 MCP 服务器

| 工具 | 功能 | 治理需求 |
|------|------|---------|
| `tools/file` | 文件读写 | 路径沙箱白名单 |
| `tools/shell` | 命令执行 | 命令白名单 + 超时熔断 |
| `tools/git` | Git 操作 | 仓库白名单 |
| `tools/browser` | 网页操作 | 域名白名单 + 只读/读写模式 |
| `tools/email` | 邮件发送/读取 | 收件人白名单 + 敏感词过滤 |

**验收**:
- [ ] 5 个工具全部可通过 `maref tools install <name>` 安装
- [ ] 每个工具有独立的策略配置
- [ ] 每个工具有单元测试覆盖 (≥ 80%)
- [ ] 集成测试验证治理层拦截

### 目标 3: Executor 模块 (新) (P0)
**定义**: `maref/executor/` 新模块 — 统一的任务执行引擎

**组件**:
```
maref/executor/
├── __init__.py
├── queue.py          # TaskQueue — 持久化异步任务队列
├── session.py        # SessionManager — 24/7 会话管理
├── checkpointer.py   # Checkpointer — 状态快照 + 恢复
├── worker.py         # WorkerPool — 任务执行工作池
├── types.py          # Task, TaskStatus, TaskResult 类型
└── scheduler.py      # Scheduler — Cron + Event 调度
```

**验收**:
- [ ] TaskQueue: 提交 → 排队 → 执行 → 完成/失败, 重启不丢失
- [ ] SessionManager: SSE/WebSocket 心跳, 会话保持
- [ ] Checkpointer: 快照创建/恢复, 故障后任务恢复
- [ ] WorkerPool: 并发执行, 超时熔断
- [ ] Scheduler: Cron 表达式 + 事件触发

### 目标 4: 异步任务 API (P1)
**定义**: RESTful API 用于任务提交、查询、管理

**端点**:
```
POST /api/v1/tasks           # 提交任务
GET  /api/v1/tasks/{id}      # 查询任务状态
POST /api/v1/tasks/{id}/cancel  # 取消任务
GET  /api/v1/tasks           # 任务列表 + 过滤
```

**通知通道**:
```
任务完成/失败 → 通知通道抽象: Email / Webhook / CLI
```

**验收**:
- [ ] 4 个端点完整实现
- [ ] 任务状态机: Pending → Running → Completed/Failed/Cancelled
- [ ] 通知通道可插拔
- [ ] OpenAPI schema 自动生成

---

## 三、实施阶段

### Phase 1: MCP 治理贯通 (Week 1)

| 任务 | 描述 | 产出 | 预估 Token |
|------|------|------|-----------|
| E1.1 | MCP Client → 策略决策树集成 | `mcp_client.py` 改造, 每次工具调用前过决策树 | 1M |
| E1.2 | 断路器集成到 MCP 调用 | MCP 调用触发熔断逻辑, 超时/错误率检测 | 0.8M |
| E1.3 | 审计日志 HMAC 签名贯通 | 每个 MCP 调用生成审计条目, HMAC-SHA256 签名 | 0.8M |
| E1.4 | HITL 中断流程集成 | 高危 MCP 调用触发 HITL, 用户确认后放行 | 1M |
| E1.5 | 策略决策树 → MCP 授权映射表 | 可配置的 YAML 映射: 工具 → 策略规则 | 0.6M |

**Phase 1 总计**: ~4.2M Token

### Phase 2: 内置 MCP 服务器 (Week 2)

| 任务 | 描述 | 产出 | 预估 Token |
|------|------|------|-----------|
| E2.1 | File MCP Server | 路径沙箱, 白名单, 读写操作 | 1.2M |
| E2.2 | Shell MCP Server | 命令白名单, 超时熔断, 输出限制 | 1.2M |
| E2.3 | Git MCP Server | 仓库白名单, 只读/读写模式 | 1M |
| E2.4 | Browser MCP Server | 域名白名单, headless 模式 | 1.5M |
| E2.5 | Email MCP Server | SMTP/IMAP, 收件人白名单, 敏感词过滤 | 1.2M |
| E2.6 | `maref tools` CLI | discover/install/policy 子命令 | 0.8M |

**Phase 2 总计**: ~6.9M Token

### Phase 3: Executor 模块 (Week 3)

| 任务 | 描述 | 产出 | 预估 Token |
|------|------|------|-----------|
| E3.1 | TaskQueue 持久化 | SQLite 后端, 优先级队列, 死信队列 | 1.5M |
| E3.2 | SessionManager | SSE 心跳, 会话恢复, 超时管理 | 1.2M |
| E3.3 | Checkpointer | 状态快照, 故障恢复, 版本管理 | 1.5M |
| E3.4 | WorkerPool | 并发执行, 超时熔断, 优雅关闭 | 1M |
| E3.5 | Scheduler | Cron 解析, 事件注册, 触发器 | 1M |

**Phase 3 总计**: ~6.2M Token

### Phase 4: 异步任务 API + 集成 (Week 4)

| 任务 | 描述 | 产出 | 预估 Token |
|------|------|------|-----------|
| E4.1 | 任务 API 端点 | 4 REST 端点 + OpenAPI schema | 1.2M |
| E4.2 | 通知通道 | Email/Webhook/CLI 通知 | 1M |
| E4.3 | GUI 任务面板 | 任务列表/状态/操作 UI 组件 | 1.5M |
| E4.4 | 端到端集成测试 | 全链路: API → Executor → MCP → 治理 | 1.5M |
| E4.5 | 文档 + 示例 | 快速开始, Skills 示例, 配置指南 | 0.8M |

**Phase 4 总计**: ~6M Token

---

## 四、验证标准

### 4.1 测试指标
| 指标 | 当前 (v0.26.0) | 目标 (v0.27.0) |
|------|---------------|---------------|
| 测试总数 | ~4,919 | ≥ 5,200 |
| 通过率 | ~4,910 | ≥ 99.5% |
| 覆盖率 | 76.51% | ≥ 78% |
| 新增测试 | - | ≥ 200 |
| executor 模块覆盖 | N/A | ≥ 85% |
| tools 模块覆盖 | N/A | ≥ 80% |

### 4.2 功能门禁
- [ ] E2E: `maref tools install file` → `maref task submit "read /tmp/test.txt"` → 返回结果
- [ ] E2E: 危险 shell 命令触发 HITL 中断
- [ ] E2E: 进程崩溃后 `maref task resume` 恢复执行
- [ ] 零新 ruff 违规
- [ ] mypy strict 通过

### 4.3 安全门禁
- [ ] 所有 MCP 调用可审计追溯
- [ ] 未经治理层授权的工具调用被拒绝
- [ ] 路径遍历攻击被路径沙箱拦截
- [ ] 命令注入攻击被命令白名单拦截

---

## 五、架构变更

### 新增目录结构
```
src/maref/
├── executor/              # [新] 执行层
│   ├── __init__.py
│   ├── queue.py
│   ├── session.py
│   ├── checkpointer.py
│   ├── worker.py
│   ├── types.py
│   └── scheduler.py
├── tools/                 # [新] 内置 MCP 工具
│   ├── __init__.py
│   ├── file_server.py
│   ├── shell_server.py
│   ├── git_server.py
│   ├── browser_server.py
│   ├── email_server.py
│   └── registry.py       # 工具注册表 + CLI
└── integration/
    ├── mcp_client.py       # [改] 集成治理层
    ├── mcp_security.py     # [改] 增强审计 + 策略
    └── mcp_security_middleware.py # [改] 集成断路器

tests/
├── executor/              # [新] Executor 测试
└── tools/                 # [新] 工具测试

gui/src/components/
├── tasks/                 # [新] 任务面板
└── tools/                 # [新] 工具管理
```

### 修改的核心文件
| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/maref/integration/mcp_client.py` | 重构 | 工具调用前过治理层 |
| `src/maref/integration/mcp_security.py` | 增强 | 集成断路器 + 策略决策树 |
| `src/maref/integration/__init__.py` | 修改 | 导出新模块 |
| `src/maref/integration/mcp_bridge.py` | 修改 | 支持 SessionManager |
| `gui/src/App.tsx` | 修改 | 新增任务/工具路由 |
| `gui/src/api/client.ts` | 修改 | 新增任务 API 调用 |
| `pyproject.toml` | 修改 | 新增依赖, 更新覆盖配置 |

---

## 六、依赖与风险

### 依赖
| 依赖项 | 用途 | 替代方案 |
|--------|------|---------|
| `pyautogui` | 桌面操作 (Browser 工具) | `pyobjc` 直接调用 |
| `selenium`/`playwright` | 浏览器自动化 | `requests` + HTML 解析 |
| `aiohttp` | 异步 HTTP (MCP SSE) | `httpx` |
| `apscheduler` | Cron 调度 | 内置 `sched` |
| `smtplib`/`imaplib` | 邮件 (标准库) | 无替代需求 |

### 风险与缓解
| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| MCP 治理层增加延迟 | 中 | 中 | 决策树缓存, 审计异步写入 |
| 浏览器工具维护成本高 | 高 | 中 | 优先 Playwright, fallback requests |
| 邮件工具需要 SMTP 凭证 | 中 | 中 | 仅配置模式, 不硬编码 |
| 任务队列 SQLite 并发限制 | 低 | 中 | WAL 模式, 可选 PostgreSQL 后端 |
| Shell 工具安全风险 | 中 | 高 | 严格命令白名单 + HITL |

---

## 七、Token 预算

| Phase | 任务数 | Token 预估 | USD 预估 |
|-------|--------|-----------|---------|
| Phase 1: MCP 治理贯通 | 5 | 4.2M | $420 |
| Phase 2: 内置 MCP 工具 | 6 | 6.9M | $690 |
| Phase 3: Executor 模块 | 5 | 6.2M | $620 |
| Phase 4: API + 集成 | 5 | 6.0M | $600 |
| **合计** | **21** | **23.3M** | **$2,330** |
| 含 40% 缓冲 |  | **32.6M** | **$3,262** |

---

## 八、里程碑

| 里程碑 | 截止 | 交付物 | 门禁 |
|--------|------|--------|------|
| M1: MCP 治理贯通 | Day 7 | 治理层集成 MCP 客户端 | E2E 工具调用可审计 |
| M2: 工具就绪 | Day 14 | 5 内置 MCP 服务器 + CLI | tools 模块 ≥ 80% 覆盖 |
| M3: Executor 就绪 | Day 21 | executor 模块完整 | 200+ 测试通过 |
| M4: 版本发布 | Day 28 | v0.27.0 Release | 全部门禁通过 |

---

## 九、Factory Missions 组织

```
.missions/v0.27.0-execution-layer/
├── mission.json
├── features.json
├── validation-contract.md
├── features/
│   ├── E1_mcp_governance/
│   │   ├── E1.1_policy_integration.md
│   │   ├── E1.2_circuit_breaker.md
│   │   ├── E1.3_audit_hmac.md
│   │   ├── E1.4_hitl_flow.md
│   │   └── E1.5_policy_mapping.md
│   ├── E2_builtin_tools/
│   │   ├── E2.1_file_server.md
│   │   ├── E2.2_shell_server.md
│   │   ├── E2.3_git_server.md
│   │   ├── E2.4_browser_server.md
│   │   ├── E2.5_email_server.md
│   │   └── E2.6_cli_tools.md
│   ├── E3_executor/
│   │   ├── E3.1_task_queue.md
│   │   ├── E3.2_session_manager.md
│   │   ├── E3.3_checkpointer.md
│   │   ├── E3.4_worker_pool.md
│   │   └── E3.5_scheduler.md
│   └── E4_api_integration/
│       ├── E4.1_task_api.md
│       ├── E4.2_notifications.md
│       ├── E4.3_gui_tasks.md
│       ├── E4.4_e2e_tests.md
│       └── E4.5_documentation.md
└── knowledge/
```

---

## 十、执行纪律

### Handoff Discipline
每个 Feature 完成后:
1. `pytest tests/ -v --cov` — 覆盖率 ≥ 80% (新模块 ≥ 85%)
2. `ruff check src/maref/executor/ src/maref/tools/` — 零违规
3. `mypy src/maref/executor/ src/maref/tools/` — strict 通过
4. Git commit: `feat(executor|tools): description`
5. 更新 `features.json`
6. 在 `knowledge/` 留下实现笔记

### 安全规则 (不可违反)
1. 所有 MCP 工具调用必须经过治理层
2. Shell 工具必须命令白名单 + 超时熔断
3. 文件工具必须路径沙箱白名单
4. 审计日志必须 HMAC-SHA256 签名
5. HITL 中断不可绕过
6. 凭证/密钥仅环境变量注入

---

## 版本时间线

| 阶段 | 日期 | 交付 |
|------|------|------|
| Phase 1: MCP 治理贯通 | 2026-05-21 → 2026-05-27 | M1 |
| Phase 2: 内置 MCP 工具 | 2026-05-28 → 2026-06-03 | M2 |
| Phase 3: Executor 模块 | 2026-06-04 → 2026-06-10 | M3 |
| Phase 4: API + 集成 | 2026-06-11 → 2026-06-17 | M4 (Release) |

**总工期**: 4 周 (2026-05-21 → 2026-06-17)
**总 Token**: 32.6M (含缓冲)
**总成本**: ~$3,262
**目标评分**: Pre-GA 7.5/10 → GA-Ready 8.5/10
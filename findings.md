# v0.27.0 迭代研究发现

## 战略上下文

### 核心问题陈述
- MAREF 当前"治理很强但动手能力很弱"（治理 10/10, 执行 3/10）
- 对标: Google Gemini Spark (3/10, 8/10), Claude Cowork (4/10, 8/10), OpenAI Operator (3/10, 7/10)
- 战略定位: **"Agent 的 Kubernetes"** — 治理与执行并重，所有执行经过治理层

### 差异化优势
- Spark 的 MCP 调用没有治理拦截；MAREF 可以做到每个工具调用先过策略决策树再放行
- MAREF 不需要自己的 Cloud VM — 它可以治理运行在任何云上的任何 Agent
- 但 MAREF 需要自己的轻量级内置执行器 — 安全、有治理的自动化工作流引擎

## 现状基线与骨架分析

### 已有骨架（可直接利用）
1. **MCP Client 层**: `mcp_client.py` — MCPClient, MCPConnection, MCPServerConfig, ConnectionState 状态机
2. **MCP 传输层**: `mcp_transport.py` — StdioTransport, SSETransport, InProcessTransport, 完整 JSONRPC
3. **MCP Server 层**: `mcp_server.py` — MCPServer, MCPTool/MCPResource/MCPPrompt 注册
4. **MCP 安全层**: `mcp_security.py` — MCPTrustLevel, SecurityVerdict, AuditLogEntry, RateLimiter
5. **MCP 安全中间件**: `mcp_security_middleware.py` — 安全中间件集成
6. **Skills 框架**: `skill_executor.py` + `skill_schema.py` + `skill_loader.py` + `skill_trigger.py`
7. **桌面 TaskExecutor**: `desktop/task_executor.py` — TaskExecutor, TaskStep, TaskResult
8. **HITL**: `hitl.py` + `hitl_api.py` — 人在回路 API
9. **治理层**: circuit_breaker, audit, state_machine — 成熟的核心差异化能力

### 关键发现
- MCP Client 已有完整的连接管理和工具调用能力，但**没有集成治理层**
- Skill 定义（YAML schema）和加载器已存在，但**无运行时调度引擎**
- 桌面 TaskExecutor 存在但**不适合通用任务执行**
- 策略决策树（`desktop/policy_decision_tree.py`）已存在，但**未连接到 MCP 层**

## 架构决策记录

### 决策 1: Executor 模块定位
- **选项 A**: 在 desktop/task_executor.py 基础上扩展
- **选项 B**: 新建独立 executor 模块
- **选择**: B — 独立模块。desktop TaskExecutor 专注桌面操控，新的 executor 模块专注通用异步任务执行

### 决策 2: 工具服务器运行模式
- **选项 A**: 每个工具独立子进程 (stdio MCP Server)
- **选项 B**: 进程内 InProcessTransport
- **选择**: B — 进程内，性能更好且安全管控更直接。未来可扩展为独立进程

### 决策 3: 任务队列后端
- **选项 A**: SQLite (轻量，零依赖)
- **选项 B**: Redis (性能好，但增加依赖)
- **选择**: A — SQLite + WAL 模式。可选 PostgreSQL 扩展

### 决策 4: 版本号
- **选项 A**: v0.27.0 (当前基线 v0.26.0)
- **选项 B**: v0.30.0 (重大架构变更)
- **选择**: A — v0.27.0。执行层是增量能力，不是架构重写

### 决策 5: Browser 工具依赖
- **选项 A**: Playwright (现代, Microsoft 维护)
- **选项 B**: Selenium (生态成熟)
- **选择**: A — Playwright。更快的 API，更好的 headless 支持，原生 async

## 风险预分析

### 技术风险
1. **Shell 工具安全**: 即使有白名单，命令注入变种很多。缓解：白名单 + HITL + 输出限制
2. **浏览器工具兼容性**: 不同网站反爬机制。缓解：Playwright stealth 模式 + 用户代理配置
3. **任务队列持久化**: SQLite 多进程并发问题。缓解：WAL 模式 + 文件锁

### 执行风险
4. **4 周工期偏紧**: 21 个任务。缓解：Phase 1 优先，必要时裁减 Phase 4
5. **与现有 desktop 模块重叠**: executor 可能与 desktop TaskExecutor 混淆。缓解：清晰架构边界文档
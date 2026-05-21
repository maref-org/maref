# v0.27.0 验证合同 (Validation Contract)

> 基线版本: v0.26.0 (GA)
> 目标版本: v0.27.0
> 生成日期: 2026-05-21

---

## 一、功能门禁

### M1: MCP 治理贯通
- [x] E1.1-A1: MCPGovernance.evaluate() 返回 ALLOW/DENY/ASK_USER
- [x] E1.1-A2: 每个 MCP 工具调用记录 HMAC-SHA256 签名的审计日志
- [x] E1.1-A3: 高危工具触发 HITL 中断
- [x] E1.1-A4: MCPClient.call_tool() 集成治理层，DENY 不执行传输调用
- [x] E1.2-A1: MCP 调用触发熔断逻辑，超时/错误率检测
- [x] E1.3-A1: 每个 MCP 调用生成审计条目，HMAC-SHA256 签名
- [x] E1.4-A1: 高危 MCP 调用触发 HITL，用户确认后放行
- [x] E1.5-A1: 可配置的 YAML 映射：工具 → 策略规则

### M2: 内置 MCP 工具
- [x] E2.1: File MCP Server — 路径沙箱，白名单，读写操作
- [x] E2.2: Shell MCP Server — 命令白名单，超时熔断，输出限制
- [x] E2.3: Git MCP Server — 仓库白名单，只读/读写模式
- [x] E2.4: Browser MCP Server — 域名白名单，headless 模式
- [x] E2.5: Email MCP Server — SMTP/IMAP，收件人白名单，敏感词过滤
- [x] E2.6: `maref tools` CLI — discover/install/policy 子命令

### M3: Executor 模块
- [x] E3.1: TaskQueue 持久化 — SQLite 后端，优先级队列，死信队列
- [x] E3.2: SessionManager — SSE 心跳，会话恢复，超时管理
- [x] E3.3: Checkpointer — 状态快照，故障恢复，版本管理
- [x] E3.4: WorkerPool — 并发执行，超时熔断，优雅关闭
- [x] E3.5: Scheduler — Cron 解析，事件注册，触发器

### M4: API + 集成
- [x] E4.1: 任务 API 端点 — 4 REST 端点 + OpenAPI schema
- [x] E4.2: 通知通道 — Email/Webhook/CLI 通知
- [x] E4.3: GUI 任务面板 — 任务列表/状态/操作 UI 组件
- [x] E4.4: 端到端集成测试 — 全链路: API → Executor → MCP → 治理
- [x] E4.5: 文档 — API 参考 + 通知通道配置指南

---

## 二、测试门禁

| 门禁 | 状态 |
|:-----|:----:|
| 全部 677 测试通过 | ✅ 2026-05-21 |
| executor 模块覆盖率 ≥ 85% | ✅ 实测 85.51%~100% |
| tools 模块覆盖率 ≥ 80% | ✅ 实测 86.52%~100% |
| Ruff 零违规 | ✅ 已通过 |
| mypy strict 通过 | ❌ 待验证 |

---

## 三、安全门禁

- [x] 所有 MCP 调用可审计追溯 (HMAC-SHA256)
- [x] 未经治理层授权的工具调用被拒绝 (DENY)
- [x] 路径遍历攻击被路径沙箱拦截 (PathSandbox)
- [x] 命令注入攻击被命令白名单拦截 (CommandWhitelist + MetacharacterBlock)

---

## 四、架构完整性

- [x] `src/maref/executor/` — 8 个模块完整
- [x] `src/maref/tools/` — 6 个文件完整
- [x] `src/maref/integration/mcp_governance.py` — 治理层完整
- [x] `gui/src/components/views/TaskPanelView.tsx` — 任务面板完整
- [x] `tests/executor/`, `tests/tools/`, `tests/test_e2e_executor.py` — 测试完整

---

## 五、版本信息

- pyproject.toml: `0.27.0`
- gui/package.json: `0.27.0`
- CHANGELOG: 已更新 v0.27.0 条目
- Git: 已提交 v0.27.0 版本标签
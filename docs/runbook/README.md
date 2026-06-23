# MAREF Runbook 目录

## 核心告警响应手册

| 编号 | 告警名称 | 严重级别 | 触发条件 | 对应 Runbook | 升级路径 |
|------|---------|----------|---------|-------------|---------|
| RB-001 | `MarefSidecarDown` | P0 | `/health` 端点连续 3 次非 200 | [rb-001-sidecar-down.md](rb-001-sidecar-down.md) | 5 分钟未恢复 → SRE 主管 |
| RB-002 | `MarefHighLatency` | P0 | API P99 延迟 > 500ms 持续 5 分钟，燃烧率 ≥ 14.4x | [rb-006-high-latency.md](rb-006-high-latency.md) | 15 分钟未恢复 → SRE 团队; 2h → 技术负责人 |
| RB-003 | `MarefErrorBudgetBurn` | P0/P1 | 错误预算燃烧率 ≥ 14.4x (P0) 或 ≥ 6x (P1) | [rb-007-error-budget-burn.md](rb-007-error-budget-burn.md) | 预算剩余 < 20% → SRE 主管; 耗尽 → 紧急降级 |
| RB-004 | `MarefMemoryGrowth` | P1 | 内存使用增长率 > 5%/h 或接近 limits | [rb-005-memory-growth.md](rb-005-memory-growth.md) | 持续增长 > 6h → 内核团队; OOM → P0 升级 |
| RB-005 | `MarefAuditLogFailure` | P0 | 审计日志写入失败率 > 1% | [rb-004-audit-log-failure.md](rb-004-audit-log-failure.md) | 10 分钟未恢复 → 安全团队; 30min → CISO |
| RB-006 | `MarefGovernanceDrift` | P1 | 治理漂移分数超过阈值持续 3 个检测周期 | [rb-008-governance-drift.md](rb-008-governance-drift.md) | > 6h → 治理团队; > 24h → 架构师 |
| RB-007 | `MarefGovernanceLatencyHigh` | P1 | P99 治理决策延迟 > 500ms 持续 5 分钟 | [rb-002-governance-latency.md](rb-002-governance-latency.md) | 30 分钟未恢复 → 治理团队 |
| RB-008 | `MarefDriftDetected` | P1 | 漂移值超过阈值持续 2 个检测周期 | [rb-003-drift-detected.md](rb-003-drift-detected.md) | > 6h → 数据科学团队 |
| RB-009 | `MarefMCPToolFailure` | P1/P0 | MCP 工具调用返回错误或超时 | [rb-009-mcp-tool-failure.md](rb-009-mcp-tool-failure.md) | 全部工具失败 → P0 升级至 SRE |
| RB-010 | `MarefBrowserAutomationFailure` | P1 | BrowserController 方法异常 | [rb-010-browser-automation-failure.md](rb-010-browser-automation-failure.md) | > 15min → 桌面自动化团队 |
| RB-011 | `MarefAuditBusDown` | P1/P0 | AuditBus 事件延迟 > 5s 或订阅者未收到 | [rb-011-auditbus-down.md](rb-011-auditbus-down.md) | 完全阻塞 > 10min → 架构团队 |

## 通用流程

- [版本回滚流程](rollback-procedure.md) — 触发条件: 发布后 P0 缺陷或兼容性问题
- [紧急停机流程](emergency-shutdown.md) — 触发条件: 安全事件或数据泄露
- [事后复盘模板](postmortem-template.md) — 触发条件: 任何 P0/P1 事故处理后

## 告警与 Runbook 关联规则

| 告警源 | 匹配方式 | 示例 |
|--------|---------|------|
| Prometheus Alertmanager | `alertname` 精确匹配 Runbook 告警名称列 | `alertname=MarefSidecarDown` → RB-001 |
| CI/CD Pipeline | 发布流水线失败自动关联 | 发布回滚 → 通用流程-版本回滚流程 |
| ErrorBudgetCalculator | 燃烧率告警自动映射 | `burn_rate >= 14.4` → RB-003/MarefErrorBudgetBurn |
| 手动工单 | 人工选择告警场景 | 根据严重级别选择对应 Runbook |

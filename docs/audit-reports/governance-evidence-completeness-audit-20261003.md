# MAREF 治理证据完整性补全审计 — 2026-10-03

- **审计类型**: 证据存在性 + 可验证性补全审计（Evidence Completeness Audit）
- **执行时间**: 2026-10-03 16:25 – 16:45 (UTC+8)
- **执行者**: opencode (mimo-v2.6-flash-free) · 经 MAREF governance MCP
- **审计范围**: 遥测层 / 治理执行层 / 自证明报告层 三层证据链
- **结论摘要**: 三层产物**都存在且部分活跃**，但**互相不可对账**——报告盯错目录、KPI 归零、哈希链不可复算，导致"有治理现场、无治理证明"。

---

## 1. 本次执行的审计动作（可复现）

| # | 命令 | 结果 |
|---|------|------|
| 1 | `python3 scripts/audit_health_check.py` | healthy=false，3 阻断 + 4 警告（**误报，见 G-01**） |
| 2 | `bash scripts/daily_governance_cycle.sh --quiet` | exit=0，1 失败：`coding-agent-status` |
| 3 | `python3 scripts/verify_audit_chain.py --audit-file <4条链>` | **4/4 Hash mismatch**；hooks 链 `KeyError: 'id'` |
| 4 | `python3 scripts/approval_tier.py` | allow=5 / unknown=256 / deny=0 |
| 5 | `python3 scripts/backlog_sla.py` | 总积压 572（中危），高危 0，SLA 达标 |
| 6 | `python3 scripts/governance_loop_validator.py` | 近 7 天：提案 0 / 部署 0 / 回滚 0 |
| 7 | `python3 scripts/check_telemetry_endpoint.py` | telemetry.maref.org DNS 失败；maref.cc HTTP 403 |
| 8 | `python3 scripts/coding_agent_status.py` (系统 python3.9) | **ImportError: cannot import name 'UTC'** |
| 9 | `curl 127.0.0.1:8931/api/health` | `{"status":"healthy","collector_running":true,"buffer_size":1000}` |
| 10 | 手工链哈希复算（4 条链，多 payload 组合） | 1 条可复算 / 3 条不可复算 |

---

## 2. 三层证据矩阵

### 2.1 遥测层

| 证据 | 路径/端点 | 规模 | 最新时间 | 状态 |
|------|-----------|------|----------|------|
| 探针读数 DB | `governance_observations.db` → `probe_readings` | **184,224 行 / 28MB**，5 类探针（oscillation 174,972、entropy 7,826、agent_trust 434、governance_health 434、test 558） | 2026-10-03 06:00 | ✅ 活跃日更 |
| Sidecar 采集器 | `127.0.0.1:8931/api/health` | healthy, collector_running=true, buffer=1000 | 实时 | ✅ 存活（进程自 10-01 起） |
| 信任分历史 | `.governance/trust_scores.jsonl` | 107,166 行 | **2026-07-24** | ⚠️ 停更 70 天 |
| 本地 ObsEvent 缓冲 | `~/.maref/obs/behavior_*.ndjson` | 仅 140 行，覆盖 3 天 | **2026-09-29** | ⚠️ 断续 |
| 远程遥测端点 | `telemetry.maref.org` / `maref.cc` | — | — | ❌ DNS 失败 / 403；本地聚合器未装 |
| agent_trust 探针质量 | `probe_readings.context_json` | `agents_with_data: 0` | 2026-10-03 | ❌ 空洞采样（分值恒 50） |

### 2.2 治理执行层

| 证据 | 路径 | 规模 | 最新时间 | 状态 |
|------|------|------|----------|------|
| **Per-tool 决策链（最强证据）** | `~/.claude/hooks/state/governance_audit.jsonl` | **63,973 条**；verdict: EXECUTED 34,110 / ALLOW 29,373 / **BLOCKED 473** / DENY 12 / FAILED 5；agent: claude-code 63,500、unified-proxy 473；工具: Bash 34,040、Read 7,621、Edit 6,138、Task* 4,021、Write 1,261、Agent 573；带 HMAC | **2026-09-24 23:05** | ⚠️ 数据真实但 **STALE 210h** |
| openclaw 运行时主链 | `${MAREF_RUNTIME_DIR}/.governance/governance_audit.jsonl` | 38.9MB / 69,508 行；actor 99.9% `state_machine`；**unique agent_id = 0** | 2026-10-03 15:34 | ⚠️ 活跃但**无 per-agent 裁决** |
| tiered-loop 生产链 | `${MAREF_RUNTIME_DIR}/.governance/audit/governance_audit.jsonl` | 3.67MB / 8,095 行；actor: tiered-loop 6,894、openclaw 891（meta_cognitive_audit 761 次异常脚本复活 + 116 次高频脚本） | **2026-10-03 16:39** | ✅ 活跃，但 22 处 prev_hash 断点 |
| Overlay 决策链 | `${MAREF_RUNTIME_DIR}/governance_audit.jsonl` | 7 行，`governance_decision` + verdict=allow | 2026-10-03 16:41 | ✅ **哈希可完整复算** |
| Sidecar 进程 | `maref_governance_sidecar.py` (8931) | PID 99980，自 10-01 12:00 | 运行中 | ✅ |
| MCP 治理接入 | `maref_governance_mcp.py` × 2 | PID 55961 / 83827 | 10-03 16:19 | ✅ 在跑，但**不落盘决策**（无状态 CLI 包装） |
| Claude Code hook | `~/.claude/hooks/pre_tool_all.py` | mode=`enforce`；GovernanceClient 已删，内联 fail-open 替代 | 配置 07-24 | ⚠️ 降级运行 |
| 审批分层 | `approval_tier_report.json` | 261 决策：allow 5 / unknown 256 / deny 0 | 2026-10-03 | ⚠️ 裁决几乎全 unknown |
| 治理闭环 | `validation_20261003.json` | 近 7 天提案 0 / 部署 0 / 回滚 0 | 2026-10-03 | ❌ 闭环零流动 |
| Agent 注册表 | `.governance/agent_registry.json` | **64 个**（generated_at 2026-07-24），active=28，status=degraded | 2026-07-24 | ⚠️ 陈旧，**无 180+ 口径** |
| Coding agent 注册表 | `configs/coding_agents_registry.json` | 5 个（opencode / claude-code / trae-cn / codex / +1），connected 4 / degraded 1 | — | ⚠️ 覆盖面窄 |
| Coding agent KPI | `reports/coding_agents_status.json` | **tool_calls_total=0, intercepted=0, denied=0, hitl=0** | 2026-10-02 22:00 | ❌ 全零（见 G-04） |

### 2.3 自证明报告层

| 证据 | 数量 | 最新 | 状态 |
|------|------|------|------|
| 定期 JSON 报告（`reports/*report*.json` / `*audit*.json`） | **34** | 2026-10-03 | ✅ |
| 晨报 `morning-report-*.json` | **23**（09-11 起） | 2026-10-03，status=attention | ✅ 日更 |
| 治理循环日志 `daily-logs/governance-cycle-*.log` | **22** | 2026-10-03 16:41 | ✅ 日更 |
| 深度审计报告 `docs/audit-reports/*.md` | **8** | 2026-09-24 | ✅ |
| 自认证报告 `self_certification_report_20260909_final.json` | 1 | 2026-09-09 | ⚠️ 自认 approved=0、无 verdict 字段、置信度 12.0 vs 常量 68 |
| 今日补跑产物 | — | `audit_health_check.json`、`morning-report-20261003.json`、`backlog_sla_report.json`、`governance_loop_validation` | ✅ 本次审计产出 |

---

## 3. 缺口清单（G-01 ~ G-10）

| ID | 缺口 | 证据 | 影响 |
|----|------|------|------|
| **G-01** | `audit_health_check` 链清单**不含真实活跃链**：`openclaw/.governance/audit/`（tiered-loop，16:39）、openclaw 根 overlay 链均未登记；`_runtime_dir()` 依赖 `MAREF_RUNTIME_DIR`，交互式运行回落 REPO_DIR → 盯错仓库 | 交互跑出 3 阻断，cycle 跑出 1 阻断，**同一脚本两种结论** | 健康判定不可信 |
| **G-02** | 4 条链哈希**无法用 `verify_audit_chain.py` 复算**；hooks 链 schema 不同直接 `KeyError: 'id'` | 手工复算：openclaw 根链 MATCH，`.governance/audit` 链、maref 两链 **NO MATCH** | 审计不可验证（ISO 27001 C.5.33 失守） |
| **G-03** | `.governance/audit/` 主链 **22 处 previous_hash 断点**（首断在第 37 行，previous_hash 清空） | 8,095 行中 22 断 | 链连续性受损 |
| **G-04** | Coding agent KPI 全零三根因：① MCP guard **不落盘决策**；② sidecar `/api/telemetry/query` 需 Bearer token，脚本未带；③ ObsEvent 断续（最新 09-29） | `coding_agents_status.json` global_kpi 全 0 | **无法证明对 opencode/claude-code 的有效拦截** |
| **G-05** | `coding_agent_status.py` 在系统 python3.9 崩溃（`from datetime import UTC`），daily cycle 该步 `fail` | `failures-2026-10-03.log` | 自证明链路单点失败 |
| **G-06** | Claude Code hook 链 STALE 210h：GovernanceClient 2026-07-24 被删，内联 fail-open 替代后**未恢复写入**（末条 09-24 23:05） | 63,973 条历史证据 vs 210h 空白 | 最强证据链断裂 |
| **G-07** | 远程遥测上报断：`telemetry.maref.org` DNS 失败、`maref.cc` 403、本地聚合器未装 | `check_telemetry_endpoint.py` exit=1 | 部署健康度无法上报 |
| **G-08** | **180+ agent 无对账源**：registry 64（07-24）/ active 28 / internal/agents 44 文件 / coding registry 5，无任何口径指向 180+ | `agent_registry.json`、`health_snapshot.json` | 覆盖率无法证明 |
| **G-09** | 裁决质量：261 决策中 unknown 256（98%）、deny 0；置信度 13.91（legacy 68）；critical 占比 91% | `approval_tier_report.json`、`confidence_audit.json` | 治理"判了等于没判" |
| **G-10** | 治理闭环零流动：近 7 天提案 0 / 部署 0 / 观测评估 0；backlog 572 中危全部 >14d | `governance_loop_validation` | 飞轮未转 |

---

## 4. 结论

1. **存在性：三层产物都存在**——遥测（184k 探针 + 活着的 sidecar）、治理执行（63,973 条 per-tool 裁决 + 活跃 tiered-loop/overlay 链）、自证明报告（34 定期 + 23 晨报 + 22 循环日志）。
2. **有效性：只有历史可证，当前窗口不可证**——最强的 per-tool 治理证据停在 210h 前；当前活跃链只有状态机 tick，**0 条 per-agent 裁决**。
3. **可验证性：不合格**——哈希链 3/4 不可复算、22 处断点、健康检查盯错目录、KPI 全零。
4. 因此当前状态是：**"有治理现场，无治理证明"**（governance exists, governance evidence doesn't）。

补全实施方案见 `docs/plans/2026-10-03-governance-evidence-completion.md`。

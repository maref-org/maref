# MAREF 元审计报告：v0.37.0-dev 全量门禁审计

**审计日期**: 2026-07-29
**审计范围**: 全仓源代码、脚本、配置、测试
**审计依据**: docs/release-gate.md（MAREF 自有门禁规范）
**目标成熟度**: Beta

---

## 0. 执行摘要

| 维度 | 得分 | 权重 | 加权 |
|------|------|------|------|
| 功能完整性 (FUNC) | 14/20 | 20% | 14.0 |
| 工程质量 (ENGR) | 16/20 | 20% | 16.0 |
| 安全合规 (SEC) | 18/20 | 15% | 13.5 |
| 性能体验 (PERF) | 12/15 | 10% | 8.0 |
| 运维就绪 (OPS) | 10/15 | 15% | 10.0 |
| **元审计健康度 (META)** | **5/15** | **20%** | **6.7** |
| **总分** | | | **68/100 → D级 (不合格)** |

**核心结论**: 未通过 Beta 门禁。元审计维度（META）评分仅 5/15，低于 Beta 等级要求的 M0+M1 全通过。三个关键严重缺陷导致整体不合格。

---

## 1. M0 — 生存性断言（严重缺陷）

| # | 检查项 | 状态 | 详情 | Severity |
|---|--------|------|------|----------|
| M0.1 | 健康快照新鲜度 | ⚠️ **未连接** | `HealthSnapshotWriter` 类存在 (`observability/health_snapshot.py`)，`is_fresh(max_age=120s)` 方法已实现，但 **生产代码中没有调用者** — 没有任何模块定期调用 `write_snapshot()` | BLOCKING |
| M0.2 | 审计日志增长 | ⚠️ **未监控** | `AuditLogger` 写入 JSONL + 自动轮转 (`_rotate`)，但 **无 meta-monitor 检查日志文件 mtime** | BLOCKING |
| M0.3 | 心跳脉冲新鲜度 | ⚠️ **孤立的实现** | `PulseWriter` 类完整实现 (`agent_health.py:136-234`)：`write_pulse()`、`is_alive()`、`check_pulse_staleness()` 均可工作，但 **无 meta-monitor 调用它们**。`PulseWriter` 不被任何生产代码实例化 | BLOCKING |
| M0.4 | Managed Agent 存活 | ❌ **完全缺失** | `check_pulse_staleness()` 静态方法可以检测死亡 agent，但 **无调度器周期性运行它** | BLOCKING |
| M0.5 | HMAC 密钥存在 | ✅ | `AuditLogger.__init__()` 在缺少密钥时抛出 `RuntimeError`。环境变量 `MAREF_HMAC_SECRET_KEY` / `MAREF_ED25519_PRIVATE_KEY` | NON-BLOCKING |
| M0.6 | GaaS API 健康 | ⚠️ **静态健康检查** | `GET /api/v1/gaas/health` 始终返回 `{"status": "healthy"}` — 不检查数据库连接、CB 状态、HITL 可用性 | BLOCKING |

**M0 通过**: ❌ BLOCKING 项 3/5 不通过，非阻塞项 1/1 通过

---

## 2. M1 — 审计数据一致性（严重缺陷）

| # | 检查项 | 状态 | 详情 | Severity |
|---|--------|------|------|----------|
| M1.1 | 路径一致性 | ❌ **分裂** | 审计数据写入至少 3 条独立路径：`governance/audit.py` → 指定 log_path，`health_snapshot.py` → `.governance/health_snapshot.json`，`PulseWriter` → `.governance/pulses/`。**无校验写入路径 = 读取路径** | BLOCKING |
| M1.2 | 格式一致性 | ❌ **多格式并存** | 至少 4 种审计条目格式：`AuditEntry` (17字段, governance/audit.py)、`UnifiedAuditRecord` (10字段, recursive/unified_audit.py)、`GaaSAuditEntry` (gaas/audit_service.py)、`AuditEvidence` (9字段, eivl/merkle_auditor.py)。**无交叉格式校验** | BLOCKING |
| M1.3 | 时间戳一致性 | ❌ **未验证** | 各子系统使用 `time.time()`，但 **无时钟偏差校验**。多副本环境可能产生时间戳不一致 | NON-BLOCKING |
| M1.4 | 数据不分裂 | ❌ **已分裂** | 审计日志分散在多个路径，无统一索引或跨路径查询接口 | BLOCKING |
| M1.5 | 链式完整性 | ✅ **EIVL 实现完整** | `MerkleAuditor` + `AuditChainIntegrator` 实现 `previous_hash` 链接和 Merkle 证明。`verify_integrity()` 在 `governance/audit.py` 中支持 HMAC+Ed25519 验证。但 **EIVL 全内存，无持久化** | BLOCKING |

**M1 通过**: ❌ BLOCKING 项 3/4 不通过

---

## 3. M2 — 反馈回路闭合（严重缺陷）

| # | 检查项 | 状态 | 详情 | Severity |
|---|--------|------|------|----------|
| M2.1 | 通知文件存活审计 | ❌ **不存在** | `.openclaw/notifications/` 目录从未创建。**无通知文件存活时长追踪** | BLOCKING |
| M2.2 | 告警修复验证 | ❌ **未实现** | `Observability/alert_rules.py` 定义 5 条规则可生成 `Alert`，`NotificationManager` 可发送通知，但 **无告警→修复→验证的回路追踪** | BLOCKING |
| M2.3 | 重复告警率 | ❌ **无去重** | `Alert` 无去重机制，无重复告警率统计 | NON-BLOCKING |

**M2 通过**: ❌ BLOCKING 项 2/2 不通过

---

## 4. M3 — 元可观测性（严重缺陷）

| # | 检查项 | 状态 | 详情 | Severity |
|---|--------|------|------|----------|
| M3.1 | 元监控自身进程 | ❌ **缺失** | `meta-monitor` **未实现**。仅在 `health_snapshot.py` 和 `agent_health.py` 的 docstring 中被引用 | BLOCKING |
| M3.2 | 元监控报告可读 | ❌ | 无 `meta-monitor-report.json` 输出 | NON-BLOCKING |
| M3.3 | 元监控触发告警 | ❌ | 无 meta-monitor 故障检测 → 告警的链路 | BLOCKING |
| M3.4 | 健康快照内容完整 | ✅ | `HealthSnapshotWriter.write_snapshot()` 包含所有要求字段：status/timestamp/cycle/consecutive_errors/agent_crashes/pid/uptime | NON-BLOCKING |
| M3.5 | 审计日志可检索 | ✅ | `AuditLogger.read_all()`/`read_filtered()`/`read_recent()` 可用。Sidecar API `GET /api/v1/audit/logs` 暴露审计日志查询 | NON-BLOCKING |

**M3 通过**: ❌ BLOCKING 项 2/2 不通过

---

## 5. 四层鸿沟检测

| 层 | 状态 | 证据 |
|----|------|------|
| **配置≠运行时** | ❌ **不通过** | 5 个 launchd plist 配置了服务，但无进程比对验证。`watchdog_audit.py` 仅监控单个硬编码 PID 78986。`audit_v14.sh` 也仅监控同一 PID。**无通用 Agent 进程存活清单比对** |
| **数据≠实际路径** | ❌ **不通过** | 审计写入路径碎片化。`governance/audit.py` 写入指定 log_path，`health_snapshot.py` 写入 `.governance/health_snapshot.json`，`PulseWriter` 写入 `.governance/pulses/`。**无路径一致性校验** |
| **告警≠消费** | ❌ **不通过** | `alert_rules.py` 可生成告警但无消费追踪。`NotificationManager` 发送后返回 bool 但无送达确认。**无通知文件存活时长审计** |
| **恢复代码≠逻辑有效** | ❌ **不通过** | **`PulseWriter` 是典型的孤魂代码**：完整实现但生产路径零调用。`_update_pulse()` 被 docstring 承诺但不存在。`check_pulse_staleness()` 无人调度。自愈逻辑存在于 `life_state/health.py` 但无触发源 |

**四层鸿沟**: ❌ 4/4 不通过

---

## 6. 专项发现

### 6.1 审计系统碎片化（结构-运行鸿沟典型案例）

```
governance/audit.py — AuditLogger (HMAC/Ed25519, JSONL, chain_hash)
  └→ 被 governance/ 子模块使用
  
recursive/unified_audit.py — UnifiedAuditStore (AuditBus, 内存+JSONL)
  └→ 被 ~50 个 recursive/ 子模块导入

gaas/audit_service.py — GaaSAuditEntry (HMAC, JSONL)
  └→ 仅 gaas/ 子模块使用

eivl/merkle_auditor.py — AuditEvidence (Merkle Tree, 全内存)
  └→ 通过 AuditChainIntegrator 桥接 AuditLogger

integration/audit_logger.py — AuditLogger (MCP 版)
  └→ 开源 Sidecar 使用
```

**风险**: 审计系统层次多、路径散、格式杂，审计员检查任何一个子系统都只能看到局部。

### 6.2 Meta-Monitor 缺失（最大单点风险）

`meta-monitor` 在代码中有 3 处 docstring 引用，但 **从未实现**：
- `health_snapshot.py:4` — "The meta-monitor checks freshness..."
- `agent_health.py:140` — "The meta-monitor checks freshness..."
- `agent_health.py:17` — docstring 提及

**后果**: M0（最底层生存断言）完全依赖 meta-monitor。meta-monitor 不存在 → M0~M3 全部失效。

### 6.3 PulseWriter 是孤魂代码

`PulseWriter` 在 `agent_health.py` 中完整实现（99 行代码），包含：
- `write_pulse()` — 原子写入脉冲 JSON
- `is_alive()` — 本地存活检测
- `check_pulse_staleness()` — 全局陈旧率统计（静态方法）

但 **全仓库零调用**。grep 显示：
- 其他文件 import 的是 `AgentHealthMonitor`（负载追踪），**不是** `PulseWriter`
- 无 launchd/cron 调度 `check_pulse_staleness`

### 6.4 `.openclaw/` 目录不存在

手册要求 `.openclaw/notifications/` 用于通知文件存活审计。该目录从未创建。

### 6.5 现有审计脚本覆盖有限

| 脚本 | 范围 | 限制 |
|------|------|------|
| `audit_v14.sh` | 仅监控 PID 78986 的 v14 自治循环 | 硬编码 PID，非通用 |
| `watchdog_audit.py` | 每 5min 运行 `audit_v20.sh`（且 v20 不存在） | 引用不存在脚本 |
| `verify_audit_chain.py` | 验证审计链完整性 | 独立脚本，非持续运行 |

### 6.6 健康检查端点脆弱

| 端点 | 实现 | 问题 |
|------|------|------|
| GaaS `/health` | 静态返回 "healthy" | 不验证任何依赖 |
| Sidecar `/api/health` | 检查 collector 运行态 + buffer_size | 不验证审计系统健康 |

---

## 7. 等级评定

| 等级 | 元审计要求 | MAREF 当前状态 | 判定 |
|------|-----------|---------------|------|
| **Experimental** | M0 全部通过 | M0 BLOCKING 3/5 不通过 | ❌ |
| **Beta** | M0+M1 全部通过 | M1 BLOCKING 3/4 不通过 | ❌ |
| **GA** | M0~M3 全部通过 | M0~M3 均不通过 | ❌ |

**当前成熟度**: Pre-Experimental

---

## 8. 修复优先级

### P0 — 阻塞上线

| # | 修复项 | 涉及文件 | 估计工作量 | 依赖 |
|---|--------|---------|-----------|------|
| P0.1 | **实现 meta-monitor** — 5 个 M0 检查的调度器 | `scripts/meta_monitor.py`（新建） | 3d | — |
| P0.2 | **部署 pulse 调用链** — 让 Agent 实际调用 `PulseWriter.write_pulse()` | `agent_health.py`、Agent 运行时入口 | 2d | P0.1 |
| P0.3 | **统一审计路径** — 建立审计数据路径映射表 + 跨路径校验 | 各 audit 模块 | 3d | — |
| P0.4 | **实现通知文件存活审计** — 创建 `.openclaw/notifications/` + 文件年龄扫描 | `scripts/` | 1d | — |
| P0.5 | **增强 GaaS 健康检查** — 检查 DB/CB/HITL 依赖 | `gaas/api.py` | 0.5d | — |

### P1 — 需修复

| # | 修复项 | 估计工作量 |
|---|--------|-----------|
| P1.1 | 统一审计条目格式（逐步淘汰旧格式） | 5d |
| P1.2 | 实现告警去重和回路追踪 | 2d |
| P1.3 | EIVL Merkle 树持久化 | 2d |
| P1.4 | 告警消失检测（15 分钟无告警 → 触发"告警缺失"告警） | 1d |
| P1.5 | launchd plist → 进程实际运行状态比对脚本 | 1d |

### P2 — 建议优化

| # | 优化项 | 估计工作量 |
|---|--------|-----------|
| P2.1 | 清理 2 个弃用审计模块（`federated_audit.py`、`security_audit_chain.py`） | 1d |
| P2.2 | 移除 `watchdog_audit.py` 中对不存在的 `audit_v20.sh` 的引用 | 0.5d |
| P2.3 | 添加 Sidecar OTEL 可选的警告日志 | 0.5d |

---

## 9. 关键数据汇总

| 指标 | 值 |
|------|-----|
| 审计相关源文件数 | 32（含 2 弃用） |
| 健康检查端点数 | 2（GaaS + Sidecar） |
| launchd 配置数 | 5 |
| PulseWriter 生产调用数 | **0** |
| meta-monitor 实现 | **不存在** |
| .openclaw/ 目录 | **不存在** |
| 审计条目格式数 | 4 |
| 审计写入路径数 | 4+ |
| 告警回路追踪 | 未实现 |
| 四层鸿沟通过率 | **0/4** |

---

**审计员**: opencode (via MAREF Governance Audit)
**审计结论**: ❌ 未通过 — 降级到 Pre-Experimental，需完成 P0 修复后重新审计

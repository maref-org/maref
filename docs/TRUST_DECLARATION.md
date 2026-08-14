# TRUST DECLARATION — MAREF 开源部署信任声明（v1.0）

> **上位依据**: [MAREF 系统宪法 v1.5](docs/CONSTITUTION.md) · [INC-2026-08-13-001](docs/incidents/INC-2026-08-13-001-cost-burn-telemetry-blackout.md)（成本失控 + 遥测全面静默，P0 信任崩塌型事故）
> **目的**: 明确开源部署者可观测 / 不可观测边界，消除"开源 MAREF 无神经系统"的结构性不信任。
> **追溯审计**: `docs/audit-reports/cost-guard-validation-20260814.md`

---

## 0. 一句话承诺

> **MAREF 开源仓库承诺：部署者运行的是一个"有大脑且有神经"的治理系统——能看见自己、能拦得住问题、能验证健康；任何不可观测的部分，本声明明确划出边界并给出替代方案。**

---

## 1. 可观测能力（开源部署自带，无需闭源组件）

| # | 能力 | 命令/落点 | 事故中对治的根因 |
|---|------|-----------|------------------|
| 1 | **API 成本护栏执行** | `maref.cost_guard.CostGuard`（CALL/CTX/BUDGET 三层 + HMAC 审计写入） | 根因 #1（观测面错位）/ #5（护栏是补丁） |
| 2 | **成本事件审计链** | `~/.maref/audit/cost_events.ndjson` / `guard_blocks.ndjson`（HMAC 签名） | 根因 #1 |
| 3 | **M4 成本健康检查** | `python -m maref.observability.meta_monitor --single-run`（5 分钟内发现成本异常） | 根因 #1/#4 |
| 4 | **看门狗真实探测** | `check_audit_log_growth` 只检查真实事件，禁止自我续命（touch） | 根因 #3 |
| 5 | **审计链内容健康度** | `check_audit_noise`——24h 内只有 state_transition 判为噪音污染 | 根因 #2 |
| 6 | **部署自检** | `maref selfcheck`（七项检查：HMAC key / 审计事件 / 遥测 / ObsBridge / 看门狗 / proxy / 护栏阈值） | 根因 #6 |
| 7 | **本地遥测聚合** | `~/.maref/telemetry/events.db`（云端不可达时离线兜底，ObsPipeline） | 根因 #6 |
| 8 | **测试隔离** | 所有测试强制 `MAREF_AUDIT_PATH=/tmp/maref-test-audit`，生产审计零污染 | 根因 #2 |
| 9 | **HMAC key 统一分发** | `.maraf_hmac_key` 单一密钥源 + fail-closed 显式告警 | 根因 #4 |

---

## 2. 不可观测边界（开源部署默认关闭，需要部署者自行接入）

以下能力**不作为开源默认提供的运行时组件**，但都有可部署替代方案：

| # | 能力 | 闭源侧实现 | 开源替代方案 |
|---|------|-----------|--------------|
| 1 | **模型网关/路由**（unified_proxy） | 闭源 `~/.claude/scripts/unified_proxy.py`（含 API key） | 部署者可基于 `maref.cost_guard.CostGuard` 在自己的代理/网关接入三层护栏；密钥自行管理 |
| 2 | **云端遥测接收端**（telemetry.maref.org） | 闭源基础设施 | 默认本地 SQLite 聚合 `~/.maref/telemetry/events.db`；云端仅作可选增强 |
| 3 | **全域数据飞轮**（data-flywheel） | 闭源调度 + 闭源 infra | 提供脱敏部署包（含治理相位显式声明，无幽灵模块） |
| 4 | **看门狗系统调度**（launchd cron） | 闭源 plist 文件 | 开源提供 `deploy/` 模板（meta-monitor 逻辑本身已在 `src/maref/observability/` 开源） |

> **重要**：若部署者未接入上述任何替代方案，则系统依然是**可自检、可拦截成本、可审计**的
> （第 1 节能力全部自带）；只是无法享受云同步 / 自动调度等增强能力。

---

## 3. 部署者 5 分钟自检协议

```bash
# 1. 部署仓库
git clone https://github.com/maref-org/maref && cd maref
pip install -e ".[dev]"

# 2. 初始化密钥（禁止无密钥运行）
if [ ! -f ~/.maraf_hmac_key ]; then openssl rand -hex 32 > ~/.maraf_hmac_key; chmod 600 ~/.maraf_hmac_key; fi

# 3. 生成成本护栏策略
maref cost-policy            # 写入 ~/.maref/proxy_config.json（写审计链）

# 4. 全量自检
maref selfcheck              # 期望全绿；FAIL 项在输出详情里给出修复指令

# 5. 接入成本护栏（任选其一）
#    a) 自建代理调用 CostGuard（见 docs/runbook/rb-012-cost-guardrails.md「开源部署」节）
#    b) 启动本地遥测聚合器（ObsPipeline 自动落 SQLite）
```

**自检通过 ≠ 成本绝对安全**：护栏只对"已接入 CostGuard 的调用路径"生效。
未接入的 API 调用（直连第三方 SDK）不在护栏范围内——请部署者在接入审计中确认覆盖面。

---

## 4. 信任恢复承诺（源自事故教训）

1. **执行能力与观测能力同源落地**：任何"治理逻辑"若其执行体在闭源，开源侧必须同步提供可部署替代（本次将 `CostGuard` 带入开源即为此承诺的兑现）。
2. **禁止静默失效**：审计 key 缺失 / 遥测不可达 / 看门狗 stale，一律显式告警（notification + stderr），不允许无声降级。
3. **看门狗禁止自我续命**：健康检查只认真实事件，touch 自查为设计禁忌（G5 已修复并删除残留）。
4. **CI 禁止静默跳过护栏测试**：成本护栏测试必须真实执行（`tests/security/test_cost_guard_opensource.py` 零闭源依赖）。
5. **失效最快 5 分钟可见**：M4 成本异常 / 审计断裂，在 meta_monitor 轮询周期内暴露。

---

## 5. 版本与追溯

| 字段 | 值 |
|------|-----|
| 版本 | v1.0（2026-08-14） |
| 触发事故 | INC-2026-08-13-001（成本失控 + 遥测全面静默） |
| 追溯审计 | `docs/audit-reports/cost-burn-root-cause-20260813.md` · `docs/audit-reports/cost-guard-validation-20260814.md` |
| 关联计划 | `docs/plans/2026-08-13-governance-reinforcement-v0.54.md` |

---

> **签名区（维护者）**: 本声明须经维护者审核确认后发布到公开仓库根目录。
> 审核日期: 2026-08-XX
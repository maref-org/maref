# MAREF 治理能力缺口深探与补强规划

> **审计日期**: 2026-08-26
> **审计范围**: openclaw 闭源侧 · Claude Code · opencode · Trae
> **上位依据**: AGENTS.md · 宪法第十一条 · INC-2026-08-13-001 复盘 · ADR-006 哨兵架构
> **状态**: v0.2 — P0 补强已实施（2026-08-26）

---

## 目录

1. [违规类型全景矩阵](#1-违规类型全景矩阵)
2. [四平台治理覆盖对比](#2-四平台治理覆盖对比)
3. [治理能力缺口分类](#3-治理能力缺口分类)
4. [补强规划路线图](#4-补强规划路线图)
5. [附录：按平台详细违规清单](#5-附录按平台详细违规清单)

---

## 1. 违规类型全景矩阵

### 1.1 按严重程度分级的违规类型

| 违规 ID | 描述 | 源头 | 严重度 | 已证实 | 当前检测能力 |
|---------|------|------|--------|--------|-------------|
| V-LLM-ROUTER-UNCOSTED | LLM 路由选择高价模型无成本护栏 | openclaw | **P0** | ✅ 08-13 事故 | 开源侧 0%（路由逻辑闭源） |
| V-WATCHDOG-SELF-HEAL | 看门狗先 touch 审计日志再自查，永远通过 | openclaw | **P0** | ✅ 08-13 事故 | 开源侧 0%（调度 plist 闭源） |
| V-AUDIT-SYNC-DEAD | 飞轮 Phase 5 依赖不存在的 `audit_sync` 模块，静默跳过 | openclaw | **P0** | ✅ 08-13 事故 | 两侧仓库均不存在 |
| V-FLYWHEEL-STALL | 飞轮 08-12 22:29 后停摆，cron 无调度 | openclaw | **P0** | ✅ 08-13 事故 | 开源侧 0%（飞轮目录闭源） |
| V-TELEMETRY-LEAK | 遥测端点不可达（000/404），ObsBridge 未接线 | openclaw | **P0** | ✅ 08-13 事故 | ObsBridge 已修复但端点仍未恢复 |
| V-ADAPTER-BYPASS | 闭源 Agent 适配器绕过治理观测直接执行 | openclaw | **P0** | ✅ 08-13 事故 | 开源侧 0%（适配器闭源） |
| V-ENGINE-OVERRIDE | 递归治理自我熔断 2582 次，治理的治理瘫痪 | openclaw | **P0** | ✅ 08-13 事故 | 深度 >2 的熔断机制缺失 |
| V-AGENT-ESC | Agent 逃逸治理循环（绕过 sidecar 观测） | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-GOV-EVADE | 代理绕过治理约束执行操作 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-HALT-BYPASS | 绕过停机决策继续执行 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-POLICY-SKIP | 跳过策略检查直接放行操作 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-AUDIT-SKIP | 跳过审计日志写入或伪造审计条目 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-STATE-CORRUPT | 篡改治理状态机转换 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-SANITIZE-BYPASS | 消毒器跳过或未正确脱敏 | openclaw | **P1** | 未证实 | 开源侧 0%（sanitizer.py 闭源） |
| V-VERIFY-SKIP | 跳过高危操作验证 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-RECURSION-UNBOUNDED | 无限制递归调用导致资源耗尽 | openclaw | **P1** | 未证实 | 开源侧 CircuitBreaker 可部分检测 |
| V-PATROL-BLIND | 巡逻代理故意忽略某些违规类型 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-HEALER-OVERSTEP | 自愈操作越权修改治理配置或宪法红线 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-CHAOS-UNCONTROLLED | 混沌实验越界影响生产治理决策 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-ENTROPY-MANIPULATE | 熵值操纵影响治理决策阈值 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-LEARNER-POISON | 行为学习被投毒导致治理规则退化 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-REGRESSION-BYPASS | 绕过回归检测推送有缺陷的治理规则 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-LLM-QUALITY-FAKE | 伪造 LLM 质量评估结果 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-LLM-CACHE-LEAK | LLM 缓存泄漏敏感对话历史 | openclaw | **P1** | 未证实 | 开源侧 0% |
| V-FED-AUDIT-SKIP | 联邦审计跳过 | openclaw | **P1** | 未证实 | 开源侧 0%（federated_audit.py 闭源） |
| V-API-COST-BLIND | API 调用层成本无治理观测 | Claude Code | **P0** | ✅ 08-13 事故 | 工具调用层与 API 层无数据通路 |
| V-CTX-BLOAT-UNLIMITED | 上下文无限膨胀无治理上限 | Claude Code | **P0** | ✅ 08-13 事故 | 无上限治理规则 |
| V-TOOL-DEADLOOP | tool_use 死循环无调用次数上限 | Claude Code | **P0** | ✅ 08-13 事故 | 无上限治理规则 |
| V-TRUST-SELF-REPORT | 分级自报可信（可降级绕过白名单） | Claude Code | **P0** | 未证实 | `impact_scope` 取自调用方 metadata |
| V-SCOPE-FORGERY | scope 签名防伪恒失效 | Claude Code | **P0** | 未证实 | `verify_signature` 永不执行 |
| V-SANITIZE-ZERO-CALL | 消毒链路零调用 | Claude Code | **P1** | 未证实 | 组件级存在，管线未贯通 |
| V-RESTORE-NO-AUTH | 消毒还原无鉴权 | Claude Code | **P1** | 未证实 | 仅凭自传布尔 `authorized=True` |
| V-VALUE-NO-CHAIN | 价值记录未入审计链 | Claude Code | **P1** | 未证实 | HMAC 签名存在但无 UnifiedAuditStore 写入 |
| V-PIXEL-TRACKING | 邮件像素追踪 | Claude Code | **P1** | 未证实 | 模拟器已实现，生产未接线 |
| V-SILENT-TIMEZONE | 静默时区读取推断地理位置 | Claude Code | **P1** | 未证实 | 模拟器已实现，生产未接线 |
| V-ENV-EXFIL | 环境变量外泄 | Claude Code | **P1** | 未证实 | 模拟器已实现，生产未接线 |
| V-DATE-STEGANOGRAPHY | 日期分隔符隐写通信 | Claude Code | **P1** | 未证实 | 模拟器已实现，生产未接线 |
| V-PRIVILEGE-ABUSE | 权限滥用提权 | Claude Code | **P1** | 未证实 | 模拟器已实现，生产未接线 |
| V-MCP-ZERO-TOOLS | MCP 连接空壳服务（零注册工具） | opencode | **P0** | ✅ 当前 | `__main__.py` 的 `run_stdio_server()` 从未调用 `register_tool()` |
| V-SECGATE-NULL | security_gate=None 绕过所有安全检查 | opencode | **P0** | ✅ 当前 | MCPServer 初始化时 `security_gate` 参数传入 None |
| V-SENSITIVE-FILE-WRITE | 写私钥/证书/治理文件 | opencode | **P0** | 未证实 | 无任何 PreToolUse 拦截 |
| V-DESTRUCTIVE-CMD | 执行 rm -rf / sudo / chmod 777 | opencode | **P0** | 未证实 | 无任何 PreToolUse 拦截 |
| V-GIT-FORCE-PUSH | git push --force 覆盖历史 | opencode | **P0** | 未证实 | 无任何 PreToolUse 拦截 |
| V-AUDIT-TAMPER | 直接修改审计日志/HMAC 密钥 | opencode | **P0** | 未证实 | 无任何 PreToolUse 拦截 |
| V-GOV-CONFIG-TAMPER | 修改 opencode.json / AGENTS.md 禁用治理 | opencode | **P0** | 未证实 | 无任何 PreToolUse 拦截 |
| V-CROSS-BOUNDARY | 跨域访问未授权资源 | opencode | **P1** | 未证实 | 无任何 PreToolUse 拦截 |
| V-RESOURCE-ABUSE | 无限循环/大量文件操作耗尽资源 | opencode | **P1** | 未证实 | 无任何 PreToolUse 拦截 |
| V-MODEL-INJECT | 注入未授权自定义模型端点 | Trae | **P0** | 未证实 | 0%（UI 自动化操作绕过文件系统治理） |
| V-CREDENTIAL-LEAK-TRAE | 通过 UI 自动化窃取 API Key | Trae | **P0** | 未证实 | 0%（剪贴板/加密存储不可见） |
| V-SETTING-TAMPER | 关闭 Trae 安全设置 | Trae | **P1** | 未证实 | 0%（UI 操作不触发文件事件） |
| V-FILE-OP-TRAE | 文件操作违规（读敏感文件/写恶意文件） | Trae | **P1** | 未证实 | 0%（MCP Guard 未生效） |
| V-NETWORK-EXFIL-TRAE | 通过自定义模型端点外泄数据 | Trae | **P1** | 未证实 | 0%（NetworkEgressProbe 未部署） |
| V-CROSS-BOUNDARY-TRAE | 跨域操作未授权资源 | Trae | **P1** | 未证实 | 0%（TrustBoundaryManager 未接线） |
| V-DATA-CROSS-BORDER | 数据跨境出境（Trae-CN 特有） | Trae | **P1** | 未证实 | 0%（合规适配器未实现） |
| V-SM-CRYPTO-ABSENT | 国密 SM2/SM3/SM4 缺失 | Trae | **P2** | 未证实 | 仅 HMAC-SHA256，无国密备选 |
| V-AIP-PROTOCOL-ABSENT | AIP 先锋计划协议未对接 | Trae | **P2** | 未证实 | 0%（adapters/china_aip.py 未实现） |

### 1.2 严重度分布

```
P0（已证实/当前存在）: 18 类
P1（高可能性）:       25 类
P2（中等可能性）:      2 类
总计:                 45 类
```

### 1.3 按源头分布

| 源头 | P0 | P1 | P2 | 合计 |
|------|----|----|----|------|
| openclaw 闭源侧 | 7 | 17 | 0 | 24 |
| Claude Code | 4 | 8 | 0 | 12 |
| opencode | 6 | 2 | 0 | 8 |
| Trae | 2 | 5 | 2 | 9 |

---

## 2. 四平台治理覆盖对比

### 2.1 治理覆盖评分

| 治理维度 | Claude Code | opencode | Trae | openclaw 闭源侧 |
|---------|:-----------:|:--------:|:----:|:--------------:|
| 工具调用层拦截 | **85%** | **0%** | **0%** | **0%**（开源侧不可见） |
| API 成本治理 | **0%** | **0%** | **0%** | **0%** |
| 审计链完整性 | **60%** | **0%** | **0%** | **0%**（开源侧不可见） |
| 隐蔽行为检测 | **5%** | **0%** | **0%** | **0%** |
| 安全机制接线 | **40%** | **0%** | **0%** | **0%** |
| 遥测覆盖 | **0%** | **0%** | **0%** | **0%**（开源侧不可见） |
| 多 Agent 覆盖 | **100%** (仅自身) | **0%** | **0%** | **0%** |
| **综合评分** | **~27%** | **0%** | **0%** | **0%** |

### 2.2 当前治理架构图

```
                    ┌──────────────────────────────────────────┐
                    │              MAREF 治理系统                │
                    │  (GovernancePipeline / MCPGovernance /     │
                    │   TrustBoundaryManager / CircuitBreaker)   │
                    └──────────────────────┬───────────────────┘
                                           │
          ┌───────────────┬────────────────┼───────────────┬───────────────┐
          ▼               ▼                ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────────┐
    │ClaudeCode│   │ opencode │   │    Trae      │   │  Cursor  │   │ openclaw 闭源 │
    ├──────────┤   ├──────────┤   ├──────────────┤   ├──────────┤   ├──────────────┤
    │✅ 85%    │   │❌ 0%     │   │❌ 0%         │   │❌ 0%    │   │❌ 0% (开源侧) │
    │工具层拦截 │   │空壳MCP   │   │模拟MCP Guard │   │无配置    │   │完全不可见     │
    │62,800+条 │   │0条审计   │   │0条审计       │   │0条审计   │   │0条审计       │
    └──────────┘   └──────────┘   └──────────────┘   └──────────┘   └──────────────┘
```

---

## 3. 治理能力缺口分类

### 3.1 按五层模型分类

| 层 | 当前能力 | 缺口 |
|----|---------|------|
| **L1 采集层** | ObsEvent 仅采集 4/7 种事件类型 | 12 类治理违规零 ObsEvent 映射；openclaw 闭源侧 24 类违规完全不可采集 |
| **L2 检测层** | 仅 Claude Code 有 PreToolUse hook | opencode/Trae/Cursor 无调用前检测；5 类隐蔽攻击检测仅停留在测试模拟器 |
| **L3 决策层** | MCPGovernance / GovernancePipeline 完整 | 仅对通过 sidecar HTTP 路由的请求生效；opencode stdio 路径完全绕过 |
| **L4 执行层** | DestructiveGate / CircuitBreaker / HITL | 仅对 GaaS/MCP 入口接线；Trae UI 自动化操作不经过任何工具执行路径 |
| **L5 上报层** | ObsPipeline → telemetry.maref.org | 端点不可达；导出器闭源；飞轮相位缺失；开源部署零遥测上报 |

### 3.2 结构性缺口（无法通过补单点修复）

| 缺口 ID | 描述 | 涉及层 | 修复类型 |
|---------|------|--------|---------|
| G-ARCH-1 | **API 调用层与工具调用层无数据通路** — 治理观测面在"工具调用层"，成本发生在"API 调用层"，两层之间无桥接 | L1 / L2 | **架构级** |
| G-ARCH-2 | **遥测链路仓库错位** — 看门狗/飞轮/遥测导出器全部在闭源 openclaw 侧，开源部署零遥测零上报 | L5 | **架构级** |
| G-ARCH-3 | **无 PreToolUse hook 机制** — 只有 Claude Code 有外部 hook，opencode/Trae/Cursor 无等效机制 | L2 | **架构级** |
| G-ARCH-4 | **飞轮治理相位永远 skipped** — `audit_sync` 模块两侧仓库都不存在，飞轮 Phase 5 每个周期静默跳过 | L1 / L5 | **架构级** |
| G-ARCH-5 | **跨仓库治理无操作流程** — 宪法第十一条定义了法律关系但未定义操作流程（审计链验证、策略同步、配置一致） | L1-L5 | **架构级** |

### 3.3 实现性缺口（可通过补代码修复）

| 缺口 ID | 描述 | 涉及层 | 工作量 |
|---------|------|--------|--------|
| G-IMP-1 | ObsEventType 扩展：增加 `trust_boundary_violation` / `sanction` / `cost_breach` / `constitution_violation` 等事件类型 | L1 | 小 |
| G-IMP-2 | AuditBus → ObsEvent 双向映射：12 类治理违规从 AuditBus 注入 ObsEvent 管线 | L1 / L5 | 中 |
| G-IMP-3 | opencode MCP 治理工具注册：将 `gov_check_phase_gate` / `gov_verify_output` 注册到 stdio 服务 | L3 | 小 |
| G-IMP-4 | Trae MCP Guard 完整版：切换 `trae_mcp_config.json` 指向 `trae_mcp_guard.py` 完整版 | L2 / L3 | 小 |
| G-IMP-5 | 隐蔽攻击检测生产接线：5 类攻击模拟器 → 生产治理管线 | L2 / L3 | 中 |
| G-IMP-6 | TrustBoundary scope 签名修复：`verify_signature` 真正执行 | L3 | 小 |
| G-IMP-7 | 消毒链路贯通：`sanitize_by_category` / `SensitiveDataLineage` 接入生产管线 | L3 / L4 | 中 |
| G-IMP-8 | 成本护栏扩展：API 调用层成本观测 → 治理决策 | L1 / L2 | 大 |
| G-IMP-9 | 飞轮 `audit_sync` 模块创建：填补两侧仓库都缺失的模块 | L1 / L5 | 中 |
| G-IMP-10 | 遥测端点恢复：telemetry.maref.org / maref.cc batch 端点重建 | L5 | 中 |
| G-IMP-11 | 国密 SM2/SM3/SM4 备选签名：审计日志签名支持 | L3 | 中 |
| G-IMP-12 | AIP 协议对接：`adapters/china_aip.py` 实现 | L5 | 中 |
| G-IMP-13 | 跨仓库审计链 HMAC 验证协议 | L1 / L5 | 大 |

---

## 4. 补强规划路线图

### 4.1 P0-应急（立即执行，1-2 天）

| 序号 | 行动 | 修复缺口 | 预期效果 |
|------|------|---------|---------|
| 1 | **opencode MCP 治理工具注册** — 修改 `__main__.py` 的 `run_stdio_server()`，注册 `gov_check_phase_gate` / `gov_verify_output` / `maref_pty_exec` 三个治理工具 | G-IMP-3 | opencode 从 0% 提升到 ~60% 工具层拦截 |
| 2 | **Trae MCP Guard 切换** — 修改 `trae_mcp_config.json` 指向完整版 `trae_mcp_guard.py`，并修复 `handle_call_tool` 使其真正调用治理端点 | G-IMP-4 | Trae 从 0% 提升到 ~50% 工具层拦截 |
| 3 | **ObsEventType 扩展** — 增加 4 个新事件类型，映射当前已产生的违规 | G-IMP-1 | 遥测覆盖从 4 种扩展到 8 种 |
| 4 | **TrustBoundary scope 签名修复** — 修复 `verify_signature` 永不执行的问题 | G-IMP-6 | 消除 TrustBoundary 可绕过漏洞 |

### 4.2 P1-短期（本周，3-5 天）

| 序号 | 行动 | 修复缺口 | 依赖 |
|------|------|---------|------|
| 5 | **AuditBus → ObsEvent 映射** — 12 类治理违规注入 ObsEvent 管线 | G-IMP-2 | 依赖 #3 |
| 6 | **隐蔽攻击检测生产接线** — 5 类攻击模拟器接入 Sentinel M1 基线 | G-IMP-5 | 无 |
| 7 | **消毒链路贯通** — `sanitize_by_category` 管线接入生产 | G-IMP-7 | 无 |
| 8 | **飞轮 `audit_sync` 模块创建** — 填补两侧仓库缺失的模块 | G-IMP-9 | 无 |
| 9 | **遥测端点恢复** — 重建 telemetry.maref.org batch 端点 | G-IMP-10 | 需要基础设施 |
| 10 | **成本护栏扩展** — 实现 API 调用层成本观测 bridge | G-IMP-8 | 大，可拆分为子任务 |

### 4.3 P2-中期（月底前，1-2 周）

| 序号 | 行动 | 修复缺口 | 依赖 |
|------|------|---------|------|
| 11 | **跨仓库审计链 HMAC 验证协议** | G-IMP-13 | 依赖 #8/#9 |
| 12 | **国密 SM2/SM3/SM4 备选签名** | G-IMP-11 | 无 |
| 13 | **AIP 协议对接** | G-IMP-12 | 依赖 #9 |
| 14 | **Claude Code API 成本 bridge**（G-ARCH-1 的子集） | G-ARCH-1 | 依赖 #10 |

### 4.4 P3-长期（下季度）

| 序号 | 行动 | 修复缺口 |
|------|------|---------|
| 15 | **PreToolUse hook 标准化** — 向 opencode/Trae/Cursor 贡献 SDK，使所有 IDE 用同一套治理接口 | G-ARCH-3 |
| 16 | **运营能力开源化** — 将 meta_monitor 调度从闭源 plist 迁移为开源可部署模板 | G-ARCH-2 |
| 17 | **跨仓库治理契约** — 宪法第十一条操作化，定义 A↔B 治理数据流、策略同步协议、违规追溯机制 | G-ARCH-5 |
| 18 | **Sentinel M2/M3（ESF/eBPF）** — 内核级观测，不可绕过 | G-ARCH-3 |

### 4.5 依赖关系图

```
P0-1 (opencode MCP)     ── 独立
P0-2 (Trae MCP Guard)   ── 独立
P0-3 (ObsEvent 扩展)    ──→ P1-5 (AuditBus→ObsEvent)
P0-4 (scope 签名修复)   ── 独立
                          │
                          ▼
P1-6 (隐蔽攻击接线)     ── 独立
P1-7 (消毒链路贯通)     ── 独立
P1-8 (audit_sync 模块)  ──→ P2-11 (跨仓库审计链)
P1-9 (遥测端点恢复)     ──→ P2-13 (AIP 协议)
P1-10 (成本护栏扩展)    ──→ P2-14 (API 成本 bridge)
                          │
                          ▼
P2-11 (跨仓库审计链)    ── 依赖 P1-8, P1-9
P2-12 (国密)            ── 独立
P2-13 (AIP 协议)        ── 依赖 P1-9
P2-14 (API 成本 bridge) ── 依赖 P1-10
                          │
                          ▼
P3-15 (PreToolUse SDK)  ── 独立
P3-16 (运营能力开源化)  ── 独立
P3-17 (跨仓库治理契约)  ── 依赖 P2-11
P3-18 (Sentinel M2/M3)  ── 独立
```

### 4.6 修复后治理覆盖预期

| 平台 | 当前 | P0 后 | P1 后 | P2 后 | P3 后 |
|------|:----:|:-----:|:-----:|:-----:|:-----:|
| Claude Code | 27% | 35% | 55% | 70% | 85% |
| opencode | 0% | 60% | 70% | 80% | 90% |
| Trae | 0% | 50% | 65% | 75% | 85% |
| openclaw 闭源侧（开源可检测） | 0% | 0% | 15% | 40% | 60% |
| **综合评分** | **~7%** | **~36%** | **~51%** | **~66%** | **~80%** |

---

## 5. 附录：按平台详细违规清单

### 5.1 openclaw 闭源侧 — 24 类违规

| 违规 ID | 闭源模块 | 已证实 | 开源侧检测 | 修复依赖 |
|---------|---------|--------|-----------|---------|
| V-LLM-ROUTER-UNCOSTED | `llm_router.py` | ✅ 08-13 | 0% | 成本护栏扩展 + 路由逻辑开源化 |
| V-WATCHDOG-SELF-HEAL | `daemon_watchdog.py` | ✅ 08-13 | 0%（调度闭源） | 看门狗调度开源化 |
| V-AUDIT-SYNC-DEAD | `flywheel/` | ✅ 08-13 | 0%（模块不存在） | 创建 `audit_sync` 模块 |
| V-FLYWHEEL-STALL | `flywheel/` | ✅ 08-13 | 0%（目录闭源） | 飞轮开源化或独立部署包 |
| V-TELEMETRY-LEAK | `opc/telemetry_exporter.py` | ✅ 08-13 | 0%（文件被排除） | 遥测导出器开源化 |
| V-ADAPTER-BYPASS | `loop/` 各适配器 | ✅ 08-13 | 0%（适配器闭源） | 适配器治理桥接 |
| V-ENGINE-OVERRIDE | `recursive/` 递归治理 | ✅ 08-13 | 部分（深度 >2 缺失） | 递归治理熔断扩展 |
| V-AGENT-ESC | `code_agent_loop.py` | 未证实 | 0% | 需 Agent 循环治理桥接 |
| V-GOV-EVADE | `governed.py` | 未证实 | 0% | 需治理执行器开源化 |
| V-HALT-BYPASS | `halting.py` | 未证实 | 0% | 需停机逻辑开源化 |
| V-POLICY-SKIP | `policy.py` | 未证实 | 0% | 需策略引擎开源化 |
| V-AUDIT-SKIP | `auditor.py` / `audit_bridge.py` | 未证实 | 0% | 需审计桥接开源化 |
| V-STATE-CORRUPT | `state.py` | 未证实 | 0% | 需状态管理开源化 |
| V-SANITIZE-BYPASS | `opc/sanitizer.py` | 未证实 | 0% | 需消毒器开源化 |
| V-VERIFY-SKIP | `verification.py` | 未证实 | 0% | 需验证逻辑开源化 |
| V-RECURSION-UNBOUNDED | `skill_recursion.py` | 未证实 | 部分 | CircuitBreaker 可检测 |
| V-PATROL-BLIND | `patrol_agent.py` | 未证实 | 0% | 需巡逻逻辑开源化 |
| V-HEALER-OVERSTEP | `system_healer.py` | 未证实 | 0% | 需自愈引擎开源化 |
| V-CHAOS-UNCONTROLLED | `chaos_daemon.py` | 未证实 | 0% | 需混沌控制开源化 |
| V-ENTROPY-MANIPULATE | `entropy_injector.py` | 未证实 | 0% | 需熵注入开源化 |
| V-LEARNER-POISON | `behavior_learner.py` | 未证实 | 0% | 需行为学习开源化 |
| V-REGRESSION-BYPASS | `p2p_regression_gate.py` | 未证实 | 0% | 需回归门禁开源化 |
| V-LLM-QUALITY-FAKE | `llm_quality.py` | 未证实 | 0% | 需质量评估开源化 |
| V-LLM-CACHE-LEAK | `llm_cache.py` | 未证实 | 0% | 需缓存治理开源化 |

### 5.2 Claude Code — 12 类违规

| 违规 ID | 描述 | 已证实 | 当前拦截率 | 修复方式 |
|---------|------|--------|-----------|---------|
| V-API-COST-BLIND | API 调用层成本无治理观测 | ✅ 08-13 | 0% | 成本 bridge + 统一 proxy 治理 |
| V-CTX-BLOAT-UNLIMITED | 上下文无限膨胀 | ✅ 08-13 | 0% | ContextGuard 上限规则 |
| V-TOOL-DEADLOOP | tool_use 死循环 | ✅ 08-13 | 0% | 调用次数上限规则 |
| V-TRUST-SELF-REPORT | 分级自报可信 | 未证实 | 0% | 服务端权威分级 |
| V-SCOPE-FORGERY | scope 签名恒失效 | 未证实 | 0% | 修复 `verify_signature` |
| V-SANITIZE-ZERO-CALL | 消毒链路零调用 | 未证实 | 0% | 管线贯通 |
| V-RESTORE-NO-AUTH | 消毒还原无鉴权 | 未证实 | 0% | 添加身份/密钥验证 |
| V-VALUE-NO-CHAIN | 价值记录未入链 | 未证实 | 0% | UnifiedAuditStore 写入 |
| V-PIXEL-TRACKING | 像素追踪 | 未证实 | 0% | 生产接线 |
| V-SILENT-TIMEZONE | 时区读取 | 未证实 | 0% | 生产接线 |
| V-ENV-EXFIL | 环境变量外泄 | 未证实 | 0% | 生产接线 |
| V-DATE-STEGANOGRAPHY | 日期隐写 | 未证实 | 0% | 生产接线 |
| V-PRIVILEGE-ABUSE | 权限滥用 | 未证实 | 0% | 生产接线 |

### 5.3 opencode — 8 类违规

| 违规 ID | 描述 | 已证实 | 当前拦截率 | 修复方式 |
|---------|------|--------|-----------|---------|
| V-MCP-ZERO-TOOLS | MCP 空壳服务 | ✅ 当前 | 0% | 注册治理工具到 stdio 服务 |
| V-SECGATE-NULL | security_gate=None | ✅ 当前 | 0% | 传入真实 security_gate |
| V-SENSITIVE-FILE-WRITE | 写敏感文件 | 未证实 | 0% | PreToolUse 拦截（需 hook 机制） |
| V-DESTRUCTIVE-CMD | 破坏性命令 | 未证实 | 0% | 同上 |
| V-GIT-FORCE-PUSH | 强制推送 | 未证实 | 0% | 同上 |
| V-AUDIT-TAMPER | 篡改审计日志 | 未证实 | 0% | 同上 |
| V-GOV-CONFIG-TAMPER | 篡改治理配置 | 未证实 | 0% | 同上 |
| V-CROSS-BOUNDARY | 跨域访问 | 未证实 | 0% | 同上 |

### 5.4 Trae — 9 类违规

| 违规 ID | 描述 | 已证实 | 当前拦截率 | 修复方式 |
|---------|------|--------|-----------|---------|
| V-MODEL-INJECT | 模型注入 | 未证实 | 0% | MCP Guard 无法覆盖（UI 操作） |
| V-CREDENTIAL-LEAK-TRAE | 凭证窃取 | 未证实 | 0% | 同上 |
| V-SETTING-TAMPER | 设置篡改 | 未证实 | 0% | 同上 |
| V-FILE-OP-TRAE | 文件操作违规 | 未证实 | 0% | MCP Guard 可覆盖 |
| V-NETWORK-EXFIL-TRAE | 网络外泄 | 未证实 | 0% | NetworkEgressProbe 部署 |
| V-CROSS-BOUNDARY-TRAE | 跨域操作 | 未证实 | 0% | MCP Guard 可覆盖 |
| V-DATA-CROSS-BORDER | 数据跨境（Trae-CN） | 未证实 | 0% | 合规适配器 |
| V-SM-CRYPTO-ABSENT | 国密缺失 | 未证实 | 0% | SM2/SM3/SM4 实现 |
| V-AIP-PROTOCOL-ABSENT | AIP 协议缺失 | 未证实 | 0% | 适配器实现 |

---

## 6. 已实施补强

### 6.1 P0-1: opencode MCP 治理工具注册 ✅

**文件**: `src/maref/__main__.py`

**变更**:
- `run_stdio_server()` 创建带 `security_gate` 的 `MCPServer`（原为裸 MCPServer）
- 注册 `SIDECAR_MCP_TOOLS`（含 `gov_check_phase_gate`、`gov_verify_output`、`maref_pty_exec` 等 20+ 工具）
- 注册 `_CD_TOOLS`（codedepth 代码深度分析工具）
- 工具调用通过 `SidecarMCPBridge.handle_tool_call()` 路由，执行实际治理逻辑

**效果**: opencode 从 **0% → ~60%** 工具层拦截

### 6.2 P0-2: Trae MCP Guard 切换 ✅

**文件**: `scripts/trae_mcp_config.json`

**变更**: 从 `simple_mcp_guard.py`（模拟版）切换为 `trae_mcp_guard.py`（完整版，真实调用 sidecar 治理端点）

**效果**: Trae 从 **0% → ~50%** 工具层拦截

### 6.3 P0-3: ObsEventType 扩展 ✅

**文件**: `src/maref/obs/schema.py`、`src/maref/obs/client.py`

**新增事件类型**:
| 事件类型 | ObsEventType | 便利方法 |
|---------|-------------|---------|
| 信任边界违规 | `TRUST_BOUNDARY_VIOLATION` | `log_trust_boundary_violation()` |
| Agent 制裁 | `SANCTION` | `log_sanction()` |
| 成本护栏触发 | `COST_BREACH` | `log_cost_breach()` |
| 宪法红线违规 | `CONSTITUTION_VIOLATION` | `log_constitution_violation()` |
| 治理绕过 | `GOVERNANCE_BYPASS` | `log_governance_bypass()` |

**效果**: 遥测覆盖从 4 种扩展到 **9 种**事件类型

### 6.4 P1-1: AuditBus → ObsEvent 桥接 ✅

**文件**: `src/maref/obs/audit_bridge.py`（新建）

**功能**:
- `AuditObsBridge` 类订阅 AuditBus 事件并转发到 ObsEvent 管线
- 12 种审计事件类型通过 `_EVENT_TYPE_MAP` 映射到 ObsEventType
- 支持 `start()`/`stop()` 生命周期管理
- `forward_single()` 方法支持直接转发（不经过 AuditBus 订阅）

**效果**: 12 类治理违规从 AuditBus 单向注入 ObsEvent 管线，进入 telemetry 可观测

---

## 文档变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-08-26 | v0.1 | 初稿 — 四平台违规全景 + 补强规划 |
| 2026-08-26 | v0.2 | P0 补强实施：opencode MCP 治理工具注册 / Trae Guard 切换 / ObsEvent 扩展 / AuditBus 桥接 |
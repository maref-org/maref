# MAREF 治理缺口与突破口审计报告

> 审计日期: 2026-07-29 | 版本: v0.38.0-dev (Ed25519 迁移阶段)
> 方法: 代码审计 + 测试覆盖率分析 + TLA+ 规约交叉验证 + 架构逃生口扫描
> 范围: `src/maref/governance/` `src/maref/security/` `src/maref/recursive/`
>       `src/sidecar/` `src/maref_lite/` `gui/` `src/formal/` `tests/`

---

## 摘要

核心引擎层（状态机、审计链、断路器、信任边界）成熟度较高：TLA+ 验证 18+ 不变量、220+ L2 测试、34 态 Gray Code FSM。但**边缘层存在系统性治理强制缺失**，形成"核心坚实、外围透风"格局。

**风险量化**: CRITICAL 缺口 2 项 / HIGH 4 项 / MEDIUM 6 项 / LOW 4 项

---

## 一、架构层级缺口

### 1.1 34 态联合 FSM 形式化验证缺失

| 模型 | 状态 | 状态空间 | 风险 |
|------|------|---------|------|
| 10 态治理 FSM `state_machine.py` | ✅ TLA+ Model Checked | 156 states | — |
| 24 态 Agent FSM `agent_24_state_machine.py` | ❌ 无 TLA+ 模型 | 24 states | 跨层死锁未检测 |
| 34 态联合 `governance/trust_bridge.py` 桥接 | ❌ 未建模 | >10¹⁰ | 桥接状态转换安全性未证明 |

**证据**: `src/formal/MarefLite.tla` 仅覆盖 10 态治理 FSM；`agent_24_state_machine.py:322` 定义了完整的 24 态 Gray Code 但无对应 `.tla`。

**突破口**: 34-state 对称归约（利用 Gray Code Hamming distance=1 的置换对称性）可将状态空间降至可枚举范围，是 v0.42 TLAPS 路线图的第一步。

### 1.2 Python 运行时层宪法红线穿透风险

`rule_freeze_zone.py` 实现模块级写入保护（基于 `__file__` 路径匹配），但 Python 对象属性在运行时无保护:

```python
# rule_freeze_zone.py — 模块级保护
_RULE_FREEZE_ZONE = {"rl_table", "safety_gate_params", "core_components"}
# 但以下直接在运行时绕过:
meta_cb._hard_limits = {"max_depth": 999}  # 无防护
```

**根源**: Python 没有真正的私有属性/内存保护。`MetaCircuitBreaker` (`meta_governance.py:241`) 的硬限制通过普通属性赋值即可绕过。

**突破口**: 引入 `__slots__` + 属性描述符 + 运行时完整性校验（类似 `IntegrityBaseline` 对关键对象的哈希检查）。

### 1.3 宪法红线测试覆盖不均

| 红线 | 实现位置 | TLA+ | 单元测试 | 集成测试 | 红蓝对抗 |
|------|---------|------|---------|---------|---------|
| RL-001 红线不可修改 | `meta_agent_closure.py:45` | ✅ | ✅ | ✅ | ✅ 15/15 |
| RL-002 安全门不可绕过 | `safety_gate_v2.py` | ✅ | ✅ | ⚠️ | ✅ 15/15 |
| RL-003 审计追踪完整 | `audit.py:571` | ✅ | ✅ | ✅ | N/A |
| RL-004 克隆需审查 | `constitution_guard.py:589` | ✅ | ❌ | ❌ | ❌ |
| RL-005 权重不可单方改 | `cross_instance.py` | ✅ | ❌ | ❌ | ❌ |

**RL-004/RL-005 的代码级测试完全空白**。TLA+ 验证了 156 states 下的不变量保持，但 Python 实现层无对应测试。

---

## 二、运行时治理强制缺口

### 2.1 [CRITICAL] REST API 零认证 —— 严重性: 9.5/10

**`src/sidecar/server.py` 中全部端点无认证/授权**:

```python
# server.py 关键行
app.add_middleware(CORSMiddleware, allow_origins=["*"])  # 全源开放
# 所有路由无 @requires_auth / @security_critical 装饰
```

| 敏感端点 | 方法 | 行号 | 攻击面 |
|---------|------|------|--------|
| `POST /api/v1/hitl/{id}/approve` | POST | server.py:612 | 伪造人工审批通过 |
| `POST /api/v1/hitl/{id}/deny` | POST | server.py:618 | 伪造人工审批拒绝 |
| `POST /api/v1/hitl/request` | POST | server.py:600 | 注入 HITL 请求 |
| `POST /api/v1/evolution/dry-run` | POST | server.py:809 | 触发 LLM 代码生成 |
| `POST /api/v1/evolution/approve-proposal` | POST | server.py:820 | 批准进化提案 |
| `POST /api/compliance/register` | POST | gaas_router.py:26 | 注册合规租户 |
| `POST /api/v1/federation/submit` | POST | federation_router.py:68 | 提交伪造 Merkle 根 |
| `DELETE /api/v1/federation/proof/{org_id}` | DELETE | federation_router.py:108 | 删除他人审计证明 |

**突破口**: 引入 Bearer Token 中间件 + 每个端点声明所需 scope（如 `scope="hitl:approve"`），审计日志中记录 caller_identity。

### 2.2 [CRITICAL] Electron PTY Shell 逃生口 —— 严重性: 9.0/10

```javascript
// gui/electron/main.cjs:81-108
// node-pty 生成本地 shell，IPC 处理任意命令
ipcMain.handle('pty:write', (_, data) => {
  pty.write(data);  // 无治理检查、无审计日志、无 sidecar 路由
});
```

PTY 写入操作**全程绕过 sidecar 治理管线**：
- 无 `AuditLogger` 记录
- 无 `CircuitBreaker` 检查
- 无 `DestructiveOperationGate` 过滤
- 无 `TrustBoundaryManager` 域检查

**突破口**: PTY IPC handler 应调用 `sidecar MCPGateway.route_tool_call()` 走统一审计管线。

### 2.3 [HIGH] CLI 显式治理旁路标志 —— 严重性: 7.5/10

```python
# src/maref_lite/cli.py
parser.add_argument('--live', action='store_true')          # line 280
parser.add_argument('--no-dry-run', action='store_true')    # line 1286
parser.add_argument('--execute-proposals', action='store_true')  # line 1176
```

三个标志分别绕过桌面 dry-run、进化只读模式、SelfExecutor 提案验证。`self_healing_loop.py:76` 中 `proposal_dry_run` 默认为 `True`，`--execute-proposals` 将其置为 `False`，绕过全部治理检查。

**突破口**: 这些标志触发时应在 `AuditLogger` 中写入 `governance_bypassed=True` 的审计条目，同时在元层记录旁路原因。

### 2.4 [HIGH] Mock 后端静默降级 —— 严重性: 7.0/10

```typescript
// gui/src/api/client.ts:28-30
private async detectBackend(): Promise<boolean> {
  try {
    await fetch(`${this.baseUrl}/api/health`);
    return true;
  } catch {
    return false;  // 静默降级，无警告
  }
}
```

当 sidecar 进程崩溃/未启动时，GUI 从 `BackendMode.LIVE` 无提示切换到 `BackendMode.MOCK`。在 mock 模式下，所有治理状态显示为硬编码值（`governanceStore.ts` 中的假数据）。

**突破口**: 降级时触发 `window.dispatchEvent(new CustomEvent('governance:offline'))`，UI 组件监听后显示黄色警告横幅。

### 2.5 [MEDIUM] CooldownManager.force_merge 手动覆盖 —— 严重性: 5.5/10

```python
# src/maref/immunity/cooldown_manager.py:90
def force_merge(self, agent_id: str, manual_override: bool = False) -> bool:
    if manual_override:
        # 直接绕过 contamination 检查
        self._contamination_log[agent_id] = []
        return True
```

`manual_override=True` 跳过所有污染检查。调用方 `immunity_fixer.py` 在自动修复失败时使用此逃生口。

**突破口**: `force_merge` 至少需要 `@security_critical` 装饰器和 `AuditLogger` 记录，以及二次确认机制。

### 2.6 [MEDIUM] ReliabilityMatrix 失败累积自动旁路 —— 严重性: 5.0/10

```python
# src/maref/recursive/reliability_matrix.py:73
BYPASS_THRESHOLD = 3  # 连续失败次数
if consecutive_failures >= BYPASS_THRESHOLD:
    bypass_mode = True  # 自动绕过健康检查
```

3 次连续失败后自动进入 `bypass_mode`，形成反模式：失败越多 → 检查越少 → 失败更隐蔽。

**突破口**: 旁路触发必须记录审计事件 + 通知 `MetaCircuitBreaker` 评估振荡风险。

### 2.7 [MEDIUM] MCP Client fail_mode="open" —— 严重性: 4.5/10

```python
# src/maref/integration/mcp_client.py:25
class MCPClient:
    def __init__(self, fail_mode: str = "open"):
        self.governance_bypassed = False
        # fail_mode="open" 时降级允许所有操作
```

`fail_mode="open"` 时标记 `governance_bypassed=true`，但**该标记未被任何审计或熔断机制消费**——它只是一个布尔值，无人读取。

---

## 三、测试覆盖缺口

### 3.1 高优先级

| 缺口 | 位置 | 当前行数 | 缺少的测试 |
|------|------|---------|-----------|
| `GovernanceOverlay.run()` 事件循环 | `maref_lite/governance.py:71-419` | 348 行 | 无 `asyncio.run()` 集成测试 |
| 跨网络 MCP/A2A 治理 | `sidecar/`, `integration/` | 多处 | 无跨进程边界测试 |
| 策略引擎端到端 | `governance/core_pipeline.py` | 239 行 | 自定义策略→管线→审计→CB 全链路 |
| API 端点安全测试 | `sidecar/server.py` | 全部 | 0 安全测试 |
| 联邦审计网络同步 | `governance/federated_audit.py` | 165 行 | 仅内存测试 |

### 3.2 中优先级

| 缺口 | 影响 |
|------|------|
| `PermissionMatrix` 仅测试"坎"角色，缺 `乾/坤/离/艮` | `permission_matrix.py:103` 定义了 5 种角色 |
| `SocialImpactAssessor` 无行业数据集成测试 | `industry_data.py` 与 `social_impact.py` 脱节 |
| `SupplyChainVerifier` 仅 2-3 组件 SBOM | 1000+ 依赖树信任传播未验证 |
| `MetaCognitiveAuditor` 无性能/内存泄漏测试 | `metacognition.py` 大规模评估未验证 |
| `PulseWriter` 无跨进程心跳测试 | `p2_new_modules.py` 零集成测试 |

### 3.3 并发/压力缺口

| 场景 | 当前测试 | 需要 |
|------|---------|------|
| 审计日志文件轮转 + 并发写入 | 仅单线程 | 10 线程 + 50MB 轮转 |
| 断路器完整节流 → cooldown → 复用 | 仅分段测试 | 24h+ 完整生命周期 |
| GovernanceOverlay 事件积压 | 无 | 10K+ 事件/秒的 backpressure |
| DriftGuard + Sidecar + 治理全链路 | 仅 `test_governance_flow.py` | 24h 混沌测试 |

---

## 四、形式化验证缺口

| 缺口 | 当前状态 | 代码位置 | 目标 |
|------|---------|---------|------|
| 34-state 联合 FSM | 仅 10-state 156 states | `formal/MarefLite.tla` | v0.42 TLAPS |
| TLAPS 定理证明 | 未开始 | — | v0.42 |
| 34-state 对称归约 | 未研究 | — | 规划中 |
| 活性/终止性证明 | 仅 PlusCal `MarefLiteModel.tla` | — | L3 |
| Agent-Gov 跨层不变量 | 无 | `trust_bridge.py:181` | L3 |
| PTY 逃生口 TLA+ 模型 | 无 | `electron/main.cjs:81` | L3 |
| Mock 降级安全模型 | 无 | `client.ts:28` | L3 |

**TLA+ 路线图进度**: Model Checking ✅ → TLAPS ❌ → Sperner/Lyapunov ❌

---

## 五、已知遗留缺口（来自 L2 验收）

| 编号 | 缺口 | 阶段 | 当前状态 |
|------|------|------|---------|
| G3 | MetaRatchet 递归硬化 — 嵌套场景未覆盖 | L3 | ❌ 未开始 |
| G4 | TLA+ 宪法合规检查 — 仅 4 条跨维不变量 | L3 | ⚠️ 部分完成 |
| G5 | SubgoalInterceptor — 子目标级联回滚未实现 | L3 | ❌ 未开始 |
| G6 | 7 天稳定性验证 — 仅 24h | L3 | ❌ |
| G7 | Self-healing RSI 自动恢复未闭环 | L3 | ❌ |
| G8 | Self-SAEB 免疫系统自检 | 规划中 | ❌ |

---

## 六、突破口优先级矩阵

```
            Impact
            HIGH    MEDIUM   LOW
Effort
  LOW      P0-1,2   P0-3    P1-8
           P0-4
  MEDIUM   P1-5     P1-6    P2-12
           P1-7
  HIGH     P2-9     P2-11   P3-14
           P2-10    P3-13   P3-15/16
```

### P0 —— 立即（1-2 周，4 项）

| # | 行动 | 预期效果 | 涉及文件 |
|---|------|---------|---------|
| 1 | API Bearer Token 认证中间件 | 封堵 30+ 零认证端点 | `sidecar/server.py` |
| 2 | PTY IPC → MCP 网关路由 | 封闭 Electron shell 逃生口 | `gui/electron/main.cjs` |
| 3 | CLI 旁路标志审计事件注入 | 所有 `--no-dry-run` 等写入 `governance_bypassed` | `maref_lite/cli.py` |
| 4 | Mock 降级 UI 警告 + 审计事件 | 治理离线时明确可见 | `gui/src/api/client.ts` |

### P1 —— 短期（1 个月，4 项）

| # | 行动 | 预期效果 | 涉及文件 |
|---|------|---------|---------|
| 5 | API 端点安全测试套件 | 认证绕过/注入/权限提升测试 | `tests/security/` |
| 6 | 策略引擎端到端集成测试 | 自定义策略全链路覆盖 | `tests/governance/` |
| 7 | 24-state Agent FSM TLA+ 建模 | 补全 34-state 第一阶段 | `src/formal/` |
| 8 | `GovernanceOverlay.run()` 事件循环测试 | CLI 治理生命周期验证 | `tests/cli/` |

### P2 —— 中期（2-3 个月，4 项）

| # | 行动 | 预期效果 |
|---|------|---------|
| 9 | 34-state 联合 TLA+ 模型 + 对称归约 | 跨层安全性形式化证明 |
| 10 | TLAPS 定理证明启动 | HALT 不可绕过 + Gray Code 单跳不变量 |
| 11 | RL-004/RL-005 集成测试 | 克隆审查 + 权重签名全链路 |
| 12 | 免疫系统 Self-SAEB 闭环 | 基因退化自检管线 |

### P3 —— 长期，4 项

7 天稳定性、跨仓库宪法检查、A2A 治理拦截、TLAPS 全链路证明

---

## 七、结论

MAREF 在**核心治理引擎层**设计了业界领先的原语集合——TLA+ 形式化验证的 Gray Code FSM、HMAC + Ed25519 双签名审计链、34 态联合状态机、5 条宪法红线。核心引擎的测试覆盖率（尤其是状态机和审计链）达到极高水准。

但**运行时边缘层存在结构性空隙**：
- 30+ REST 端点零认证（CRITICAL）
- Electron PTY 提供无治理的本地 shell（CRITICAL）
- 3 个 CLI 标志可在无审计的情况下绕过治理（HIGH）
- 治理离线时 GUI 静默降级（HIGH）
- 4 个自动旁路机制形成"失败→更少检查"的反模式（MEDIUM）

**核心洞察**: MAREF 治理架构已具备"做什么"的完备设计，但在"强制做到"的边缘层存在系统性缺失。P0 的四项修复（API 认证、PTY 路由、CLI 旁路审计、Mock 降级警告）可在 1-2 周内消除最大的治理断裂面，使核心设计在运行时得到有效实施。

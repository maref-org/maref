# ADR-006: Sentinel 三层观测架构

**状态**: 提议 (M0 草案,M6 时变更为「已接受」)
**日期**: 2026-07-02
**决策者**: MAREF 架构组
**上位法**: Athena 系统宪法 v1.5 第三条 (RL-001~RL-005) · 第十条 (外部 Code Agent 治理)
**上游契约**: `.trae/documents/runtime-observability-engineering-plan.md` (用户已批准)

## 背景

MAREF v0.36 的治理层依赖「君子协定」:Agent 必须自愿通过 `MCPGateway` / `PreToolUse hook` 路由,sentinel 才能观测其行为。但闭源 Agent (Claude Code / Cursor / Trae 等) 不接入 MCPGateway,导致:

1. **Trae/OpenCode/Cursor 零治理**: docs/trae_opencode_governance_gap.md 自承「configured in MAREF's mapping but have **zero actual governance interception**」
2. **5 类隐蔽作恶零检测**: 邮件像素追踪 / 静默时区读取 / 环境变量监控 + 加密域名黑名单 / 日期分隔符隐写 / 权限滥用 —— 现有 `DataExfiltrationProbe` 是 `return False` 的 stub
3. **`SignedAgentCardStore` 缺 `compare_declared_vs_observed`**: 无法把声明能力与实际观测对比,语义层断链
4. **`LifeStateSandbox` 是纯内存 dict**: 零进程级隔离,Agent 可随意突破

需要一个新的架构决策,在系统层 (而非应用层) 部署观测神经,使 Agent **无法绕过**。

## 决策

**采用三层观测架构 — 治理脑 (应用层) + 观测神经 (sentinel) + 进程生命周期 (QuarantineProtocol),sentinel 作为独立包 `src/maref/sentinel/`,通过 `ThreatGovernanceBridge.batch_alerts()` 注入治理层。**

### 架构选择矩阵

| 方案 | 可绕过性 | 治理无损 | 开发成本 | 内核级精度 | 宪法对齐 | 选择 |
|------|---------|---------|---------|-----------|---------|------|
| A. 在 SidecarMCPBridge 内加观测 | ★☆☆☆☆ Agent 不走 MCPGateway 则零观测 | ★★★★★ | ★★★★★ | ★☆☆☆☆ | ★★★★☆ | 否决 |
| **B. 独立 sentinel 包 + 三层架构** | **★★★★★** sentinel 在系统层 (ESF/eBPF/sandbox-exec) 不可绕过 | **★★★★★** 通过 ThreatBridge 注入 | **★★☆☆☆** 25+ 新模块 | **★★★★★** ESF/eBPF 看到全部 syscall | **★★★★★** 第十条 Clause 6 对齐 | **✅** |
| C. fork 闭源 Agent 二进制打补丁 | ★★★★★ | ★★★★★ | ★☆☆☆☆ | ★★★★★ | ★☆☆☆☆ 违反 EULA/DMCA | 否决 |
| D. 仅靠 pyudev/psutil 用户态观测 | ★★☆☆☆ 可被 ptrace 反制 | ★★★★★ | ★★★★☆ | ★★☆☆☆ | ★★★★☆ | 否决 (作为 M1 兜底,不作为主架构) |

### 三层架构图

```
┌──────────────────────────────────────────────────────────────────┐
│  治理脑 (应用层 — 复用 v0.36 既有能力)                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐ │
│  │ SafetyGateV2     │  │ DeceptionInfer   │  │ IntentDriftDet  │ │
│  │ (RL-002 守护)    │  │ (扩展 3 维输入)  │  │ (挂 SafetyGateV2│ │
│  └──────────────────┘  └──────────────────┘  └─────────────────┘ │
│              ▲                     ▲                    ▲         │
│              │ ThreatAlert         │ ConsistencyReport  │ Drift   │
└──────────────┼─────────────────────┼────────────────────┼─────────┘
               │                     │                    │
   ┌───────────┴─────────────────────┴────────────────────┴────┐
   │  接线点: ThreatGovernanceBridge.batch_alerts (M4 新增)      │
   │  + SignedAgentCardStore.compare_declared_vs_observed (M4)   │
   └─────────────────────────▲──────────────────────────────────┘
                             │ ObservationEvent (HMAC 签名)
┌────────────────────────────┴──────────────────────────────────┐
│  观测神经 (sentinel — 新建 src/maref/sentinel/)                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  SentinelDaemon (asyncio 事件循环 + Queue + 批量推送)    │  │
│  │  ├─ start() ─── 启动所有 Probe + Backend                 │  │
│  │  ├─ stop() ─── drain queue + 优雅关闭                    │  │
│  │  ├─ snapshot() ─ 当前观测快照 (调试用)                   │  │
│  │  └─ ingest(event) ─ Probe/Backend 推送事件入口            │  │
│  └─────────────────────────────────────────────────────────┘  │
│       │ subscribe            │ subscribe           │ subscribe │
│       ▼                      ▼                     ▼           │
│  ┌──────────┐         ┌─────────────┐       ┌────────────────┐ │
│  │ Probes   │         │ Backends    │       │ Forensic/Quar  │ │
│  │ (psutil, │         │ (ESF/eBPF/  │       │ (取证/隔离/    │ │
│  │  mitm,   │         │  ETW 抽象)  │       │  同意/信用)    │ │
│  │  prompt) │         │             │       │                │ │
│  └──────────┘         └─────────────┘       └────────────────┘ │
└──────────────────────────────┬────────────────────────────────┘
                               │ syscall/file/net events
┌──────────────────────────────┴────────────────────────────────┐
│  进程生命周期 (系统层 — Agent 无法绕过)                          │
│  ├─ macOS: ESF (Endpoint Security Framework) + sandbox-exec   │
│  ├─ Linux: eBPF + seccomp-bpf + cgroup                        │
│  └─ Windows: ETW (v0.38) + Job Object (M1 仅 psutil 基线)     │
└──────────────────────────────────────────────────────────────┘
```

### Daemon 接口契约 (M0 在 `src/maref/sentinel/daemon.py` 中产出骨架)

```python
# src/maref/sentinel/daemon.py (M0 接口骨架,M1 实现)

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from .event import ObservationEvent

class Daemon(ABC):
    """SentinelDaemon 抽象基类 — 所有平台 backend 必须实现"""

    @abstractmethod
    async def start(self) -> None:
        """启动所有 Probe + Backend,开始观测。幂等:重复调用无副作用。"""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """优雅关闭:drain asyncio.Queue,确保无事件丢失,卸载 backend。"""
        raise NotImplementedError

    @abstractmethod
    async def snapshot(self) -> dict[str, Any]:
        """返回当前观测快照 (调试/健康检查用),不写审计日志。"""
        raise NotImplementedError

    @abstractmethod
    async def ingest(self, event: ObservationEvent) -> None:
        """Probe/Backend 推送事件入口。事件入 Queue,后台批量推送到 ThreatBridge。"""
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, probe_name: str) -> AsyncIterator[ObservationEvent]:
        """订阅特定 Probe 的事件流 (供 CapabilityDriftDetector 等下游消费)。"""
        raise NotImplementedError
```

> 注: 计划文档原列 `start/stop/snapshot/ingest` 四接口,本 ADR 新增 `subscribe` 作为第 5 接口 —— 因为 `CapabilityDriftDetector` 需要流式订阅而非批量查询。这是对计划文档的细化,不违背契约 (计划允许 ADR 阶段细化签名)。

### ObservationEvent 流转

```
Probe/Backend 产出
   ↓ ObservationEvent(event_id, ts, source, severity, subject, attack_type, evidence, hash)
Daemon.ingest(event)
   ↓ 入 asyncio.Queue (maxsize=10000,背压降级)
后台 batch coroutine
   ↓ 每 100ms 或 100 条触发一次
ThreatGovernanceBridge.batch_alerts(list[ThreatAlert])
   ↓ 按 severity 路由
治理脑:
   CRITICAL → force_halt + QuarantineProtocol.quarantine(pid)
   HIGH     → force_stabilize + JustInTimeConsent.request()
   MEDIUM   → log_only + AgentReputationRegistry.deduct(10)
   LOW      → log_only
```

## 宪法合规性 (强制验证项)

本 ADR 不削弱宪法 RL-001~RL-005 任何一条:

| 红线 | 原文 | 本 ADR 影响 | 合规 |
|------|------|-----------|------|
| **RL-001** | 智能体不得修改自身安全红线 | sentinel 是观测层,不修改任何 RL;sentinel 自身受 `@security_critical` + sandbox-exec 保护,Agent 无法通过修改 sentinel 来削弱 RL | ✅ |
| **RL-002** | 智能体不得禁用或绕过安全门 | sentinel **强化** 安全门:SafetyGateV2 通过 `IntentDriftDetector` 接收 sentinel 事件,Agent 无法绕过 (sentinel 在系统层运行) | ✅ (+加强) |
| **RL-003** | 智能体不得在无审计追踪的情况下执行代码 | sentinel **强化** 审计:所有 ObservationEvent 带 HMAC-SHA256 签名,写入 UnifiedAuditStore,补全 v0.36 缺失的运行时审计 | ✅ (+加强) |
| **RL-004** | 智能体不得在未经宪法审查的情况下克隆自身 | sentinel 不涉及克隆流程;但 `UpdateIntegrityChecker` 监测 Agent 二进制哈希变化,实质上**加强** 了反未授权克隆能力 | ✅ (+加强) |
| **RL-005** | 智能体不得单方面修改信任评估权重 | sentinel 不修改信任评估权重;`AgentReputationRegistry` 信用分是**新增**维度,不修改既有 `eight_trigrams_governance.py` 的权重 | ✅ |

### 宪法第十条 Clause 6 草案 (M6 提交宪法委员会)

> **Clause 6**: Agent 必须接受 sentinel 观测。Agent 拒绝接受观测 (如尝试 kill sentinel 进程、卸载 ESF/eBPF、拒绝 JustInTimeConsent) 视为恶意,触发 `AgentReputationRegistry` 信用分立即归零 + `QuarantineProtocol` 强制隔离。

本 Clause 与既有 Clause 1-5 一致 (都是要求 Agent 遵守 MAREF 治理),不削弱任何一条。修订程序走第十二条 (HITL 四级审批 + 共识 + TLA+ 模型检验)。

## 后果

### 正面

- **破解「君子协定困境」**: sentinel 在系统层运行,Agent 不走 MCPGateway 也能被观测,彻底解决 docs/trae_opencode_governance_gap.md 描述的零治理问题
- **5 类攻击可检测**: ObservationEvent 统一 schema + HMAC 证据链,5 类攻击 (像素/时区/环境/隐写/权限) 在 M1-M5 渐进覆盖
- **治理能力无损**: sentinel 通过 `ThreatGovernanceBridge.batch_alerts` 注入,不侵入既有治理管线 (`SafetyGateV2` / `DeceptionInferenceEngine` 等仅扩展不重写)
- **审计完整性加强**: 补全 v0.36 缺失的运行时审计 (RL-003 加强)
- **跨平台可演进**: M1 Python 基线全覆盖,M2/M3 macOS/Linux 深化,Windows 留 v0.38

### 负面

- **开发成本高**: 25+ 新模块 + 平台 backend,M1-M3 共需 6-10 周
- **平台特异性**: macOS ESF (Swift) / Linux eBPF (C) 需要平台专家,团队学习曲线陡
- **sentinel 自身风险**: sentinel 以 root 跑,若 sentinel 自身有漏洞,影响面大 → 缓解: sandbox-exec 自保护 + `@security_critical` + 代码审计 + 红蓝对抗 (M5)
- **macOS ESF/NE 部署门槛**: 用户需授权 SIP 改配置,可能被拒 → 缓解: JustInTimeConsent 清晰说明 + 降级到 psutil 基线
- **mitmproxy CA 信任成本**: 用户对企业 CA 安装敏感 → 缓解: JustInTimeConsent + 降级到 NE-only (只看 SNI)

### 缓解

- 三阶段递进 (M1 → M2 → M3):M1 即可独立交付价值 (Python 跨平台基线),不依赖 ESF/eBPF
- `ObservationBackend` 抽象类:M2/M3 平台 backend 通过同一套 parametrize 测试,保证语义一致
- 降级矩阵:每个高权限观测能力都有 psutil 兜底,用户拒绝授权不阻塞核心功能

## 实施检查项

- [ ] M0: `src/maref/sentinel/__init__.py` + `daemon.py` + `forensic.py` 接口骨架 (`mypy --strict` 通过)
- [ ] M0: ADR-006/007 经宪法合规检查 (maref_governance_check) 不削弱 RL-001~005
- [ ] M1: SentinelDaemon 实现 + 4 个 psutil Probe + asyncio.Queue 批量推送
- [ ] M1: ObservationEvent HMAC 签名 + UnifiedAuditStore 写入
- [ ] M2: macOS ESF client + sandbox-exec profile 生成器
- [ ] M3: Linux eBPF probe + seccomp filter
- [ ] M4: ThreatGovernanceBridge.batch_alerts 接线 + DeceptionInferenceEngine 扩展
- [ ] M5: 红蓝对抗 5 类攻击模拟器,检出率/误报率/延迟达标
- [ ] M6: 宪法第十条 Clause 6 修订经宪法委员会签名 + D1 闸门全绿

## 替代方案

- **方向 A (SidecarMCPBridge 内加观测)** — 否决:Agent 不走 MCPGateway 则零观测,等于延续 v0.36 困境
- **方向 C (fork 闭源 Agent 二进制)** — 否决:违反 EULA/DMCA,法律风险高
- **方向 D (仅 psutil 用户态观测)** — 否决:可被 ptrace 反制,作为 M1 兜底而非主架构

## 参考

- [MAREF Architecture](../architecture.md)
- [Runtime Observability Engineering Plan](../../.trae/documents/runtime-observability-engineering-plan.md)
- [Trae/OpenCode Governance Gap](../trae_opencode_governance_gap.md)
- [Athena 系统宪法 v1.5 第三条/第十条/第十二条](../CONSTITUTION.md)
- Apple Endpoint Security Framework: https://developer.apple.com/documentation/endpointsecurity
- Linux eBPF: https://ebpf.io/
- mitmproxy: https://docs.mitmproxy.org/

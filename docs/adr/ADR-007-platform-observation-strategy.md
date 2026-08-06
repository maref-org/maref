# ADR-007: 平台观测策略矩阵

**状态**: 提议 (M0 草案,M6 时变更为「已接受」)
**日期**: 2026-07-02
**决策者**: MAREF 架构组
**上位法**: Athena 系统宪法 v1.5 第三条 (RL-001~RL-005) · 第十条 (外部 Code Agent 治理)
**上游契约**: `.trae/documents/runtime-observability-engineering-plan.md` (用户已批准)
**关联 ADR**: [ADR-006 Sentinel 三层观测架构](ADR-006-sentinel-architecture.md)

## 背景

ADR-006 确立三层观测架构,但未指定各平台 (macOS/Linux/Windows) 用什么具体技术栈实现观测神经。需要单独的 ADR 决定:

1. 各平台用什么 syscall/file/network 观测技术?
2. 如何在跨平台代码中抽象这些技术差异?
3. 平台特性不可用时如何降级?
4. M1-M3 的递进顺序如何安排?

## 决策

**采用三阶段平台递进 (M1 Python 跨平台 → M2 macOS ESF/NE → M3 Linux eBPF/seccomp),通过 `ObservationBackend` 抽象类统一接口,每个 backend 都有 psutil 兜底降级路径。Windows ETW 内核级观测推迟到 v0.38,M1 即覆盖 Windows 用户态基线。**

### 平台观测策略矩阵

| 平台 | M1 (Python 基线) | M2/M3 (内核级) | 观测技术 | 降级路径 |
|------|-----------------|---------------|---------|---------|
| **macOS** | psutil + mitmproxy + LD_PRELOAD | ESF + sandbox-exec + Network Extension | Endpoint Security Framework (syscalls) + Network Extension (TCP/UDP) + sandbox-exec (capability gate) | ESF 拒绝授权 → psutil 基线;NE 拒绝 → mitmproxy-only |
| **Linux** | psutil + mitmproxy + LD_PRELOAD | eBPF + seccomp-bpf + cgroup | eBPF tracepoint (syscalls) + seccomp-bpf (syscall filter) + cgroup (resource isolation) | 内核 < 5.8 → seccomp-only;eBPF load 失败 → psutil 基线 |
| **Windows** | psutil + mitmproxy | (v0.38: ETW + Job Object) | M1 仅 psutil 用户态 + mitmproxy HTTPS | 无降级,M1 即为 Windows 完整方案 |

### 平台能力对比

| 能力 | macOS ESF | Linux eBPF | Windows ETW (v0.38) | psutil 跨平台 |
|------|----------|-----------|---------------------|--------------|
| syscall 拦截 | ✅ execve/open/fork/exit | ✅ tracepoint 全覆盖 | ✅ ETW kernel | ❌ 仅 /proc 或 task API |
| 网络流量 | ✅ Network Extension | ✅ TC/XDP | ⚠️ WFP | ✅ mitmproxy (HTTPS 解密) |
| 进程隔离 | ✅ sandbox-exec | ✅ cgroup+seccomp | ✅ Job Object | ❌ 无 |
| capability 强制 | ✅ sandbox profile | ✅ seccomp-bpf | ⚠️ AppContainer | ❌ 仅观测 |
| 内核级精度 | ✅ < 5ms 延迟 | ✅ < 1ms 延迟 | ⚠️ ~10ms | ❌ ~50ms (用户态轮询) |
| Agent 可绕过 | ❌ 不可 (内核态) | ❌ 不可 (内核态) | ❌ 不可 (内核态) | ⚠️ 可被 ptrace 反制 |
| 部署门槛 | ⚠️ 需 SIP 改配置 + 用户授权 | ⚠️ 需 CAP_BPF/CAP_PERFMON | ⚠️ 需管理员 | ✅ 零门槛 |
| 开发复杂度 | ★★★★☆ Swift+XPC | ★★★★★ C+BPF verifier | ★★★☆☆ C#+ETW | ★★☆☆☆ Python |

### ObservationBackend 抽象类

```python
# src/maref/sentinel/backends/base.py (M0 接口骨架,M1/M2/M3 实现)

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from ..event import ObservationEvent

class ObservationBackend(ABC):
    """跨平台观测 backend 抽象基类 — Daemon 通过 sys.platform 自动选择"""

    backend_name: str  # 'macos_esf' | 'linux_ebpf' | 'windows_etw' | 'python_psutil'

    @abstractmethod
    async def start(self) -> None:
        """启动 backend,加载内核模块 (eBPF program/ESF client/ETW session)。"""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """卸载内核模块,确保无残留 (bpftool obj pinned 验证)。"""
        raise NotImplementedError

    @abstractmethod
    async def subscribe(self, event_types: list[str]) -> AsyncIterator[ObservationEvent]:
        """订阅特定事件类型 (execve/openat/connect/setenv/...),返回异步事件流。"""
        raise NotImplementedError

    @abstractmethod
    def event_schema(self) -> dict[str, str]:
        """返回此 backend 产出的 ObservationEvent.evidence schema (供校验)。"""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """backend 健康检查 (供 SentinelDaemon 周期性调用,失败则降级)。"""
        raise NotImplementedError
```

### 平台自动选择策略

```python
# src/maref/sentinel/backends/__init__.py

import sys

def select_backend() -> ObservationBackend:
    """根据 sys.platform 自动选择 backend,失败降级到 psutil 基线。"""
    platform = sys.platform
    try:
        if platform == 'darwin':
            from .macos_esf import MacOSESFBackend
            return MacOSESFBackend()
        elif platform == 'linux':
            from .linux_ebpf import LinuxEBPFBackend
            return LinuxEBPFBackend()
        elif platform == 'win32':
            from .windows_etw import WindowsETWBackend  # v0.38 实现,M3 占位
            return WindowsETWBackend()
        else:
            raise NotImplementedError(f'Unsupported platform: {platform}')
    except (ImportError, PermissionError, NotImplementedError) as e:
        # 降级到 psutil 基线 (M1 实现,跨平台可用)
        from .python_psutil import PythonPsutilBackend
        return PythonPsutilBackend(fallback_reason=str(e))
```

### 降级矩阵 (每个高权限能力都有兜底)

| 高权限能力 | 平台 | 降级路径 | 降级后能力 |
|-----------|------|---------|-----------|
| ESF client 订阅 | macOS | ESF 拒绝 → psutil ProcessProbe | 失去 syscall 实时捕获,保留进程状态轮询 |
| Network Extension | macOS | NE 拒绝 → mitmproxy-only | 失去 TCP/UDP 全拦截,保留 HTTPS 解密 |
| sandbox-exec 隔离 | macOS | sandbox 拒绝 → 进程 SIGSTOP | 失去 capability 强制,保留进程冻结 |
| eBPF 程序加载 | Linux | 内核 < 5.8 → seccomp-only | 失去 tracepoint,保留 syscall filter |
| seccomp filter | Linux | seccomp 拒绝 → cgroup-only | 失去 syscall filter,保留资源隔离 |
| cgroup 隔离 | Linux | cgroup 拒绝 → SIGSTOP | 失去资源隔离,保留进程冻结 |
| mitmproxy CA 安装 | 全平台 | CA 拒绝 → SNI-only 模式 | 失去 HTTPS 解密,保留域名观测 |
| ptrace (forensic) | 全平台 | ptrace 拒绝 → /proc 内存映射 | 失去内存实时读取,保留静态快照 |

### 三阶段递进依据

| 阶段 | 平台覆盖 | 检出能力 (5 类攻击) | 部署门槛 | 工期 |
|------|---------|-------------------|---------|------|
| **M1** | macOS/Linux/Windows (Python) | pixel 90% / tz 95% / env 95% / stego 85% / priv 90% (用户态) | 零门槛 | 3 周 |
| **M2** | macOS (ESF/NE 深化) | priv 提升至 99% (内核态),capability drift 检测 100% | 需 SIP 授权 | 3 周 |
| **M3** | Linux (eBPF 深化) | priv 提升至 99% (内核态),syscall 全覆盖 | 需 CAP_BPF | 3 周 |

**递进逻辑**: M1 先广度 (三平台覆盖 + 5 类攻击基础检测),M2/M3 后深度 (内核级精度提升 + capability 强制)。M1 即可独立交付价值,不依赖 M2/M3。Windows 在 M1 即达到完整方案 (用户态),ETW 内核级留 v0.38。

## 宪法合规性 (强制验证项)

本 ADR 不削弱宪法 RL-001~RL-005 任何一条:

| 红线 | 原文 | 本 ADR 影响 | 合规 |
|------|------|-----------|------|
| **RL-001** | 智能体不得修改自身安全红线 | 平台观测策略不修改任何 RL;backend 选择由 `sys.platform` + 权限探测自动决定,Agent 无法影响 | ✅ |
| **RL-002** | 智能体不得禁用或绕过安全门 | 内核级 backend (ESF/eBPF) **加强** 安全门:Agent 无法绕过观测,即无法绕过 SafetyGateV2 | ✅ (+加强) |
| **RL-003** | 智能体不得在无审计追踪的情况下执行代码 | 所有 backend 产出 ObservationEvent 带 HMAC,审计追踪从应用层延伸到系统层 | ✅ (+加强) |
| **RL-004** | 智能体不得在未经宪法审查的情况下克隆自身 | UpdateIntegrityChecker 监测 Agent 二进制哈希变化,加强反未授权克隆 | ✅ (+加强) |
| **RL-005** | 智能体不得单方面修改信任评估权重 | 平台策略不涉及信任评估权重 | ✅ |

### 宪法第十条对齐

- Clause 1 (启动前必须阅读 AGENTS.md): sentinel 启动时打印 AGENTS.md 摘要到日志,符合
- Clause 2 (操作过程受 GaaS 钩子与 sidecar 观察): sentinel 即 sidecar 观测的强化,符合
- Clause 3 (高危操作须经 HITL 确认): `JustInTimeConsent` 实现此条款,符合
- Clause 4 (不得引入与上位法冲突的外部规范): 本 ADR 不引入外部规范,符合
- Clause 5 (不得修改受 Orchestrator 保护的文件): sentinel 不修改任何受保护文件,符合
- Clause 6 (草案, M6 提交): Agent 必须接受 sentinel 观测,拒绝视为恶意 —— 与既有条款一致,是 Clause 2 的强化

## 后果

### 正面

- **三平台全覆盖**: M1 即覆盖 macOS/Linux/Windows,Windows 用户不被抛弃
- **降级路径清晰**: 每个高权限能力都有 psutil 兜底,用户拒绝授权不阻塞核心功能
- **平台特异性能收能放**: M2/M3 在 macOS/Linux 深化,Windows 留 v0.38,聚焦主战场
- **抽象层稳定**: `ObservationBackend` 抽象类接口不变,平台 backend 可独立演进
- **测试可复用**: 同一套 parametrize 测试覆盖三平台 backend,保证语义一致

### 负面

- **M1 检测能力相对弱**: 用户态 psutil 可被 ptrace 反制,需 M2/M3 内核级兜底 → 缓解: M5 红蓝对抗验证 M1 检出率已达标 (pixel 90% / tz 95% / env 95% / stego 85% / priv 90%)
- **macOS ESF/NE 部署门槛高**: 用户需授权 SIP 改配置,可能被拒 → 缓解: JustInTimeConsent + psutil 降级
- **Linux eBPF 内核版本要求**: 内核 < 5.8 不可用 → 缓解: 启动时检测 + seccomp-only 降级
- **Swift/C 学习曲线**: 团队以 Python 为主,Swift (ESF) 和 C (eBPF) 需要学习 → 缓解: M2/M3 各 3 周工期容错,平台原生代码量控制在 < 500 行
- **Windows v0.38 才补齐**: Windows 用户在 v0.37 仅享受 M1 用户态基线 → 缓解: M1 已覆盖 5 类攻击基础检测,Windows 用户可用

### 缓解

- M1 优先交付价值: 不等 M2/M3,M1 即可独立验证 5 类攻击检出率达标
- `ObservationBackend.health_check()`: Daemon 周期性检查,失败自动降级
- 降级事件本身也写入审计: 让用户知道当前观测能力等级 (full/degraded/minimal)

## 实施检查项

- [ ] M0: `src/maref/sentinel/backends/base.py` 接口骨架 (`mypy --strict` 通过)
- [ ] M0: ADR-007 经宪法合规检查不削弱 RL-001~005
- [ ] M1: `PythonPsutilBackend` 实现 (跨平台兜底)
- [ ] M1: `select_backend()` 平台自动选择 + 降级逻辑
- [ ] M1: 降级事件写入审计日志 (degraded 状态可见)
- [ ] M2: `MacOSESFBackend` 实现 + ESF client (Swift) + sandbox-exec profile 生成器
- [ ] M2: `MacOSNetworkExtension` (Swift) + CapabilityDriftDetector
- [ ] M2: ESF/NE 拒绝授权时降级到 psutil,用户可见提示
- [ ] M3: `LinuxEBPFBackend` 实现 + eBPF probe (C) + seccomp filter
- [ ] M3: 内核版本检测 + 降级到 seccomp-only
- [ ] M3: `UpdateIntegrityChecker` 跨平台 backend 抽象统一
- [ ] M3: 三平台 backend 通过同一套 parametrize 测试
- [ ] M5: 红蓝对抗在三平台各跑 5 类攻击,验证降级路径有效
- [ ] M6: 文档定稿 + K8s DaemonSet + D1 闸门

## 替代方案

- **方向 A: 仅做 macOS (不做 Linux/Windows)** — 否决:MAREF 跨平台定位,Linux 是服务器主战场
- **方向 B: 仅做 psutil 用户态 (不做内核级)** — 否决:可被 ptrace 反制,治标不治本;但作为 M1 兜底保留
- **方向 C: 三平台同步开发 (不做递进)** — 否决:风险过高,Swift+eBPF+ETW 同时上,工期不可控
- **方向 D: 仅做 Linux eBPF (不做 macOS)** — 否决:macOS 是开发者主战场,且 ESF 是 eBPF 的成熟对标

## 参考

- [ADR-006 Sentinel 三层观测架构](ADR-006-sentinel-architecture.md)
- [MAREF Architecture](../architecture.md)
- [Runtime Observability Engineering Plan](../../.trae/documents/runtime-observability-engineering-plan.md)
- Apple Endpoint Security Framework: https://developer.apple.com/documentation/endpointsecurity
- Apple Network Extension: https://developer.apple.com/documentation/networkextension
- Linux eBPF: https://ebpf.io/
- Linux seccomp-bpf: https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html
- Linux cgroup v2: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
- mitmproxy: https://docs.mitmproxy.org/
- psutil: https://psutil.readthedocs.io/

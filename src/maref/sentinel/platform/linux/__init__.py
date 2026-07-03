"""
maref.sentinel.platform.linux — Linux eBPF + seccomp 内核观测

M3 (Linux) 内核观测模块提供:
1. BPFProbe — 通过 eBPF (bcc) 跟踪 syscall 事件 (connect/openat/getenv)
2. SeccompFilter — 通过 seccomp-bpf (prctl) 限制进程 syscall 权限

与 macOS 平台类似,内核事件通过异步队列推送到 SentinelDaemon,
事件带 HMAC-SHA256 签名保证证据完整性。
"""

from __future__ import annotations

from maref.sentinel.platform.linux.bpf_probe import (
    BPFNotAvailableError,
    BPFProbe,
)
from maref.sentinel.platform.linux.seccomp_filter import (
    SECCOMP_MODE_FILTER,
    X8664Syscalls,
    SeccompFilter,
    SeccompPolicy,
)

__all__: list[str] = [
    "BPFNotAvailableError",
    "BPFProbe",
    "SECCOMP_MODE_FILTER",
    "SeccompFilter",
    "SeccompPolicy",
    "X8664Syscalls",
]

__version__ = "0.37.0-m3.0"

"""
maref.sentinel.platform — 平台专属观测 backend

跨平台观测基线 (M1) 在 psutil 层完成后,M2/M3 在内核层补充:
- macOS: ESF (Endpoint Security Framework) + Network Extension + sandbox-exec
- Linux: eBPF + seccomp-bpf + cgroup
- Windows: ETW + Job Object (v0.38)

平台 backend 通过 Unix domain socket 或 XPC 把内核事件推送到
SentinelDaemon,与 psutil Probe 形成双重判定。
"""

from __future__ import annotations

__all__: list[str] = ["macos", "linux"]
__version__ = "0.37.0-m2.0"

"""
maref.sentinel.platform.macos — macOS 系统扩展观测

包含四个组件:
1. esf_client.swift — Endpoint Security Framework 客户端 (Swift 源码,需 swiftc 编译)
2. sandbox_profile_gen.py — 根据 SignedAgentCard 生成 sandbox-exec profile
3. xpc_bridge.py — Python ↔ Swift ESF client 的 XPC/Unix socket 桥接
4. entitlements.py — macOS 系统扩展代码签名 entitlement 生成与验证

ESF client 以独立进程运行 (需 com.apple.developer.endpoint-security.client entitlement),
通过 Unix domain socket 把内核事件流式传输到 Python SentinelDaemon。
"""

from __future__ import annotations

from maref.sentinel.platform.macos.entitlements import (
    COMBINED_ENTITLEMENTS,
    ESF_REQUIRED_ENTITLEMENTS,
    NE_REQUIRED_ENTITLEMENTS,
    EntitlementGenerator,
    EntitlementGeneratorError,
    EntitlementValidator,
)
from maref.sentinel.platform.macos.sandbox_profile_gen import (
    CAPABILITY_TO_SANDBOX_RULES,
    SandboxProfileError,
    SandboxProfileGenerator,
    SandboxProfileResult,
)
from maref.sentinel.platform.macos.xpc_bridge import (
    ESFClientError,
    ESFEvent,
    ESFEventType,
    XPCBridge,
    XPCBridgeState,
)

__all__: list[str] = [
    # entitlements
    "COMBINED_ENTITLEMENTS",
    "ESF_REQUIRED_ENTITLEMENTS",
    "NE_REQUIRED_ENTITLEMENTS",
    "EntitlementGenerator",
    "EntitlementGeneratorError",
    "EntitlementValidator",
    # sandbox profile generator
    "CAPABILITY_TO_SANDBOX_RULES",
    "SandboxProfileError",
    "SandboxProfileGenerator",
    "SandboxProfileResult",
    # XPC bridge
    "ESFClientError",
    "ESFEvent",
    "ESFEventType",
    "XPCBridge",
    "XPCBridgeState",
]

__version__ = "0.37.0-m2.1"

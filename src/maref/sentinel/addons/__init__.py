"""
maref.sentinel.addons — 第三方工具的 sentinel 扩展

每个 addon 把外部工具 (mitmproxy / wireshark / etc.) 的事件流
转换为 sentinel 内部数据结构 (FlowRecord / 等),推入对应 Probe 的队列。

M1.2 已实现:
- SentinelMitmAddon — mitmproxy addon,捕获 HTTP flow → FlowRecord → NetworkEgressProbe
"""

from __future__ import annotations

from maref.sentinel.addons.mitm_addon import SentinelMitmAddon

__all__: list[str] = [
    "SentinelMitmAddon",
]

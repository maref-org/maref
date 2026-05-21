"""
Protocols 模块

协议桥接和安全增强，支持 MCP/A2A 双向转换。
"""

from maref.protocols.protocol_bridge import (
    A2AMessage,
    A2ATask,
    BridgeDirection,
    MCPMessage,
    MCPResponse,
    ProtocolBridge,
    ProtocolBridgeMetrics,
    ProtocolType,
    SecureProtocolBridge,
    create_protocol_bridge,
    create_secure_protocol_bridge,
)

__all__ = [
    "ProtocolBridge",
    "SecureProtocolBridge",
    "MCPMessage",
    "MCPResponse",
    "A2ATask",
    "A2AMessage",
    "ProtocolType",
    "BridgeDirection",
    "ProtocolBridgeMetrics",
    "create_protocol_bridge",
    "create_secure_protocol_bridge",
]
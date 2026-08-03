"""
MCP/A2A 协议桥接器

实现 Model Context Protocol (MCP) 与 Agent-to-Agent (A2A) 协议之间的双向转换。
支持状态映射、错误处理和协议级安全增强。

协议映射:
- MCP Tool <-> A2A Task
- MCP Resource <-> A2A Artifact
- MCP Prompt <-> A2A Message
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.protocols.adapters import (
    MCPToA2AAdapter,
    ProtocolAdapter,
    create_default_adapters,
)


class ProtocolType(str, Enum):
    """协议类型"""

    MCP = "mcp"
    A2A = "a2a"


class BridgeDirection(str, Enum):
    """桥接方向"""

    MCP_TO_A2A = "mcp_to_a2a"
    A2A_TO_MCP = "a2a_to_mcp"


@dataclass
class MCPMessage:
    """MCP 消息结构"""

    message_id: str
    method: str  # "tools/call", "resources/read", "prompts/get"
    params: dict[str, Any]
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "id": self.message_id,
            "method": self.method,
            "params": self.params,
        }

    def compute_hash(self) -> str:
        """计算消息哈希"""
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()


@dataclass
class MCPResponse:
    """MCP 响应结构"""

    message_id: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self.message_id,
        }
        if self.result is not None:
            data["result"] = self.result
        if self.error is not None:
            data["error"] = self.error
        return data

    @property
    def is_error(self) -> bool:
        return self.error is not None


@dataclass
class A2ATask:
    """A2A 任务结构"""

    task_id: str
    agent_id: str
    action: str
    input_data: dict[str, Any]
    status: str = "pending"  # pending, in_progress, completed, failed
    output_data: dict[str, Any] | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()
        if self.updated_at == 0.0:
            self.updated_at = self.created_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "input": self.input_data,
            "status": self.status,
            "output": self.output_data,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


@dataclass
class A2AMessage:
    """A2A 消息结构"""

    message_id: str
    from_agent: str
    to_agent: str
    message_type: str  # task_request, task_response, status_update
    payload: dict[str, Any]
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "from": self.from_agent,
            "to": self.to_agent,
            "type": self.message_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


@dataclass
class ProtocolBridgeMetrics:
    """桥接器指标"""

    total_converted: int = 0
    errors: int = 0
    mcp_to_a2a_count: int = 0
    a2a_to_mcp_count: int = 0
    average_latency_ms: float = 0.0

    def record_conversion(
        self, direction: BridgeDirection, latency_ms: float, success: bool
    ) -> None:
        """记录转换事件"""
        self.total_converted += 1
        if not success:
            self.errors += 1

        if direction == BridgeDirection.MCP_TO_A2A:
            self.mcp_to_a2a_count += 1
        else:
            self.a2a_to_mcp_count += 1

        # 更新平均延迟
        self.average_latency_ms = (
            self.average_latency_ms * (self.total_converted - 1) + latency_ms
        ) / self.total_converted


class ProtocolBridge:
    """
    协议桥接器

    实现 MCP 和 A2A 协议之间的双向转换。
    """

    # 方法映射表（语义映射由适配器持有，此处保留类属性以向后兼容）
    MCP_TO_A2A_METHOD_MAP = MCPToA2AAdapter.METHOD_MAP

    A2A_TO_MCP_METHOD_MAP = {v: k for k, v in MCP_TO_A2A_METHOD_MAP.items()}

    def __init__(self):
        self.metrics = ProtocolBridgeMetrics()
        self._session_store: dict[str, dict[str, Any]] = {}
        self._task_to_message_map: dict[str, str] = {}  # task_id -> message_id
        self._adapters: dict[str, ProtocolAdapter] = create_default_adapters()

    # -- 适配器管理（方案 A：可插拔转换单元） --

    def adapter(self, name: str) -> ProtocolAdapter:
        """按名称获取适配器（如 mcp-to-a2a / a2a-to-mcp / asl）。"""
        if name not in self._adapters:
            raise KeyError(f"未知适配器: {name!r}")
        return self._adapters[name]

    def register_adapter(self, adapter: ProtocolAdapter) -> None:
        """注册自定义适配器（扩展新协议无需改桥层核心）。"""
        self._adapters[adapter.name] = adapter

    def list_adapters(self) -> list[str]:
        """列出已注册适配器。"""
        return sorted(self._adapters)

    def convert_mcp_to_a2a(self, mcp_message: MCPMessage, target_agent: str) -> A2ATask:
        """
        将 MCP 消息转换为 A2A 任务

        Args:
            mcp_message: MCP 消息
            target_agent: 目标 Agent ID

        Returns:
            A2ATask: 转换后的 A2A 任务
        """
        start_time = time.perf_counter()

        task = self._adapters["mcp-to-a2a"].convert(
            mcp_message, target_agent=target_agent
        )

        # 记录映射关系
        self._task_to_message_map[task.task_id] = mcp_message.message_id

        latency_ms = (time.perf_counter() - start_time) * 1000
        self.metrics.record_conversion(BridgeDirection.MCP_TO_A2A, latency_ms, True)

        return task

    def convert_a2a_to_mcp(self, a2a_task: A2ATask) -> MCPResponse:
        """
        将 A2A 任务结果转换为 MCP 响应

        Args:
            a2a_task: A2A 任务

        Returns:
            MCPResponse: MCP 响应
        """
        start_time = time.perf_counter()

        # 查找原始消息 ID
        message_id = self._task_to_message_map.get(a2a_task.task_id, a2a_task.task_id)

        response = self._adapters["a2a-to-mcp"].convert(
            a2a_task, message_id=message_id
        )

        latency_ms = (time.perf_counter() - start_time) * 1000
        self.metrics.record_conversion(BridgeDirection.A2A_TO_MCP, latency_ms, True)

        return response

    def convert_a2a_message_to_mcp(self, a2a_message: A2AMessage) -> MCPMessage:
        """
        将 A2A 消息转换为 MCP 消息

        Args:
            a2a_message: A2A 消息

        Returns:
            MCPMessage: MCP 消息
        """
        # 消息类型映射
        method = "tools/call"  # 默认映射
        if a2a_message.message_type == "fetch_artifact":
            method = "resources/read"
        elif a2a_message.message_type == "send_message":
            method = "prompts/get"

        params = {
            "agent_id": a2a_message.from_agent,
            "payload": a2a_message.payload,
            "original_type": a2a_message.message_type,
        }

        return MCPMessage(
            message_id=a2a_message.message_id,
            method=method,
            params=params,
        )

    def create_mcp_tool_request(self, tool_name: str, arguments: dict[str, Any]) -> MCPMessage:
        """创建 MCP 工具调用请求"""
        return MCPMessage(
            message_id=str(uuid.uuid4()),
            method="tools/call",
            params={
                "name": tool_name,
                "arguments": arguments,
            },
        )

    def create_a2a_task_request(
        self, agent_id: str, action: str, input_data: dict[str, Any]
    ) -> A2ATask:
        """创建 A2A 任务请求"""
        return A2ATask(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            action=action,
            input_data=input_data,
        )

    def map_error(self, source_protocol: ProtocolType, error: dict[str, Any]) -> dict[str, Any]:
        """
        错误码映射

        将源协议的错误码转换为目标协议的错误码。
        """
        if source_protocol == ProtocolType.MCP:
            # MCP 错误 -> A2A 错误
            mcp_code = error.get("code", 0)
            error_map: dict[int, dict[str, str]] = {
                -32700: {"type": "parse_error", "status": "failed"},
                -32600: {"type": "invalid_request", "status": "failed"},
                -32601: {"type": "method_not_found", "status": "failed"},
                -32602: {"type": "invalid_params", "status": "failed"},
                -32603: {"type": "internal_error", "status": "failed"},
                -32000: {"type": "task_execution_failed", "status": "failed"},
                -32001: {"type": "timeout", "status": "failed"},
            }
            return error_map.get(mcp_code, {"type": "unknown_error", "status": "failed"})

        else:
            # A2A 错误 -> MCP 错误
            a2a_type = error.get("type", "unknown")
            a2a_error_map: dict[str, dict[str, Any]] = {
                "task_execution_failed": {"code": -32000, "message": "Task execution failed"},
                "agent_not_found": {"code": -32601, "message": "Agent not found"},
                "invalid_params": {"code": -32602, "message": "Invalid parameters"},
                "timeout": {"code": -32001, "message": "Task execution timeout"},
                "parse_error": {"code": -32700, "message": "Parse error"},
                "invalid_request": {"code": -32600, "message": "Invalid request"},
                "method_not_found": {"code": -32601, "message": "Method not found"},
                "internal_error": {"code": -32603, "message": "Internal error"},
            }
            return a2a_error_map.get(a2a_type, {"code": -32603, "message": "Internal error"})

    def get_metrics(self) -> dict[str, Any]:
        """获取桥接器指标"""
        return {
            "total_converted": self.metrics.total_converted,
            "errors": self.metrics.errors,
            "mcp_to_a2a": self.metrics.mcp_to_a2a_count,
            "a2a_to_mcp": self.metrics.a2a_to_mcp_count,
            "average_latency_ms": round(self.metrics.average_latency_ms, 3),
            "error_rate": round(self.metrics.errors / self.metrics.total_converted, 3)
            if self.metrics.total_converted > 0
            else 0.0,
        }

    def generate_bridge_session(self, initiator: str, target: str) -> str:
        """生成桥接会话"""
        session_id = f"bridge-{uuid.uuid4().hex[:8]}"
        self._session_store[session_id] = {
            "initiator": initiator,
            "target": target,
            "created_at": time.time(),
            "message_count": 0,
        }
        return session_id


class SecureProtocolBridge(ProtocolBridge):
    """
    安全增强的协议桥接器

    在基础桥接器之上添加:
    - ATP 身份验证
    - 防重放攻击
    - 消息签名验证
    """

    def __init__(self):
        super().__init__()
        self._nonce_store: set[str] = set()
        self._max_nonce_age = 300  # 5分钟

    def verify_and_convert_mcp_to_a2a(
        self, mcp_message: MCPMessage, target_agent: str, agent_did: str, signature: str
    ) -> A2ATask | None:
        """
        验证身份后转换 MCP 到 A2A

        Args:
            mcp_message: MCP 消息
            target_agent: 目标 Agent
            agent_did: Agent DID
            signature: 消息签名

        Returns:
            如果验证通过返回 A2ATask，否则返回 None
        """
        # 验证签名（简化实现）
        expected_sig = hashlib.sha256(f"{agent_did}:{mcp_message.message_id}".encode()).hexdigest()

        if signature != expected_sig:
            self.metrics.record_conversion(BridgeDirection.MCP_TO_A2A, 0.0, False)
            return None

        # 检查重放
        if mcp_message.message_id in self._nonce_store:
            return None

        self._nonce_store.add(mcp_message.message_id)

        return self.convert_mcp_to_a2a(mcp_message, target_agent)

    def add_replay_protection(self, message: dict[str, Any]) -> dict[str, Any]:
        """添加防重放保护"""
        message["nonce"] = hashlib.sha256(
            f"{message.get('id', '')}:{time.time()}:{uuid.uuid4().hex}".encode()
        ).hexdigest()[:16]
        message["timestamp"] = time.time()
        return message


def create_protocol_bridge() -> ProtocolBridge:
    """创建协议桥接器"""
    return ProtocolBridge()


def create_secure_protocol_bridge() -> SecureProtocolBridge:
    """创建安全增强的协议桥接器"""
    return SecureProtocolBridge()


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

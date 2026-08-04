"""协议适配器层（方案 A 适配器化接线）。

将 MCP↔A2A 语义转换拆为可插拔的 ProtocolAdapter 单元，由 ProtocolBridge
聚合。新协议标准（如 ASL）只需新增一个 adapter，无需改动桥层核心。

设计: docs/plans/2026-08-01-agent-war-governance-design.md 方案 A（D4）
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class ProtocolKind(str, Enum):
    """支持的协议类型。ASL 为智能体安全可信互联协议（中国标准）预留。"""

    MCP = "mcp"
    A2A = "a2a"
    ASL = "asl"


class ProtocolAdapter(ABC):
    """协议语义转换适配器接口。

    每个 adapter 负责一个方向的语义映射；新协议（如 ASL）实现该接口后
    通过 :func:`register_adapter` 或工厂接入桥层。
    """

    name: str = "unnamed"
    source: ProtocolKind = ProtocolKind.MCP
    target: ProtocolKind = ProtocolKind.A2A

    @abstractmethod
    def convert(self, message: Any, **context: Any) -> Any:
        """将 source 协议消息转换为 target 协议表示。"""


class MCPToA2AAdapter(ProtocolAdapter):
    """MCP 消息 → A2A 任务（工具调用/资源读取/提示词 语义映射）。"""

    name = "mcp-to-a2a"
    source = ProtocolKind.MCP
    target = ProtocolKind.A2A

    METHOD_MAP = {
        "tools/call": "execute_task",
        "resources/read": "fetch_artifact",
        "prompts/get": "send_message",
        "tools/list": "list_capabilities",
        "resources/list": "list_artifacts",
    }

    def convert(self, message: Any, **context: Any) -> Any:
        # 延迟导入避免 adapters <-> protocol_bridge 循环依赖
        from maref.protocols.protocol_bridge import A2ATask

        target_agent = context.get("target_agent", "")
        action = self.METHOD_MAP.get(message.method, "execute_task")
        task = A2ATask(
            task_id=f"task-{message.message_id}",
            agent_id=target_agent,
            action=action,
            input_data={
                "original_method": message.method,
                "original_params": message.params,
                "source_protocol": "mcp",
                "message_hash": message.compute_hash(),
            },
            metadata={
                "source_message_id": message.message_id,
                "converted_at": time.time(),
                "bridge_version": "1.0",
                "adapter": self.name,
            },
        )
        return task


class A2AToMCPAdapter(ProtocolAdapter):
    """A2A 任务结果 → MCP 响应（状态映射 + MCP 错误码）。"""

    name = "a2a-to-mcp"
    source = ProtocolKind.A2A
    target = ProtocolKind.MCP

    def convert(self, message: Any, **context: Any) -> Any:
        from maref.protocols.protocol_bridge import MCPResponse

        message_id = context.get("message_id", message.task_id)
        if message.status == "completed":
            text = (
                json.dumps(message.output_data)
                if message.output_data is not None
                else "Task completed"
            )
            result = {
                "content": [{"type": "text", "text": text}],
                "task_status": message.status,
                "agent_id": message.agent_id,
            }
            return MCPResponse(message_id=message_id, result=result)
        if message.status == "failed":
            error = {
                "code": -32000,
                "message": "A2A task execution failed",
                "data": {
                    "task_id": message.task_id,
                    "agent_id": message.agent_id,
                    "error_details": message.output_data,
                },
            }
            return MCPResponse(message_id=message_id, error=error)
        result = {
            "status": "pending",
            "task_id": message.task_id,
        }
        return MCPResponse(message_id=message_id, result=result)


class ASLAdapter(ProtocolAdapter):
    """智能体安全可信互联协议（ASL）适配器——占位实现。

    ASL（Agent Security & Trustworthy Interconnection Protocol）为
    中国信通院主导的跨厂商智能体互信协议。接入前需确认 ASL 消息规范；
    此处保留注册槽位，convert 未实现。
    """

    name = "asl"
    source = ProtocolKind.ASL
    target = ProtocolKind.A2A

    def convert(self, message: Any, **context: Any) -> Any:
        raise NotImplementedError(
            "ASL adapter is a reserved placeholder — ASL wire spec not yet defined"
        )


_DEFAULT_ADAPTERS: dict[str, ProtocolAdapter] = {
    MCPToA2AAdapter.name: MCPToA2AAdapter(),
    A2AToMCPAdapter.name: A2AToMCPAdapter(),
    ASLAdapter.name: ASLAdapter(),
}


def create_adapter(name: str) -> ProtocolAdapter:
    """按名称创建默认适配器。"""
    if name not in _DEFAULT_ADAPTERS:
        raise KeyError(f"未知适配器: {name!r}")
    return _DEFAULT_ADAPTERS[name]


def register_adapter(adapter: ProtocolAdapter) -> None:
    """注册自定义适配器（供桥层 / 工厂全局取用）。"""
    _DEFAULT_ADAPTERS[adapter.name] = adapter


def create_default_adapters() -> dict[str, ProtocolAdapter]:
    return dict(_DEFAULT_ADAPTERS)


__all__ = [
    "ProtocolKind",
    "ProtocolAdapter",
    "MCPToA2AAdapter",
    "A2AToMCPAdapter",
    "ASLAdapter",
    "create_adapter",
    "register_adapter",
    "create_default_adapters",
]

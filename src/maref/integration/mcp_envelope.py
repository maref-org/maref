"""MCP 消息信封 — 宪法第十五-A条

所有跨 Agent MCP 通信的请求与响应必须包含:
- trace_id: UUID v4, 全链路追踪, 缺失则拒绝
- timestamp: ISO-8601, 消息时效判断
- source_agent: 调用来源, 审计责任归属
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def make_envelope(source_agent: str = "unknown") -> dict[str, str]:
    """创建标准 MCP 消息信封。"""
    return {
        "trace_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_agent": source_agent,
    }


def validate_envelope(payload: dict[str, Any]) -> tuple[bool, str]:
    """验证信封字段完整。

    Returns:
        (is_valid, error_msg) — error_msg 空表示通过
    """
    trace_id = payload.get("trace_id")
    if not trace_id:
        return False, "400 Bad Request: missing trace_id"

    try:
        uuid.UUID(str(trace_id))
    except (ValueError, AttributeError):
        return False, "400 Bad Request: trace_id is not a valid UUID v4"

    ts = payload.get("timestamp")
    source = payload.get("source_agent")
    if not ts or not source:
        return True, "missing timestamp or source_agent (degraded, continuing)"

    return True, ""


def inject_envelope(
    payload: dict[str, Any],
    source_agent: str = "unknown",
) -> dict[str, Any]:
    """向消息中注入信封字段（缺啥补啥）。"""
    result = dict(payload)
    if "trace_id" not in result:
        result["trace_id"] = str(uuid.uuid4())
    if "timestamp" not in result:
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
    if "source_agent" not in result:
        result["source_agent"] = source_agent
    return result

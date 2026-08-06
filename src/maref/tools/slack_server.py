from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx

from maref.integration.mcp_server import MCPServer
from maref.tools.tool_schema import ToolCategory, ToolDefinition, ToolParameter, ToolRiskLevel

TOOL_NAME = "slack"
TOOL_DESCRIPTION = "Slack messaging and channel management tools"

SLACK_API_BASE = "https://slack.com/api"
TIMEOUT = 30


def _get_headers() -> dict[str, str]:
    token = os.environ.get("SLACK_TOKEN")
    if not token:
        raise RuntimeError("SLACK_TOKEN environment variable not set")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _slack_send_message(channel: str, text: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                headers=_get_headers(),
                json={"channel": channel, "text": text},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                return {"isError": True, "content": [{"type": "text", "text": f"Slack error: {data.get('error', 'unknown')}"}]}
            return {
                "channel": data["channel"],
                "ts": data["ts"],
                "message": {"text": data.get("message", {}).get("text", "")},
            }
    except httpx.HTTPStatusError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"Slack API error: {exc.response.status_code}"}]}
    except httpx.RequestError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"Slack request failed: {exc}"}]}


async def _slack_list_channels() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SLACK_API_BASE}/conversations.list",
                headers=_get_headers(),
                params={"limit": 200, "exclude_archived": True},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                return {"isError": True, "content": [{"type": "text", "text": f"Slack error: {data.get('error', 'unknown')}"}]}
            return {
                "channels": [
                    {
                        "id": ch["id"],
                        "name": ch["name"],
                        "is_channel": ch.get("is_channel", False),
                        "is_private": ch.get("is_private", False),
                        "member_count": ch.get("num_members", 0),
                        "topic": ch.get("topic", {}).get("value", ""),
                    }
                    for ch in data.get("channels", [])
                ],
                "count": len(data.get("channels", [])),
            }
    except httpx.HTTPStatusError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"Slack API error: {exc.response.status_code}"}]}
    except httpx.RequestError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"Slack request failed: {exc}"}]}


async def _slack_search_messages(query: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SLACK_API_BASE}/search.messages",
                headers=_get_headers(),
                params={"query": query},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                return {"isError": True, "content": [{"type": "text", "text": f"Slack error: {data.get('error', 'unknown')}"}]}
            matches = data.get("messages", {}).get("matches", [])
            return {
                "messages": [
                    {
                        "channel": m.get("channel", {}).get("name", ""),
                        "user": m.get("username", m.get("user", "")),
                        "text": m.get("text", ""),
                        "ts": m.get("ts", ""),
                        "permalink": m.get("permalink", ""),
                    }
                    for m in matches
                ],
                "count": len(matches),
            }
    except httpx.HTTPStatusError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"Slack API error: {exc.response.status_code}"}]}
    except httpx.RequestError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"Slack request failed: {exc}"}]}


TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "slack_send_message": _slack_send_message,
    "slack_list_channels": _slack_list_channels,
    "slack_search_messages": _slack_search_messages,
}


def get_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        category=ToolCategory.CUSTOM,
        risk_level=ToolRiskLevel.MEDIUM,
        version="0.33.0",
        tools=list(TOOL_HANDLERS.keys()),
        tool_parameters={
            "slack_send_message": [
                ToolParameter(name="channel", type="string", description="Slack channel ID or name", required=True),
                ToolParameter(name="text", type="string", description="Message text", required=True),
            ],
            "slack_list_channels": [],
            "slack_search_messages": [
                ToolParameter(name="query", type="string", description="Search query", required=True),
            ],
        },
        security_controls=["EnvVarCheck"],
        default_config={},
        requires_hitl=False,
        timeout_seconds=30.0,
    )


def execute_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    import asyncio

    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}
    try:
        return asyncio.run(handler(**args))
    except RuntimeError as exc:
        return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
    except Exception as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"Execution error: {exc}"}]}


def create_slack_server() -> MCPServer:
    server = MCPServer(name="maref-slack-server", version="0.33.0")

    server.register_tool(
        name="slack_send_message",
        description="Send a message to a Slack channel",
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Slack channel ID or name"},
                "text": {"type": "string", "description": "Message text"},
            },
            "required": ["channel", "text"],
        },
        handler=lambda args: execute_tool("slack_send_message", args),
    )

    server.register_tool(
        name="slack_list_channels",
        description="List public Slack channels",
        input_schema={
            "type": "object",
            "properties": {},
        },
        handler=lambda args: execute_tool("slack_list_channels", args),
    )

    server.register_tool(
        name="slack_search_messages",
        description="Search Slack messages",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
        handler=lambda args: execute_tool("slack_search_messages", args),
    )

    return server

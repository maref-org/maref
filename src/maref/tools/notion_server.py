from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx

from maref.integration.mcp_server import MCPServer
from maref.tools.tool_schema import ToolCategory, ToolDefinition, ToolParameter, ToolRiskLevel

TOOL_NAME = "notion"
TOOL_DESCRIPTION = "Notion-like content management tools"

NOTION_API_BASE = "https://api.notion.com/v1"
TIMEOUT = 30


def _get_headers() -> dict[str, str]:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN environment variable not set")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


async def _notion_query_database(database_id: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{NOTION_API_BASE}/databases/{database_id}/query",
                headers=_get_headers(),
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            return {
                "results": [
                    {
                        "id": r["id"],
                        "url": r.get("url", ""),
                        "created_time": r.get("created_time", ""),
                        "last_edited_time": r.get("last_edited_time", ""),
                        "properties": {
                            k: v.get("title", {}).get("plain_text", "")
                            if v.get("type") == "title"
                            else v.get("rich_text", [{}])[0].get("plain_text", "")
                            if v.get("type") == "rich_text"
                            else str(v)
                            for k, v in r.get("properties", {}).items()
                        },
                    }
                    for r in results
                ],
                "count": len(results),
                "has_more": data.get("has_more", False),
            }
    except httpx.HTTPStatusError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Notion API error: {exc.response.status_code}"}],
        }
    except httpx.RequestError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Notion request failed: {exc}"}],
        }


async def _notion_create_page(database_id: str, title: str, content: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{NOTION_API_BASE}/pages",
                headers=_get_headers(),
                json={
                    "parent": {"database_id": database_id},
                    "properties": {
                        "title": {
                            "title": [{"type": "text", "text": {"content": title}}],
                        },
                    },
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"type": "text", "text": {"content": content}}],
                            },
                        }
                    ],
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            page = response.json()
            return {
                "id": page["id"],
                "url": page.get("url", ""),
                "created_time": page.get("created_time", ""),
            }
    except httpx.HTTPStatusError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Notion API error: {exc.response.status_code}"}],
        }
    except httpx.RequestError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Notion request failed: {exc}"}],
        }


async def _notion_search(query: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{NOTION_API_BASE}/search",
                headers=_get_headers(),
                json={"query": query},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            return {
                "results": [
                    {
                        "id": r["id"],
                        "type": r.get("object", ""),
                        "url": r.get("url", ""),
                    }
                    for r in results
                ],
                "count": len(results),
            }
    except httpx.HTTPStatusError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Notion API error: {exc.response.status_code}"}],
        }
    except httpx.RequestError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Notion request failed: {exc}"}],
        }


TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "notion_query_database": _notion_query_database,
    "notion_create_page": _notion_create_page,
    "notion_search": _notion_search,
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
            "notion_query_database": [
                ToolParameter(
                    name="database_id",
                    type="string",
                    description="Notion database ID",
                    required=True,
                ),
            ],
            "notion_create_page": [
                ToolParameter(
                    name="database_id",
                    type="string",
                    description="Target database ID",
                    required=True,
                ),
                ToolParameter(name="title", type="string", description="Page title", required=True),
                ToolParameter(
                    name="content", type="string", description="Page content", required=True
                ),
            ],
            "notion_search": [
                ToolParameter(
                    name="query", type="string", description="Search query", required=True
                ),
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
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
        }
    try:
        return asyncio.run(handler(**args))
    except RuntimeError as exc:
        return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
    except Exception as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"Execution error: {exc}"}]}


def create_notion_server() -> MCPServer:
    server = MCPServer(name="maref-notion-server", version="0.33.0")

    server.register_tool(
        name="notion_query_database",
        description="Query a Notion database",
        input_schema={
            "type": "object",
            "properties": {
                "database_id": {"type": "string", "description": "Notion database ID"},
            },
            "required": ["database_id"],
        },
        handler=lambda args: execute_tool("notion_query_database", args),
    )

    server.register_tool(
        name="notion_create_page",
        description="Create a page in a Notion database",
        input_schema={
            "type": "object",
            "properties": {
                "database_id": {"type": "string", "description": "Target database ID"},
                "title": {"type": "string", "description": "Page title"},
                "content": {"type": "string", "description": "Page content"},
            },
            "required": ["database_id", "title", "content"],
        },
        handler=lambda args: execute_tool("notion_create_page", args),
    )

    server.register_tool(
        name="notion_search",
        description="Search across Notion pages and databases",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
        handler=lambda args: execute_tool("notion_search", args),
    )

    return server

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx

from maref.integration.mcp_server import MCPServer
from maref.tools.tool_schema import ToolCategory, ToolDefinition, ToolParameter, ToolRiskLevel

TOOL_NAME = "jira"
TOOL_DESCRIPTION = "Jira issue tracking and project management tools"

TIMEOUT = 30


def _get_config() -> tuple[str, str]:
    token = os.environ.get("JIRA_TOKEN")
    if not token:
        raise RuntimeError("JIRA_TOKEN environment variable not set")
    jira_url = os.environ.get("JIRA_URL")
    if not jira_url:
        raise RuntimeError("JIRA_URL environment variable not set")
    return jira_url.rstrip("/"), token


def _get_headers() -> dict[str, str]:
    _, token = _get_config()
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def _jira_get_issue(issue_key: str) -> dict[str, Any]:
    try:
        base_url, _ = _get_config()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/rest/api/3/issue/{issue_key}",
                headers=_get_headers(),
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            issue = response.json()
            fields = issue.get("fields", {})
            return {
                "key": issue["key"],
                "summary": fields.get("summary", ""),
                "description": fields.get("description", ""),
                "status": fields.get("status", {}).get("name", ""),
                "assignee": fields.get("assignee", {}).get("displayName", "")
                if fields.get("assignee")
                else None,
                "reporter": fields.get("reporter", {}).get("displayName", ""),
                "priority": fields.get("priority", {}).get("name", ""),
                "issuetype": fields.get("issuetype", {}).get("name", ""),
                "created": fields.get("created", ""),
                "updated": fields.get("updated", ""),
                "url": f"{base_url}/browse/{issue['key']}",
            }
    except httpx.HTTPStatusError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Jira API error: {exc.response.status_code}"}],
        }
    except httpx.RequestError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Jira request failed: {exc}"}],
        }


async def _jira_search_issues(jql: str) -> dict[str, Any]:
    try:
        base_url, _ = _get_config()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/rest/api/3/search",
                headers=_get_headers(),
                json={"jql": jql, "maxResults": 50},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            issues = data.get("issues", [])
            return {
                "issues": [
                    {
                        "key": i["key"],
                        "summary": i.get("fields", {}).get("summary", ""),
                        "status": i.get("fields", {}).get("status", {}).get("name", ""),
                        "priority": i.get("fields", {}).get("priority", {}).get("name", ""),
                        "assignee": i.get("fields", {}).get("assignee", {}).get("displayName", "")
                        if i.get("fields", {}).get("assignee")
                        else None,
                    }
                    for i in issues
                ],
                "total": data.get("total", 0),
                "count": len(issues),
            }
    except httpx.HTTPStatusError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Jira API error: {exc.response.status_code}"}],
        }
    except httpx.RequestError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Jira request failed: {exc}"}],
        }


async def _jira_create_issue(project: str, summary: str, description: str) -> dict[str, Any]:
    try:
        base_url, _ = _get_config()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/rest/api/3/issue",
                headers=_get_headers(),
                json={
                    "fields": {
                        "project": {"key": project},
                        "summary": summary,
                        "description": {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": description}],
                                }
                            ],
                        },
                        "issuetype": {"name": "Task"},
                    }
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            issue = response.json()
            return {
                "key": issue["key"],
                "url": f"{base_url}/browse/{issue['key']}",
            }
    except httpx.HTTPStatusError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Jira API error: {exc.response.status_code}"}],
        }
    except httpx.RequestError as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Jira request failed: {exc}"}],
        }


TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "jira_get_issue": _jira_get_issue,
    "jira_search_issues": _jira_search_issues,
    "jira_create_issue": _jira_create_issue,
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
            "jira_get_issue": [
                ToolParameter(
                    name="issue_key",
                    type="string",
                    description="Jira issue key (e.g. PROJ-123)",
                    required=True,
                ),
            ],
            "jira_search_issues": [
                ToolParameter(
                    name="jql", type="string", description="JQL query string", required=True
                ),
            ],
            "jira_create_issue": [
                ToolParameter(
                    name="project", type="string", description="Project key", required=True
                ),
                ToolParameter(
                    name="summary", type="string", description="Issue summary", required=True
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="Issue description",
                    required=True,
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


def create_jira_server() -> MCPServer:
    server = MCPServer(name="maref-jira-server", version="0.33.0")

    server.register_tool(
        name="jira_get_issue",
        description="Get details of a Jira issue",
        input_schema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Jira issue key (e.g. PROJ-123)"},
            },
            "required": ["issue_key"],
        },
        handler=lambda args: execute_tool("jira_get_issue", args),
    )

    server.register_tool(
        name="jira_search_issues",
        description="Search Jira issues using JQL",
        input_schema={
            "type": "object",
            "properties": {
                "jql": {"type": "string", "description": "JQL query string"},
            },
            "required": ["jql"],
        },
        handler=lambda args: execute_tool("jira_search_issues", args),
    )

    server.register_tool(
        name="jira_create_issue",
        description="Create a new Jira issue",
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project key"},
                "summary": {"type": "string", "description": "Issue summary"},
                "description": {"type": "string", "description": "Issue description"},
            },
            "required": ["project", "summary", "description"],
        },
        handler=lambda args: execute_tool("jira_create_issue", args),
    )

    return server

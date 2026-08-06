from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import httpx

from maref.integration.mcp_server import MCPServer
from maref.tools.tool_schema import ToolCategory, ToolDefinition, ToolParameter, ToolRiskLevel

TOOL_NAME = "github"
TOOL_DESCRIPTION = "GitHub API tools for repository and issue management"

GITHUB_API_BASE = "https://api.github.com"
TIMEOUT = 30


def _get_headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN environment variable not set")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "maref-github-tool",
    }


async def _github_list_repos(username: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API_BASE}/users/{username}/repos",
                headers=_get_headers(),
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            repos = response.json()
            return {
                "repos": [
                    {
                        "name": r["name"],
                        "full_name": r["full_name"],
                        "description": r.get("description"),
                        "url": r["html_url"],
                        "stars": r["stargazers_count"],
                        "forks": r["forks_count"],
                        "language": r.get("language"),
                    }
                    for r in repos
                ],
                "count": len(repos),
            }
    except httpx.HTTPStatusError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"GitHub API error: {exc.response.status_code}"}]}
    except httpx.RequestError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"GitHub request failed: {exc}"}]}


async def _github_get_issue(owner: str, repo: str, issue_number: int) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}",
                headers=_get_headers(),
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            issue = response.json()
            return {
                "number": issue["number"],
                "title": issue["title"],
                "state": issue["state"],
                "body": issue.get("body"),
                "user": issue["user"]["login"],
                "labels": [l["name"] for l in issue.get("labels", [])],
                "comments": issue["comments"],
                "created_at": issue["created_at"],
                "updated_at": issue["updated_at"],
                "url": issue["html_url"],
            }
    except httpx.HTTPStatusError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"GitHub API error: {exc.response.status_code}"}]}
    except httpx.RequestError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"GitHub request failed: {exc}"}]}


async def _github_create_issue(owner: str, repo: str, title: str, body: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
                headers=_get_headers(),
                json={"title": title, "body": body},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            issue = response.json()
            return {
                "number": issue["number"],
                "title": issue["title"],
                "state": issue["state"],
                "url": issue["html_url"],
            }
    except httpx.HTTPStatusError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"GitHub API error: {exc.response.status_code}"}]}
    except httpx.RequestError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"GitHub request failed: {exc}"}]}


async def _github_search_code(query: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API_BASE}/search/code",
                headers=_get_headers(),
                params={"q": query},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            return {
                "total_count": data["total_count"],
                "items": [
                    {
                        "name": item["name"],
                        "path": item["path"],
                        "repository": item["repository"]["full_name"],
                        "url": item["html_url"],
                    }
                    for item in data.get("items", [])
                ],
            }
    except httpx.HTTPStatusError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"GitHub API error: {exc.response.status_code}"}]}
    except httpx.RequestError as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"GitHub request failed: {exc}"}]}


TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "github_list_repos": _github_list_repos,
    "github_get_issue": _github_get_issue,
    "github_create_issue": _github_create_issue,
    "github_search_code": _github_search_code,
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
            "github_list_repos": [
                ToolParameter(name="username", type="string", description="GitHub username", required=True),
            ],
            "github_get_issue": [
                ToolParameter(name="owner", type="string", description="Repository owner", required=True),
                ToolParameter(name="repo", type="string", description="Repository name", required=True),
                ToolParameter(name="issue_number", type="integer", description="Issue number", required=True),
            ],
            "github_create_issue": [
                ToolParameter(name="owner", type="string", description="Repository owner", required=True),
                ToolParameter(name="repo", type="string", description="Repository name", required=True),
                ToolParameter(name="title", type="string", description="Issue title", required=True),
                ToolParameter(name="body", type="string", description="Issue body", required=True),
            ],
            "github_search_code": [
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


def create_github_server() -> MCPServer:
    server = MCPServer(name="maref-github-server", version="0.33.0")

    server.register_tool(
        name="github_list_repos",
        description="List repositories for a GitHub user",
        input_schema={
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "GitHub username"},
            },
            "required": ["username"],
        },
        handler=lambda args: execute_tool("github_list_repos", args),
    )

    server.register_tool(
        name="github_get_issue",
        description="Get details of a GitHub issue",
        input_schema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "issue_number": {"type": "integer", "description": "Issue number"},
            },
            "required": ["owner", "repo", "issue_number"],
        },
        handler=lambda args: execute_tool("github_get_issue", args),
    )

    server.register_tool(
        name="github_create_issue",
        description="Create a new GitHub issue",
        input_schema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "title": {"type": "string", "description": "Issue title"},
                "body": {"type": "string", "description": "Issue body"},
            },
            "required": ["owner", "repo", "title", "body"],
        },
        handler=lambda args: execute_tool("github_create_issue", args),
    )

    server.register_tool(
        name="github_search_code",
        description="Search code on GitHub",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
        handler=lambda args: execute_tool("github_search_code", args),
    )

    return server

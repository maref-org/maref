#!/usr/bin/env python3
"""
Trae MCP Guard for MAREF Governance Integration

This MCP server intercepts tool calls from Trae/OpenCode/Cursor and performs
MAREF governance checks before allowing execution.

Usage in Trae MCP config:
{
  "mcpServers": {
    "maref-governance": {
      "command": "python3",
      "args": ["/path/to/trae_mcp_guard.py"],
      "env": {"MAREF_AGENT_ID": "trae-cn", "MAREF_SIDECAR_URL": "http://127.0.0.1:8000"}
    }
  }
}
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import uuid

import aiohttp
from mcp import ClientSession, StdioServerParameters
from mcp.server import Server, StdioServerTransport
from mcp.server.models import (
    CallToolResult,
    ListToolsResult,
    Tool,
    ToolResult,
    ToolResultContent,
)
from mcp.types import TextContent

# Configuration
MAREF_SIDECAR_URL = os.getenv("MAREF_SIDECAR_URL", "http://127.0.0.1:8000")
MAREF_AGENT_ID = os.getenv("MAREF_AGENT_ID", "trae-cn")
MAREF_API_KEY = os.getenv("MAREF_API_KEY", "default-key")  # Should be configured per tenant

# Tool mapping from Trae to MAREF governance actions
TOOL_MAPPING = {
    "write_file": "Write",
    "read_file": "Read",
    "edit_file": "Edit",
    "execute_command": "Bash",
    "search_files": "Glob",
    "search_content": "Grep",
    "create_directory": "Mkdir",
    "delete_file": "Rm",
    "move_file": "Mv",
    "copy_file": "Cp",
}

@dataclass
class GovernanceRequest:
    """Request to MAREF governance endpoint"""
    actor: str
    action: str
    tool: str
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "actor": self.actor,
            "action": self.action,
            "tool": self.tool,
            "file_path": self.file_path,
            "metadata": self.metadata or {}
        }

class MAREFGovernanceClient:
    """Client for MAREF governance checks"""
    
    def __init__(self, sidecar_url: str, api_key: str):
        self.sidecar_url = sidecar_url.rstrip("/")
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def connect(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession(
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"}
        )
        
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            
    async def check_governance(self, req: GovernanceRequest) -> Dict[str, Any]:
        """Check if action is allowed by MAREF governance"""
        if not self.session:
            await self.connect()
            
        try:
            # Try GaaS endpoint first
            url = f"{self.sidecar_url}/api/v1/gaas/govern"
            payload = {
                "tenant_id": "default",
                "actor_id": req.actor,
                "action": req.action,
                "tool": req.tool,
                "file_path": req.file_path,
                "metadata": req.metadata or {}
            }
            
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    # Fallback to compliance endpoint
                    return await self._fallback_check(req)
                else:
                    return {
                        "allowed": False,
                        "decision": "deny",
                        "reason": f"Governance service error: {response.status}",
                        "requires_hitl": False
                    }
                    
        except Exception as e:
            # If governance service is unavailable, default to allow with warning
            print(f"Warning: Governance check failed: {e}", file=sys.stderr)
            return {
                "allowed": True,
                "decision": "allow",
                "reason": "Governance service unavailable, defaulting to allow",
                "requires_hitl": False
            }
            
    async def _fallback_check(self, req: GovernanceRequest) -> Dict[str, Any]:
        """Fallback check using compliance endpoint"""
        try:
            url = f"{self.sidecar_url}/api/compliance/check-action"
            payload = {
                "agent_id": req.actor,
                "action": req.action,
                "tool": req.tool,
                "file_path": req.file_path
            }
            
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "allowed": data.get("allowed", False),
                        "decision": data.get("decision", "deny"),
                        "reason": "Compliance check",
                        "requires_hitl": False
                    }
                else:
                    return {
                        "allowed": True,  # Default to allow if service down
                        "decision": "allow",
                        "reason": "Fallback: Service unavailable",
                        "requires_hitl": False
                    }
        except:
            return {
                "allowed": True,
                "decision": "allow",
                "reason": "Emergency fallback",
                "requires_hitl": False
            }

class TraeMCPGuardServer:
    """MCP server that intercepts and governs Trae tool calls"""
    
    def __init__(self):
        self.server = Server("maref-governance")
        self.governance_client = MAREFGovernanceClient(MAREF_SIDECAR_URL, MAREF_API_KEY)
        
        # Register handlers
        self.server.list_tools()(self.handle_list_tools)
        self.server.call_tool()(self.handle_call_tool)
        
    async def handle_list_tools(self) -> ListToolsResult:
        """List tools that we can govern"""
        tools = [
            Tool(
                name="write_file",
                description="Write file with MAREF governance check",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "content": {"type": "string", "description": "File content"}
                    },
                    "required": ["path", "content"]
                }
            ),
            Tool(
                name="read_file",
                description="Read file with MAREF governance check",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"}
                    },
                    "required": ["path"]
                }
            ),
            Tool(
                name="edit_file",
                description="Edit file with MAREF governance check",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "old_string": {"type": "string", "description": "Text to replace"},
                        "new_string": {"type": "string", "description": "Replacement text"}
                    },
                    "required": ["path", "old_string", "new_string"]
                }
            ),
            Tool(
                name="execute_command",
                description="Execute command with MAREF governance check",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"}
                    },
                    "required": ["command"]
                }
            ),
        ]
        return ListToolsResult(tools=tools)
        
    async def handle_call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Handle tool call with governance check"""
        # Map tool name to MAREF action
        maref_action = TOOL_MAPPING.get(name, name)
        
        # Extract file path from arguments
        file_path = arguments.get("path") if "path" in arguments else None
        
        # Create governance request
        req = GovernanceRequest(
            actor=MAREF_AGENT_ID,
            action=maref_action,
            tool=name,
            file_path=file_path,
            metadata={"arguments": arguments}
        )
        
        # Perform governance check
        result = await self.governance_client.check_governance(req)
        
        if not result.get("allowed", False):
            # Block the action
            return CallToolResult(
                content=[
                    ToolResultContent(
                        type="text",
                        text=f"🚫 MAREF Governance Blocked: {result.get('reason', 'Action not allowed')}\n\n"
                             f"Action: {maref_action}\n"
                             f"File: {file_path or 'N/A'}\n"
                             f"Decision: {result.get('decision', 'deny')}\n"
                             f"HITL Required: {result.get('requires_hitl', False)}"
                    )
                ],
                isError=True
            )
            
        elif result.get("requires_hitl", False):
            # HITL required - prompt user
            return CallToolResult(
                content=[
                    ToolResultContent(
                        type="text",
                        text=f"⏳ MAREF HITL Required: {result.get('reason', 'Human approval needed')}\n\n"
                             f"Please approve this action in the MAREF dashboard:\n"
                             f"- Action: {maref_action}\n"
                             f"- File: {file_path or 'N/A'}\n"
                             f"- Actor: {MAREF_AGENT_ID}\n\n"
                             f"After approval, retry the action."
                    )
                ],
                isError=True
            )
        else:
            # Action allowed - execute through original tool
            # In production, this would call the actual tool implementation
            # For now, we'll just return a success message
            return CallToolResult(
                content=[
                    ToolResultContent(
                        type="text",
                        text=f"✅ MAREF Governance Approved: {result.get('reason', 'Action allowed')}\n\n"
                             f"Proceeding with execution:\n"
                             f"- Action: {maref_action}\n"
                             f"- File: {file_path or 'N/A'}\n"
                             f"- Decision: {result.get('decision', 'allow')}"
                    )
                ]
            )

async def main():
    """Main entry point for MCP server"""
    server = TraeMCPGuardServer()
    
    # Initialize governance client
    await server.governance_client.connect()
    
    # Run MCP server over stdio
    async with StdioServerTransport() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            Server.create_initialization_options()
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("MCP Guard shutting down...", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
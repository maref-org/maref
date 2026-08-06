#!/usr/bin/env python3
"""
Simple MCP Guard for testing MAREF governance integration.

This is a minimal MCP server that demonstrates the integration pattern.
It logs all tool calls and simulates governance checks.

Run with: python3 simple_mcp_guard.py
"""

import json
import sys
import os
from typing import Any, Dict, List

# Simple MCP server implementation
class SimpleMCPServer:
    def __init__(self):
        self.tools = [
            {
                "name": "write_file",
                "description": "Write file with MAREF governance logging",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "read_file", 
                "description": "Read file with MAREF governance logging",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            }
        ]
        
    def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP initialize request"""
        return {
            "jsonrpc": "2.0",
            "id": params.get("id"),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": "MAREF Simple MCP Guard",
                    "version": "0.1.0"
                }
            }
        }
        
    def handle_list_tools(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle listTools request"""
        return {
            "jsonrpc": "2.0",
            "id": params.get("id"),
            "result": {
                "tools": self.tools
            }
        }
        
    def handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle callTool request with governance logging"""
        tool_name = params["params"]["name"]
        arguments = params["params"]["arguments"]
        
        # Log the tool call for governance
        self._log_governance_check(tool_name, arguments)
        
        # Simulate governance check
        allowed, reason = self._simulate_governance(tool_name, arguments)
        
        if not allowed:
            return {
                "jsonrpc": "2.0",
                "id": params.get("id"),
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"🚫 MAREF Governance Blocked: {reason}"
                        }
                    ],
                    "isError": True
                }
            }
        
        # Return success (simulated)
        return {
            "jsonrpc": "2.0",
            "id": params.get("id"),
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": f"✅ MAREF Governance Approved: {reason}\n\n"
                               f"Tool: {tool_name}\n"
                               f"Arguments: {json.dumps(arguments, indent=2)}"
                    }
                ]
            }
        }
    
    def _log_governance_check(self, tool_name: str, arguments: Dict[str, Any]):
        """Log governance check to file"""
        log_entry = {
            "tool": tool_name,
            "arguments": arguments,
            "timestamp": time.time(),
            "agent_id": os.getenv("MAREF_AGENT_ID", "unknown"),
            "sidecar_url": os.getenv("MAREF_SIDECAR_URL", "http://127.0.0.1:8000")
        }
        
        log_file = Path.home() / ".maref_mcp_guard.log"
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        print(f"[MCP Guard] Tool call: {tool_name}", file=sys.stderr)
        print(f"[MCP Guard] Arguments: {arguments}", file=sys.stderr)
    
    def _simulate_governance(self, tool_name: str, arguments: Dict[str, Any]) -> tuple[bool, str]:
        """Simulate governance check logic"""
        # Simple rules for demonstration
        if tool_name == "write_file":
            path = arguments.get("path", "")
            if "/etc/" in path or "/root/" in path:
                return False, "Writing to system directories not allowed"
            if path.endswith(".pem") or path.endswith(".key"):
                return False, "Writing cryptographic keys requires HITL approval"
            return True, "File write allowed"
        
        elif tool_name == "read_file":
            path = arguments.get("path", "")
            if "/etc/passwd" in path or "/etc/shadow" in path:
                return False, "Reading sensitive system files not allowed"
            return True, "File read allowed"
        
        return True, "Default allow"

import time
from pathlib import Path

def main():
    """Main stdio loop for MCP server"""
    server = SimpleMCPServer()
    
    print("MAREF Simple MCP Guard starting...", file=sys.stderr)
    print(f"Agent ID: {os.getenv('MAREF_AGENT_ID', 'not-set')}", file=sys.stderr)
    print(f"Sidecar URL: {os.getenv('MAREF_SIDECAR_URL', 'not-set')}", file=sys.stderr)
    
    try:
        while True:
            # Read JSON-RPC message from stdin
            line = sys.stdin.readline()
            if not line:
                break
                
            try:
                message = json.loads(line.strip())
                method = message.get("method")
                
                # Handle different MCP methods
                if method == "initialize":
                    response = server.handle_initialize(message)
                elif method == "tools/list":
                    response = server.handle_list_tools(message)
                elif method == "tools/call":
                    response = server.handle_call_tool(message)
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}"
                        }
                    }
                
                # Write response to stdout
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error processing message: {e}", file=sys.stderr)
                error_response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id") if 'message' in locals() else None,
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()
                
    except KeyboardInterrupt:
        print("MCP Guard shutting down...", file=sys.stderr)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
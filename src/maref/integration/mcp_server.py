from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maref.integration.mcp_transport import (
    InProcessTransport,
    JSONRPCRequest,
    JSONRPCResponse,
    MCP_JSONRPC_VERSION,
)


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class MCPResource:
    uri: str
    name: str
    mime_type: str
    handler: Callable[[str], dict[str, Any]]


@dataclass
class MCPPrompt:
    name: str
    description: str
    arguments: list[dict[str, Any]]
    handler: Callable[[dict[str, Any]], dict[str, Any]]


class MCPServer:
    """MCP Server 实现。

    支持 Tools、Resources、Prompts 端点，可与安全门集成。
    """

    def __init__(
        self,
        name: str = "maref-mcp-server",
        version: str = "0.25.0",
        security_gate: "Any | None" = None,
    ) -> None:
        self.name = name
        self.version = version
        self.security_gate = security_gate
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
        self._prompts: dict[str, MCPPrompt] = {}
        self._inprocess_transport: InProcessTransport | None = None

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self._tools[name] = MCPTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )

    def register_resource(
        self,
        uri: str,
        name: str,
        mime_type: str,
        handler: Callable[[str], dict[str, Any]],
    ) -> None:
        self._resources[uri] = MCPResource(
            uri=uri,
            name=name,
            mime_type=mime_type,
            handler=handler,
        )

    def register_prompt(
        self,
        name: str,
        description: str,
        arguments: list[dict[str, Any]],
        handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self._prompts[name] = MCPPrompt(
            name=name,
            description=description,
            arguments=arguments,
            handler=handler,
        )

    def handle_request(
        self,
        request: JSONRPCRequest,
        trust_level: "Any | None" = None,
    ) -> JSONRPCResponse:
        method = request.method
        params = request.params or {}

        if method == "initialize":
            return self._handle_initialize(request.id, params)
        elif method == "tools/list":
            return self._handle_tools_list(request.id)
        elif method == "tools/call":
            return self._handle_tools_call(request.id, params, trust_level)
        elif method == "resources/list":
            return self._handle_resources_list(request.id)
        elif method == "resources/read":
            return self._handle_resources_read(request.id, params)
        elif method == "prompts/list":
            return self._handle_prompts_list(request.id)
        elif method == "prompts/get":
            return self._handle_prompts_get(request.id, params)
        else:
            return JSONRPCResponse(
                error={"code": -32601, "message": f"Method not found: {method}"},
                id=request.id,
            )

    def _handle_initialize(self, req_id: int | str, params: dict[str, Any]) -> JSONRPCResponse:
        client_info = params.get("clientInfo", {})
        protocol_version = params.get("protocolVersion", "2024-11-05")
        return JSONRPCResponse(
            result={
                "protocolVersion": protocol_version,
                "capabilities": {},
                "serverInfo": {"name": self.name, "version": self.version},
            },
            id=req_id,
        )

    def _handle_tools_list(self, req_id: int | str) -> JSONRPCResponse:
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]
        return JSONRPCResponse(result={"tools": tools}, id=req_id)

    def _handle_tools_call(
        self,
        req_id: int | str,
        params: dict[str, Any],
        trust_level: Any | None,
    ) -> JSONRPCResponse:
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._tools:
            return JSONRPCResponse(
                error={"code": -32602, "message": f"Unknown tool: {tool_name}"},
                id=req_id,
            )

        # 安全门检查
        if self.security_gate is not None and trust_level is not None:
            verdict = self.security_gate.check(tool_name, trust_level, arguments)
            if verdict.value == "DENY":
                return JSONRPCResponse(
                    error={"code": -32000, "message": f"Tool blocked by security gate: {tool_name}"},
                    id=req_id,
                )

        try:
            result = self._tools[tool_name].handler(arguments)
            return JSONRPCResponse(result=result, id=req_id)
        except Exception as e:
            return JSONRPCResponse(
                error={"code": -32603, "message": f"Tool execution error: {e}"},
                id=req_id,
            )

    def _handle_resources_list(self, req_id: int | str) -> JSONRPCResponse:
        resources = [
            {
                "uri": res.uri,
                "name": res.name,
                "mimeType": res.mime_type,
            }
            for res in self._resources.values()
        ]
        return JSONRPCResponse(result={"resources": resources}, id=req_id)

    def _handle_resources_read(self, req_id: int | str, params: dict[str, Any]) -> JSONRPCResponse:
        uri = params.get("uri", "")
        if uri not in self._resources:
            return JSONRPCResponse(
                error={"code": -32602, "message": f"Unknown resource: {uri}"},
                id=req_id,
            )
        try:
            result = self._resources[uri].handler(uri)
            return JSONRPCResponse(result=result, id=req_id)
        except Exception as e:
            return JSONRPCResponse(
                error={"code": -32603, "message": f"Resource read error: {e}"},
                id=req_id,
            )

    def _handle_prompts_list(self, req_id: int | str) -> JSONRPCResponse:
        prompts = [
            {
                "name": prompt.name,
                "description": prompt.description,
                "arguments": prompt.arguments,
            }
            for prompt in self._prompts.values()
        ]
        return JSONRPCResponse(result={"prompts": prompts}, id=req_id)

    def _handle_prompts_get(self, req_id: int | str, params: dict[str, Any]) -> JSONRPCResponse:
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        if name not in self._prompts:
            return JSONRPCResponse(
                error={"code": -32602, "message": f"Unknown prompt: {name}"},
                id=req_id,
            )
        try:
            result = self._prompts[name].handler(arguments)
            return JSONRPCResponse(result=result, id=req_id)
        except Exception as e:
            return JSONRPCResponse(
                error={"code": -32603, "message": f"Prompt execution error: {e}"},
                id=req_id,
            )

    def get_inprocess_transport(self) -> InProcessTransport:
        if self._inprocess_transport is None:
            self._inprocess_transport = InProcessTransport(message_handler=self.handle_request)
        return self._inprocess_transport

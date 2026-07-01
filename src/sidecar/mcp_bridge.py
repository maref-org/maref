from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sidecar.protocol import AgentId, Observation

_CM_PREFIX = "claude_mem_"


@dataclass
class MCPResourceURI:
    scheme: str = "maref"
    resource_type: str = "agents"
    namespace: str = "default"
    name: str = ""
    instance: str = ""

    def to_uri(self) -> str:
        base = f"{self.scheme}://{self.resource_type}/{self.namespace}/{self.name}"
        if self.instance:
            return f"{base}#{self.instance}"
        return base

    @classmethod
    def from_agent_id(cls, agent: AgentId) -> MCPResourceURI:
        return cls(
            namespace=agent.namespace,
            name=agent.name,
            instance=agent.instance,
        )

    @classmethod
    def from_observation(cls, obs: Observation) -> MCPResourceURI:
        obs_type = obs.obs_type.name.lower() if obs.obs_type else "unknown"
        return cls(
            resource_type=f"observations/{obs_type}",
            namespace="default",
            name=obs.source,
        )


@dataclass
class MCPToolDefinition:
    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


SIDECAR_MCP_TOOLS: list[MCPToolDefinition] = [
    MCPToolDefinition(
        name="maref_observe_agent",
        description="Observe a specific agent's state",
        input_schema={"type": "object", "properties": {"agent_id": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="maref_read_entropy",
        description="Read entropy reading for an agent",
        input_schema={"type": "object", "properties": {"agent_id": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="maref_read_observations",
        description="Read recent observations",
        input_schema={"type": "object", "properties": {"count": {"type": "integer"}}},
    ),
    MCPToolDefinition(
        name="maref_read_anomalies",
        description="Read recent anomalies",
        input_schema={"type": "object", "properties": {"count": {"type": "integer"}}},
    ),
    MCPToolDefinition(
        name="maref_compliance_check",
        description="Check compliance for an action",
        input_schema={"type": "object", "properties": {"agent_id": {"type": "string"}, "action": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="maref_ingest_signal",
        description="Ingest a signal from external source",
        input_schema={"type": "object", "properties": {"signal_type": {"type": "string"}, "payload": {"type": "object"}, "source": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="maref_list_agents",
        description="List all registered agents",
        input_schema={"type": "object", "properties": {}},
    ),
    MCPToolDefinition(
        name="maref_get_snapshot",
        description="Get full state snapshot",
        input_schema={"type": "object", "properties": {"agent_id": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="maref_health_check",
        description="Check sidecar health",
        input_schema={"type": "object", "properties": {"detail": {"type": "boolean"}}},
    ),
    MCPToolDefinition(
        name="maref_get_correlation",
        description="Get correlation data",
        input_schema={"type": "object", "properties": {"source": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="maref_migrate",
        description="Migrate agent to new state",
        input_schema={"type": "object", "properties": {"agent_id": {"type": "string"}, "target_state": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="maref_verifier_list",
        description="List all registered verifiers",
        input_schema={"type": "object", "properties": {}},
    ),
    MCPToolDefinition(
        name="maref_verifier_check",
        description="Run consensus check via verifiers",
        input_schema={"type": "object", "properties": {"action": {"type": "string"}, "context": {"type": "object"}}},
    ),
    MCPToolDefinition(
        name="maref_verifier_history",
        description="Get verifier evaluation history",
        input_schema={"type": "object", "properties": {}},
    ),
    MCPToolDefinition(
        name="maref_health_check",
        description="Check sidecar health",
        input_schema={"type": "object", "properties": {}},
    ),
    MCPToolDefinition(
        name="maref_run_evolution",
        description="Trigger a single evolution run with the specified engine",
        input_schema={
            "type": "object",
            "properties": {
                "engine": {"type": "string", "enum": ["daily", "rel", "multi", "continuous", "saeb", "tla"]},
                "dry_run": {"type": "boolean"},
            },
        },
    ),
    MCPToolDefinition(
        name="maref_get_evolution_status",
        description="Get current evolution daemon status (last run, total runs, failures)",
        input_schema={"type": "object", "properties": {}},
    ),
    MCPToolDefinition(
        name="maref_list_evolution_results",
        description="List recent evolution run results from vault",
        input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
    ),
]

SIDECAR_MCP_RESOURCES: list[dict[str, Any]] = [
    {"uri": "maref://agents", "name": "All Agents", "mimeType": "application/json"},
    {"uri": "maref://observations", "name": "Recent Observations", "mimeType": "application/json"},
    {"uri": "maref://anomalies", "name": "Recent Anomalies", "mimeType": "application/json"},
    {"uri": "maref://governance/decisions", "name": "Governance Decisions", "mimeType": "application/json"},
]

# ── claude-mem 工具前缀 ─────────────────────────────────────

_CM_TOOL_MAP: dict[str, MCPToolDefinition] = {}  # prefixed_name → def, lazy-populated


def _build_cm_tool_map(cm_tools_raw: list[dict[str, Any]]) -> dict[str, MCPToolDefinition]:
    """将 claude-mem 工具加上 claude_mem_ 前缀并缓存。"""
    result: dict[str, MCPToolDefinition] = {}
    for t in cm_tools_raw:
        raw_name = t.get("name", "")
        if not raw_name:
            continue
        prefixed = _CM_PREFIX + raw_name
        result[prefixed] = MCPToolDefinition(
            name=prefixed,
            description=t.get("description", f"claude-mem: {raw_name}"),
            input_schema=t.get("inputSchema", t.get("input_schema", {"type": "object", "properties": {}})),
        )
    return result


def _strip_cm_prefix(prefixed: str) -> str:
    """去掉 claude_mem_ 前缀获取原始工具名。"""
    if prefixed.startswith(_CM_PREFIX):
        return prefixed[len(_CM_PREFIX):]
    return prefixed


class MCPBridge:
    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok"}


class MCPGovernanceInterceptor:
    async def intercept(self, request: dict[str, Any]) -> dict[str, Any]:
        return request


_CD_TOOLS: list[MCPToolDefinition] = [
    MCPToolDefinition(
        name="depth_symbol_search",
        description="Search symbols in codebase by name pattern",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "kind": {"type": "string"}, "limit": {"type": "integer"}}},
    ),
    MCPToolDefinition(
        name="depth_file_outline",
        description="Get structured symbol outline for a file",
        input_schema={"type": "object", "properties": {"file_path": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="depth_call_graph",
        description="Show callers and callees for a symbol",
        input_schema={"type": "object", "properties": {"symbol_name": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="depth_imports",
        description="Show import dependencies for a file",
        input_schema={"type": "object", "properties": {"file_path": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="depth_references",
        description="Find all references to a symbol across the codebase",
        input_schema={"type": "object", "properties": {"symbol_name": {"type": "string"}}},
    ),
    MCPToolDefinition(
        name="depth_stats",
        description="Code index statistics",
        input_schema={"type": "object", "properties": {}},
    ),
]

_CD_TOOL_NAMES = {t.name for t in _CD_TOOLS}


class SidecarMCPBridge:
    def __init__(self, exfiltration_probe: Any | None = None, repo_path: str | None = None) -> None:
        self._probe = exfiltration_probe
        self._repo_path = repo_path
        self._cm_backend: Any | None = None  # ClaudeMemBackend, lazy-imported
        self._cd_indexer: Any | None = None  # CodeIndexer, lazy-imported

    def _get_cm_backend(self) -> Any | None:
        """延迟导入并返回 ClaudeMemBackend 实例。"""
        if self._cm_backend is None:
            try:
                from sidecar.claude_mem_adapter import ClaudeMemBackend as _CMB  # noqa: N814
                backend = _CMB()
                if backend.available:
                    backend.start()
                    self._cm_backend = backend
                    global _CM_TOOL_MAP
                    _CM_TOOL_MAP = _build_cm_tool_map(backend.list_tools())
            except Exception:
                pass
        return self._cm_backend

    def _get_cd_indexer(self) -> Any | None:
        """延迟导入并返回 CodeIndexer 实例。"""
        if self._cd_indexer is None:
            try:
                from maref.codedepth.indexer import CodeIndexer

                idx = CodeIndexer(self._repo_path)
                if idx.is_built or idx.build().get("files", 0) > 0:
                    self._cd_indexer = idx
            except Exception:
                pass
        return self._cd_indexer

    def get_server_info(self) -> dict[str, Any]:
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "MAREF Sidecar", "version": "0.32.0-rc"},
            "capabilities": self.get_capabilities(),
        }

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "tools": {},
            "resources": {},
            "prompts": {},
        }

    def list_tools(self) -> list[dict[str, Any]]:
        """合并 sidecar 工具 + claude-mem 工具 + codedepth 工具列表。"""
        self._get_cm_backend()
        self._get_cd_indexer()
        tools = [t.to_dict() for t in SIDECAR_MCP_TOOLS]
        for _prefixed, tdef in _CM_TOOL_MAP.items():
            tools.append(tdef.to_dict())
        for tdef in _CD_TOOLS:
            tools.append(tdef.to_dict())
        return tools

    def list_resources(self) -> list[dict[str, Any]]:
        return SIDECAR_MCP_RESOURCES

    def list_prompts(self) -> list[dict[str, Any]]:
        return [
            {"name": "maref_compliance_snapshot", "description": "Compliance snapshot prompt"},
            {"name": "maref_governance_overview", "description": "Governance overview prompt"},
        ]

    def handle_tool_call(self, name: str, args: dict[str, Any], trace_id: str | None = None) -> dict[str, Any]:
        """路由工具调用 — sidecar 工具直连，claude-mem 工具转发到后端。"""
        # claude-mem 工具路由
        if name.startswith(_CM_PREFIX):
            backend = self._get_cm_backend()
            if backend is None:
                result: dict[str, Any] = {
                    "isError": True,
                    "content": [{"type": "text", "text": "claude-mem backend unavailable. Is the plugin installed?"}],
                }
            else:
                raw_name = _strip_cm_prefix(name)
                result = backend.call_tool(raw_name, args)
            if trace_id:
                result["_trace_id"] = trace_id
            return result

        # codedepth 工具路由
        if name in _CD_TOOL_NAMES:
            idx = self._get_cd_indexer()
            if idx is None:
                result = {
                    "isError": True,
                    "content": [{"type": "text", "text": "CodeDepth indexer unavailable"}],
                }
            else:
                result = {"content": [{"type": "text", "text": self._route_cd(name, args)}]}
            if trace_id:
                result["_trace_id"] = trace_id
            return result

        # sidecar 内置工具
        tool_names = {t.name for t in SIDECAR_MCP_TOOLS}
        if name not in tool_names:
            result = {
                "isError": True,
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            }
        elif name == "maref_run_evolution":
            result = self._handle_evolution_run(args)
        elif name == "maref_get_evolution_status":
            result = self._handle_evolution_status(args)
        elif name == "maref_list_evolution_results":
            result = self._handle_evolution_results(args)
        else:
            result = {
                "content": [{"type": "text", "text": f"Tool {name} executed"}],
            }
        if trace_id:
            result["_trace_id"] = trace_id
        return result

    def _route_cd(self, name: str, args: dict[str, Any]) -> str:
        """路由 codedepth 工具调用，返回 JSON 字符串。"""
        import json

        idx = self._cd_indexer
        if not idx:
            return json.dumps({"error": "Indexer not available"})
        try:
            if name == "depth_stats":
                return json.dumps(idx.get_stats())
            if name == "depth_symbol_search":
                return json.dumps(idx.search_symbols(
                    query=args.get("query", ""),
                    kind=args.get("kind"),
                    limit=args.get("limit", 50),
                ))
            if name == "depth_file_outline":
                return json.dumps(idx.get_file_outline(args.get("file_path", "")))
            if name == "depth_call_graph":
                return json.dumps(idx.get_call_graph(args.get("symbol_name", "")))
            if name == "depth_imports":
                return json.dumps(idx.get_imports(args.get("file_path", "")))
            if name == "depth_references":
                return json.dumps(idx.get_references(args.get("symbol_name", "")))
            return json.dumps({"error": f"Unknown codedepth tool: {name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _handle_evolution_run(self, args: dict[str, Any]) -> dict[str, Any]:
        import json
        try:
            from maref.evolution.daemon import DaemonConfig, EvolutionDaemon
            engine = args.get("engine", "daily")
            dry_run = args.get("dry_run", True)
            config = DaemonConfig(engine=engine, dry_run=dry_run, max_runs=1)
            daemon = EvolutionDaemon(config)
            result = daemon._loop.run_once()
            return {
                "content": [{"type": "text", "text": json.dumps(result.to_dict() if result else {"error": "no result"}, indent=2)}],
            }
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Evolution run failed: {e}"}]}

    def _handle_evolution_status(self, args: dict[str, Any]) -> dict[str, Any]:
        import json
        try:
            state_path = ".evolution_daemon_state.json"
            import os
            if os.path.exists(state_path):
                data = json.loads(open(state_path).read())
            else:
                data = {"last_run": "", "total_runs": 0, "failed_runs": 0}
            return {
                "content": [{"type": "text", "text": json.dumps(data, indent=2)}],
            }
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Status check failed: {e}"}]}

    def _handle_evolution_results(self, args: dict[str, Any]) -> dict[str, Any]:
        import json
        import os
        try:
            limit = args.get("limit", 10)
            vault_dir = ".evolution_vault"
            if not os.path.isdir(vault_dir):
                return {"content": [{"type": "text", "text": "[]"}]}
            results = sorted(os.listdir(vault_dir), reverse=True)[:limit]
            return {
                "content": [{"type": "text", "text": json.dumps(results, indent=2)}],
            }
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"List results failed: {e}"}]}

    def close(self) -> None:
        """释放后端资源。"""
        if self._cm_backend is not None:
            try:
                self._cm_backend.stop()
            except Exception:
                pass
            self._cm_backend = None
        if self._cd_indexer is not None:
            try:
                self._cd_indexer.close()
            except Exception:
                pass
            self._cd_indexer = None

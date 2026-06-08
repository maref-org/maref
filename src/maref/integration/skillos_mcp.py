#!/usr/bin/env python3
"""
SKILLOS MCP Integration — Expose SKILLOS capabilities as MCP Tools/Resources.

This module bridges SKILLOS (Skill-based Orchestration for Intelligent Life-cycle
Operations System) with the MCP protocol, enabling:
  - SKILLOS Skills as MCP Tools (discoverable and callable)
  - SKILLOS Agent State as MCP Resources (monitorable)
  - SKILLOS Skill Metadata as MCP Prompts (template-based execution)

Usage:
    from maref.integration.skillos_mcp import SKILLOSMCPServer

    server = SKILLOSMCPServer()
    server.register_skill("search", search_skill_handler)
    server.register_agent_state("agent-1", get_agent_state)

    # Use with MCPServer
    mcp_server = server.build_mcp_server()
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maref.integration.mcp_server import MCPServer
from maref.recursive.skill_executor import ExecutionResult, ExecutionStatus, SkillExecutor
from maref.recursive.skill_schema import MarefSkill


@dataclass
class SKILLOSAgentState:
    """State of a SKILLOS agent exposed via MCP Resource."""

    agent_id: str
    current_state: str
    active_skill: str | None = None
    skill_queue: list[str] = field(default_factory=list)
    trust_score: float = 0.0
    last_updated: float = field(default_factory=time.time)
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "current_state": self.current_state,
            "active_skill": self.active_skill,
            "skill_queue": self.skill_queue,
            "trust_score": self.trust_score,
            "last_updated": self.last_updated,
            "metrics": self.metrics,
        }


@dataclass
class SKILLOSSkillTool:
    """A SKILLOS skill wrapped as an MCP Tool."""

    skill_id: str
    skill_def: MarefSkill
    handler: Callable[[dict[str, Any]], Any]
    executor: SkillExecutor
    input_schema: dict[str, Any] = field(default_factory=dict)
    last_execution: ExecutionResult | None = None

    def to_mcp_tool_def(self) -> dict[str, Any]:
        return {
            "name": f"skillos.{self.skill_id}",
            "description": self.skill_def.meta.description,
            "inputSchema": self.input_schema or self._default_input_schema(),
        }

    def _default_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Input for the skill execution",
                },
                "context": {
                    "type": "object",
                    "description": "Optional context parameters",
                },
            },
            "required": ["input"],
        }


class SKILLOSMCPServer:
    """
    Bridges SKILLOS skills and agent state with MCP protocol.

    This server:
    1. Registers SKILLOS skills as MCP tools
    2. Exposes agent state as MCP resources
    3. Provides skill metadata as MCP prompts
    4. Integrates with MCP security gate
    """

    def __init__(
        self,
        name: str = "skillos-mcp-bridge",
        version: str = "0.30.0",
        security_gate: Any | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.security_gate = security_gate
        self._skills: dict[str, SKILLOSSkillTool] = {}
        self._agent_states: dict[str, Callable[[], SKILLOSAgentState]] = {}
        self._mcp_server: MCPServer | None = None

    def register_skill(
        self,
        skill_id: str,
        skill_def: MarefSkill,
        handler: Callable[[dict[str, Any]], Any],
        executor: SkillExecutor | None = None,
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        """Register a SKILLOS skill as an MCP tool."""
        self._skills[skill_id] = SKILLOSSkillTool(
            skill_id=skill_id,
            skill_def=skill_def,
            handler=handler,
            executor=executor or SkillExecutor(),
            input_schema=input_schema or {},
        )

    def register_agent_state(
        self,
        agent_id: str,
        state_provider: Callable[[], SKILLOSAgentState],
    ) -> None:
        """Register an agent state provider as an MCP resource."""
        self._agent_states[agent_id] = state_provider

    def build_mcp_server(self) -> MCPServer:
        """Build and configure an MCPServer with all registered skills and resources."""
        if self._mcp_server is None:
            self._mcp_server = MCPServer(
                name=self.name,
                version=self.version,
                security_gate=self.security_gate,
            )
            self._register_all_tools()
            self._register_all_resources()
            self._register_all_prompts()
        return self._mcp_server

    def get_skill_execution_history(self) -> dict[str, Any]:
        """Get execution history for all registered skills."""
        history = {}
        for skill_id, skill_tool in self._skills.items():
            if skill_tool.last_execution:
                history[skill_id] = {
                    "status": skill_tool.last_execution.status.value,
                    "handler_used": skill_tool.last_execution.handler_used,
                    "duration_ms": skill_tool.last_execution.duration_ms,
                    "execution_id": skill_tool.last_execution.execution_id,
                }
        return history

    def get_capabilities_summary(self) -> dict[str, Any]:
        """Get a summary of all exposed capabilities."""
        return {
            "tools": list(self._skills.keys()),
            "resources": list(self._agent_states.keys()),
            "prompts": [f"skill_template:{skill_id}" for skill_id in self._skills],
        }

    def _register_all_tools(self) -> None:
        """Register all skills as MCP tools."""
        mcp_server = self.build_mcp_server()
        for skill_id, skill_tool in self._skills.items():
            tool_name = f"skillos.{skill_id}"
            mcp_server.register_tool(
                name=tool_name,
                description=skill_tool.skill_def.meta.description,
                input_schema=skill_tool.input_schema or skill_tool._default_input_schema(),
                handler=self._create_tool_handler(skill_tool),
            )

    def _register_all_resources(self) -> None:
        """Register all agent states as MCP resources."""
        mcp_server = self.build_mcp_server()
        for agent_id in self._agent_states:
            uri = f"skillos://agent/{agent_id}/state"
            mcp_server.register_resource(
                uri=uri,
                name=f"Agent {agent_id} State",
                mime_type="application/json",
                handler=self._create_resource_handler(agent_id),
            )

    def _register_all_prompts(self) -> None:
        """Register skill templates as MCP prompts."""
        mcp_server = self.build_mcp_server()
        for skill_id, skill_tool in self._skills.items():
            prompt_name = f"skill_template:{skill_id}"
            mcp_server.register_prompt(
                name=prompt_name,
                description=f"Template for executing skill: {skill_tool.skill_def.meta.name}",
                arguments=[
                    {
                        "name": "input",
                        "description": "Input for the skill",
                        "required": True,
                    },
                ],
                handler=self._create_prompt_handler(skill_tool),
            )

    def _create_tool_handler(
        self,
        skill_tool: SKILLOSSkillTool,
    ) -> Callable[[dict[str, Any]], dict[str, Any]]:
        """Create an MCP tool handler for a SKILLOS skill."""
        def handler(args: dict[str, Any]) -> dict[str, Any]:
            start_time = time.time()
            try:
                result = skill_tool.handler(args)
                duration_ms = (time.time() - start_time) * 1000
                execution_result = ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    handler_used=skill_tool.skill_id,
                    result=result,
                    duration_ms=duration_ms,
                )
                skill_tool.last_execution = execution_result
                return {
                    "ok": True,
                    "result": result,
                    "execution": execution_result.__dict__,
                }
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                execution_result = ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    handler_used=skill_tool.skill_id,
                    error=str(e),
                    duration_ms=duration_ms,
                )
                skill_tool.last_execution = execution_result
                return {
                    "ok": False,
                    "error": str(e),
                    "execution": execution_result.__dict__,
                }
        return handler

    def _create_resource_handler(
        self,
        agent_id: str,
    ) -> Callable[[str], dict[str, Any]]:
        """Create an MCP resource handler for an agent state."""
        def handler(uri: str) -> dict[str, Any]:
            state_provider = self._agent_states.get(agent_id)
            if state_provider is None:
                return {"error": f"Agent {agent_id} not found"}
            state = state_provider()
            return state.to_dict()
        return handler

    def _create_prompt_handler(
        self,
        skill_tool: SKILLOSSkillTool,
    ) -> Callable[[dict[str, Any]], dict[str, Any]]:
        """Create an MCP prompt handler for a skill template."""
        def handler(args: dict[str, Any]) -> dict[str, Any]:
            skill_meta = skill_tool.skill_def.meta
            return {
                "skill_id": skill_tool.skill_id,
                "skill_name": skill_meta.name,
                "description": skill_meta.description,
                "version": skill_meta.version,
                "source": skill_tool.skill_def.source.value if skill_tool.skill_def.source else "unknown",
                "role_affinity": skill_tool.skill_def.role_affinity,
                "template": {
                    "input": args.get("input", ""),
                    "context": {},
                },
            }
        return handler


# Factory function
def create_skillos_mcp_bridge(
    skills: list[tuple[str, MarefSkill, Callable]] | None = None,
    agent_states: dict[str, Callable[[], SKILLOSAgentState]] | None = None,
    security_gate: Any | None = None,
) -> SKILLOSMCPServer:
    """Create a SKILLOS MCP bridge with pre-registered skills and agent states."""
    server = SKILLOSMCPServer(security_gate=security_gate)

    if skills:
        for skill_id, skill_def, handler in skills:
            server.register_skill(skill_id, skill_def, handler)

    if agent_states:
        for agent_id, state_provider in agent_states.items():
            server.register_agent_state(agent_id, state_provider)

    return server

#!/usr/bin/env python3
"""
SKILLOS MCP Integration — Phase of Evolution Daily Loop

This script integrates SKILLOS capabilities with the daily evolution loop:
1. Exposes SKILLOS skills as MCP tools
2. Registers agent states as MCP resources
3. Runs a smoke test to verify MCP connectivity
4. Outputs integration status report

Usage:
    python -m maref.integration.skillos_mcp_daily \
        --output-file ./research_output/integration/skillos_mcp_daily.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maref.integration.skillos_mcp import (
    SKILLOSAgentState,
    create_skillos_mcp_bridge,
)
from maref.recursive.skill_schema import MarefSkill, MarefSkillMeta, SkillSource


@dataclass
class SKILLOSMCPDailyResult:
    """Result of daily SKILLOS MCP integration check."""

    timestamp: str
    status: str  # "ok", "partial", "failed"
    skills_registered: int = 0
    agents_registered: int = 0
    smoke_test_passed: bool = False
    capabilities: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "status": self.status,
            "skills_registered": self.skills_registered,
            "agents_registered": self.agents_registered,
            "smoke_test_passed": self.smoke_test_passed,
            "capabilities": self.capabilities,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


def create_default_skills() -> list[tuple[str, MarefSkill, Callable]]:
    """Create default SKILLOS skills for daily integration."""
    # Example: Research skill
    from maref.recursive.skill_schema import DegradationChain, HexagramTrigger

    research_skill = MarefSkill(
        maref_skill="1.0",
        meta=MarefSkillMeta(
            name="research",
            version="0.30.0",
            description="Research and analyze code patterns",
        ),
        role_affinity={"primary": "Explorer"},
        hexagram_trigger=HexagramTrigger(require=[], exclude=[], transition_from=None),
        degradation_chain=DegradationChain(primary="default", degraded=[]),
        behavior={"entrypoint": "research"},
        source=SkillSource.BUILTIN,
    )

    # Example: Execution skill
    exec_skill = MarefSkill(
        maref_skill="1.0",
        meta=MarefSkillMeta(
            name="execute",
            version="0.30.0",
            description="Execute commands and scripts",
        ),
        role_affinity={"primary": "Executor"},
        hexagram_trigger=HexagramTrigger(require=[], exclude=[], transition_from=None),
        degradation_chain=DegradationChain(primary="default", degraded=[]),
        behavior={"entrypoint": "execute"},
        source=SkillSource.BUILTIN,
    )

    def research_handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"query": args.get("input", ""), "status": "simulated"}

    def exec_handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"command": args.get("input", ""), "status": "simulated"}

    return [
        ("research", research_skill, research_handler),
        ("execute", exec_skill, exec_handler),
    ]


def create_default_agent_states() -> dict[str, Callable[[], SKILLOSAgentState]]:
    """Create default agent state providers for daily integration."""
    def agent_state_provider() -> SKILLOSAgentState:
        return SKILLOSAgentState(
            agent_id="daily-agent",
            current_state="IDLE",
            active_skill=None,
            skill_queue=[],
            trust_score=0.85,
            metrics={
                "tasks_completed": 0,
                "success_rate": 1.0,
                "avg_response_ms": 0.0,
            },
        )

    return {"daily-agent": agent_state_provider}


def run_skillos_mcp_integration(output_file: str) -> SKILLOSMCPDailyResult:
    """Run SKILLOS MCP integration and verify connectivity."""
    start_time = time.time()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    result = SKILLOSMCPDailyResult(
        timestamp=timestamp,
        status="ok",
    )

    try:
        # 1. Create default skills and agent states
        skills = create_default_skills()
        agent_states = create_default_agent_states()

        # 2. Build MCP bridge
        bridge = create_skillos_mcp_bridge(
            skills=skills,
            agent_states=agent_states,
        )

        result.skills_registered = len(skills)
        result.agents_registered = len(agent_states)

        # 3. Build MCP server and verify registration
        mcp_server = bridge.build_mcp_server()
        result.capabilities = bridge.get_capabilities_summary()

        # 4. Run smoke test: verify tools are registered
        tools_list = mcp_server._tools
        if len(tools_list) < len(skills):
            result.errors.append(
                f"Expected {len(skills)} tools, got {len(tools_list)}"
            )
            result.status = "partial"

        # 5. Run smoke test: verify resources are registered
        resources_list = mcp_server._resources
        if len(resources_list) < len(agent_states):
            result.errors.append(
                f"Expected {len(agent_states)} resources, got {len(resources_list)}"
            )
            result.status = "partial"

        # 6. Run smoke test: test a tool call
        test_tool = f"skillos.{skills[0][0]}"
        if test_tool in mcp_server._tools:
            from maref.integration.mcp_transport import JSONRPCRequest
            request = JSONRPCRequest(
                jsonrpc="2.0",
                method="tools/call",
                params={"name": test_tool, "arguments": {"input": "test"}},
                id=1,
            )
            response = mcp_server.handle_request(request)
            if response.is_error:
                result.errors.append(f"Tool call failed: {response.error}")
                result.status = "partial"
            else:
                result.smoke_test_passed = True
        else:
            result.errors.append(f"Test tool not found: {test_tool}")
            result.status = "partial"

        # 7. Run smoke test: test a resource read
        test_resource = "skillos://agent/daily-agent/state"
        if test_resource in mcp_server._resources:
            request = JSONRPCRequest(
                jsonrpc="2.0",
                method="resources/read",
                params={"uri": test_resource},
                id=2,
            )
            response = mcp_server.handle_request(request)
            if response.is_error:
                result.errors.append(f"Resource read failed: {response.error}")
                result.status = "partial"
            else:
                result.smoke_test_passed = True
        else:
            result.errors.append(f"Test resource not found: {test_resource}")
            result.status = "partial"

    except Exception as e:
        result.status = "failed"
        result.errors.append(str(e))

    result.duration_seconds = time.time() - start_time

    # Save output
    output_path = __import__("pathlib").Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    # Print summary to stdout
    print("SKILLOS MCP Integration Summary:")
    print(f"  Timestamp:      {timestamp}")
    print(f"  Status:         {result.status}")
    print(f"  Skills:         {result.skills_registered} registered")
    print(f"  Agents:         {result.agents_registered} registered")
    print(f"  Smoke Test:     {'PASSED' if result.smoke_test_passed else 'FAILED'}")
    print(f"  Errors:         {len(result.errors)}")
    if result.errors:
        for err in result.errors:
            print(f"    - {err}")
    print(f"  Duration:       {result.duration_seconds:.2f}s")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="SKILLOS MCP Integration — Daily Check"
    )
    parser.add_argument(
        "--output-file",
        default="./research_output/integration/skillos_mcp_daily.json",
        help="Output file for integration results",
    )

    args = parser.parse_args()

    try:
        result = run_skillos_mcp_integration(output_file=args.output_file)

        if result.status == "ok" and result.smoke_test_passed:
            sys.exit(0)
        elif result.status == "partial":
            sys.exit(1)
        else:
            sys.exit(2)

    except Exception as e:
        print(f"[ERROR] SKILLOS MCP integration failed: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()

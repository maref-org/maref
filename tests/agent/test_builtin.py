from __future__ import annotations

from maref.agent.builtin import (
    BUILTIN_AGENTS,
    CODEGEN_AGENT,
    DIAGNOSE_AGENT,
    OPTIMIZE_AGENT,
    VERIFY_AGENT,
)


class TestBuiltinAgents:
    def test_builtin_list_not_empty(self) -> None:
        assert len(BUILTIN_AGENTS) > 0

    def test_diagnose_agent_read_only(self) -> None:
        assert DIAGNOSE_AGENT.permission_mode == "read_only"
        assert "ObserveTool" in DIAGNOSE_AGENT.allowed_tools

    def test_codegen_agent_has_edit_tools(self) -> None:
        assert "EditFileTool" in CODEGEN_AGENT.allowed_tools
        assert CODEGEN_AGENT.max_turns == 50

    def test_verify_agent_disallows_edit(self) -> None:
        assert "EditFileTool" in VERIFY_AGENT.disallowed_tools
        assert VERIFY_AGENT.permission_mode == "read_only"

    def test_optimize_agent_has_benchmark(self) -> None:
        assert "BenchmarkTool" in OPTIMIZE_AGENT.allowed_tools

    def test_all_builtins_have_unique_types(self) -> None:
        types = [a.agent_type for a in BUILTIN_AGENTS]
        assert len(types) == len(set(types))

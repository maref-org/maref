from __future__ import annotations

from typing import Any

import pytest

from maref.mcp.evolution_tools import (
    ArchitectTool,
    CodegenTool,
    DeployTool,
    DiagnoseTool,
    EVOLUTION_TOOLS,
    ObserveTool,
    VerifyTool,
)
from maref.tool.context import ToolUseContext


class TestEvolutionTools:
    def test_all_tools_have_names(self) -> None:
        for tool in EVOLUTION_TOOLS:
            assert tool.name
            assert tool.name.startswith("maref_")

    def test_all_tools_have_descriptions(self) -> None:
        for tool in EVOLUTION_TOOLS:
            assert tool.description

    def test_observe_is_read_only(self) -> None:
        assert ObserveTool().is_read_only()

    def test_diagnose_is_read_only(self) -> None:
        assert DiagnoseTool().is_read_only()

    def test_architect_is_read_only(self) -> None:
        assert ArchitectTool().is_read_only()

    def test_verify_is_read_only(self) -> None:
        assert VerifyTool().is_read_only()

    def test_codegen_is_not_read_only(self) -> None:
        assert not CodegenTool().is_read_only()

    def test_deploy_is_not_read_only(self) -> None:
        assert not DeployTool().is_read_only()

    def test_all_tools_enabled_by_default(self) -> None:
        for tool in EVOLUTION_TOOLS:
            assert tool.is_enabled()

    def test_input_schema_is_dict(self) -> None:
        for tool in EVOLUTION_TOOLS:
            assert isinstance(tool.input_schema, dict)

"""Smoke tests for maref.codegen.codegen_tool."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from unittest.mock import MagicMock

from maref.codegen.codegen_tool import CodeGenInput, CodeGenOutput, CodeGenTool
from maref.codegen.loop import CodeGenLoop


class TestCodeGenInput:
    def test_init_default(self) -> None:
        inp = CodeGenInput(file_path="/tmp/test.py", new_string="print('hello')")
        assert inp.file_path == "/tmp/test.py"
        assert inp.new_string == "print('hello')"
        assert inp.old_string == ""
        assert inp.rationale == ""

    def test_init_custom(self) -> None:
        inp = CodeGenInput(
            file_path="/tmp/test.py", old_string="old", new_string="new",
            rationale="Update logic",
        )
        assert inp.old_string == "old"
        assert inp.rationale == "Update logic"

    def test_validation_none_path(self) -> None:
        with pytest.raises(ValidationError):
            CodeGenInput(file_path=None, new_string="test")  # type: ignore[arg-type]


class TestCodeGenOutput:
    def test_init_default(self) -> None:
        out = CodeGenOutput(file_path="/tmp/test.py", applied=True)
        assert out.file_path == "/tmp/test.py"
        assert out.applied is True
        assert out.lint_passed is None
        assert out.patch == ""

    def test_init_custom(self) -> None:
        out = CodeGenOutput(
            file_path="/tmp/test.py", applied=False,
            lint_passed=False, test_passed=False,
            patch="--- a/+++ b/", error="lint error",
        )
        assert out.applied is False
        assert out.error == "lint error"


class TestCodeGenTool:
    def test_init_with_loop(self) -> None:
        registry = MagicMock()
        permission_engine = MagicMock()
        context_manager = MagicMock()
        loop = CodeGenLoop(
            registry=registry,
            permission_engine=permission_engine,
            context_manager=context_manager,
        )
        tool = CodeGenTool(loop=loop)
        assert tool is not None
        assert tool.history == []

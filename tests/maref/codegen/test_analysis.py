"""Smoke tests for maref.codegen.analysis."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from maref.codegen.analysis import (
    CodeCompletionInput,
    CodeCompletionOutput,
    CodeCompletionTool,
    LSPInput,
    LSPOutput,
    LSPTool,
)


class TestLSPInput:
    def test_init_default(self) -> None:
        instance = LSPInput(file_path="/tmp/test.py")
        assert instance.file_path == "/tmp/test.py"
        assert instance.action == "hover"
        assert instance.line == 1

    def test_init_custom(self) -> None:
        instance = LSPInput(file_path="/tmp/test.py", action="diagnostics", line=10, character=3)
        assert instance.file_path == "/tmp/test.py"
        assert instance.action == "diagnostics"
        assert instance.line == 10
        assert instance.character == 3

    def test_validation_none_path(self) -> None:
        with pytest.raises(ValidationError):
            LSPInput(file_path=None)  # type: ignore[arg-type]


class TestLSPOutput:
    def test_init_default(self) -> None:
        instance = LSPOutput(action="hover")
        assert instance.action == "hover"
        assert instance.results == []

    def test_init_with_results(self) -> None:
        instance = LSPOutput(action="diagnostics", results=[{"severity": "error", "message": "test"}])
        assert instance.action == "diagnostics"
        assert len(instance.results) == 1


class TestCodeCompletionInput:
    def test_init_default(self) -> None:
        instance = CodeCompletionInput(file_path="/tmp/test.py")
        assert instance.file_path == "/tmp/test.py"
        assert instance.cursor_line == 1

    def test_init_custom(self) -> None:
        instance = CodeCompletionInput(
            file_path="/tmp/test.py", cursor_line=5, cursor_character=3,
            context_before="def foo():", context_after="",
        )
        assert instance.context_before == "def foo():"

    def test_validation_none_path(self) -> None:
        with pytest.raises(ValidationError):
            CodeCompletionInput(file_path=None)  # type: ignore[arg-type]


class TestCodeCompletionOutput:
    def test_init_default(self) -> None:
        instance = CodeCompletionOutput()
        assert instance.generated_code == ""

    def test_init_custom(self) -> None:
        instance = CodeCompletionOutput(generated_code="pass", alternatives=["pass", "return"], confidence=0.9)
        assert instance.generated_code == "pass"
        assert len(instance.alternatives) == 2
        assert instance.confidence == 0.9


class TestLSPTool:
    def test_init(self) -> None:
        instance = LSPTool()
        assert instance is not None
        assert instance.name == "LSP"

    def test_is_read_only(self) -> None:
        instance = LSPTool()
        inp = LSPInput(file_path="/tmp/test.py")
        assert instance.is_read_only(inp) is True

    def test_is_concurrency_safe(self) -> None:
        instance = LSPTool()
        inp = LSPInput(file_path="/tmp/test.py")
        assert instance.is_concurrency_safe(inp) is True

    def test_supported_extensions(self) -> None:
        assert ".py" in LSPTool._supported_extensions
        assert ".pyi" in LSPTool._supported_extensions


class TestCodeCompletionTool:
    def test_init_default(self) -> None:
        instance = CodeCompletionTool()
        assert instance is not None

    def test_is_read_only(self) -> None:
        instance = CodeCompletionTool()
        inp = CodeCompletionInput(file_path="/tmp/test.py")
        assert instance.is_read_only(inp) is True

    def test_is_concurrency_safe(self) -> None:
        instance = CodeCompletionTool()
        inp = CodeCompletionInput(file_path="/tmp/test.py")
        assert instance.is_concurrency_safe(inp) is True

from __future__ import annotations

from typing import Any

import pytest

from maref.execution.adapters.base import ModelAdapter


class TestModelAdapter:
    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            ModelAdapter("test")  # type: ignore[abstract]

    def test_concrete_subclass_model_name(self) -> None:
        class ConcreteAdapter(ModelAdapter):
            def __init__(self, model_name: str) -> None:
                self._name = model_name

            def complete(self, prompt: str, **kwargs: Any) -> str:
                return f"response to: {prompt}"

            @property
            def model_name(self) -> str:
                return self._name

            def count_tokens(self, text: str) -> int:
                return len(text.split())

        adapter = ConcreteAdapter("gpt-4")
        assert adapter.model_name == "gpt-4"

    def test_concrete_subclass_methods_work(self) -> None:
        class ConcreteAdapter(ModelAdapter):
            def __init__(self, model_name: str) -> None:
                self._name = model_name

            def complete(self, prompt: str, **kwargs: Any) -> str:
                return f"response to: {prompt}"

            @property
            def model_name(self) -> str:
                return self._name

            def count_tokens(self, text: str) -> int:
                return len(text.split())

        adapter = ConcreteAdapter("claude-3")
        assert adapter.complete("hello") == "response to: hello"
        assert adapter.count_tokens("hello world") == 2

    def test_incomplete_subclass_cannot_instantiate(self) -> None:
        class IncompleteAdapter(ModelAdapter):
            @property
            def model_name(self) -> str:
                return "test"

        with pytest.raises(TypeError):
            IncompleteAdapter("test")  # type: ignore[abstract]

from __future__ import annotations

import builtins
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from maref.execution.adapters.local_adapter import LocalModelAdapter


class TestLocalModelAdapter:
    def test_init_stores_model_name(self) -> None:
        adapter = LocalModelAdapter("custom-model")
        assert adapter._model_name == "custom-model"

    def test_init_default_model_name(self) -> None:
        adapter = LocalModelAdapter()
        assert adapter._model_name == "microsoft/phi-2"

    def test_model_name_property(self) -> None:
        adapter = LocalModelAdapter("test-model")
        assert adapter.model_name == "test-model"

    def test_count_tokens_with_mocked_tokenizer(self) -> None:
        adapter = LocalModelAdapter("test-model")
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [101, 230, 145, 189]
        adapter._tokenizer = mock_tokenizer
        adapter._model = MagicMock()

        result = adapter.count_tokens("hello world")
        assert result == 4
        mock_tokenizer.encode.assert_called_once_with("hello world")

    def test_complete_with_mocked_deps(self) -> None:
        adapter = LocalModelAdapter("test-model")
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {"input_ids": MagicMock()}
        mock_model = MagicMock()
        mock_outputs: Any = MagicMock()
        mock_outputs.__getitem__.return_value = [[101, 230, 145]]
        mock_model.generate.return_value = mock_outputs
        mock_tokenizer.decode.return_value = "generated response"
        adapter._tokenizer = mock_tokenizer
        adapter._model = mock_model

        with patch.dict(sys.modules, {"torch": MagicMock()}):
            result = adapter.complete("hello", max_length=50)

        assert result == "generated response"
        mock_tokenizer.assert_called_once_with("hello", return_tensors="pt")
        mock_model.generate.assert_called_once()
        mock_tokenizer.decode.assert_called_once()

    def test_lazy_init_import_error_transformers(self) -> None:
        adapter = LocalModelAdapter("test-model")
        orig_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "transformers":
                raise ImportError("No module named 'transformers'")
            return orig_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(ImportError, match="No module named 'transformers'"):
                adapter._lazy_init()

    def test_lazy_init_import_error_torch(self) -> None:
        adapter = LocalModelAdapter("test-model")
        mock_tokenizer = MagicMock()
        mock_model = MagicMock()
        adapter._tokenizer = mock_tokenizer
        adapter._model = mock_model

        orig_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "torch":
                raise ImportError("No module named 'torch'")
            return orig_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(ImportError, match="No module named 'torch'"):
                adapter.complete("hello")

    def test_lazy_init_only_once(self) -> None:
        adapter = LocalModelAdapter("test-model")
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [101, 102]
        adapter._tokenizer = mock_tokenizer
        adapter._model = MagicMock()

        with patch.object(adapter, "_lazy_init") as mock_lazy:
            with patch.dict(sys.modules, {"torch": MagicMock()}):
                adapter.count_tokens("test")
                adapter.count_tokens("test again")
                adapter.complete("hello")
            assert mock_lazy.call_count == 3

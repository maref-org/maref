from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from maref.integration.feature_dev.llm_client import (
    LlmClient,
    _first_key,
)


class TestFirstKey:
    def test_returns_first_found(self) -> None:
        with patch.dict("os.environ", {"KEY_A": "val_a", "KEY_B": "val_b"}):
            assert _first_key("KEY_A", "KEY_B") == "val_a"

    def test_skips_missing(self) -> None:
        with patch.dict("os.environ", {"KEY_B": "val_b"}, clear=True):
            assert _first_key("KEY_A", "KEY_B") == "val_b"

    def test_returns_none_when_none_found(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            assert _first_key("KEY_A", "KEY_B") is None


class TestLlmClient:
    def test_not_available_when_no_keys(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            client = LlmClient()
            assert client.available is False
            assert client.provider_name == "none"

    def test_generate_returns_none_when_not_available(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            client = LlmClient()
            result = client.generate(system="test", prompt="test")
            assert result is None

    def test_generate_json_returns_none_when_not_available(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            client = LlmClient()
            result = client.generate_json(system="test", prompt="test")
            assert result is None

    def test_generate_success(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello, world!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            with patch.object(httpx, "post", return_value=mock_resp):
                client = LlmClient()
                assert client.available is True
                assert client.provider_name == "deepseek"
                result = client.generate(system="Be helpful", prompt="Say hi")
                assert result == "Hello, world!"

    def test_generate_http_error(self) -> None:
        from httpx import HTTPStatusError

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = HTTPStatusError(
            "401", request=MagicMock(), response=mock_resp
        )

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            with patch.object(httpx, "post", return_value=mock_resp):
                client = LlmClient()
                result = client.generate(system="S", prompt="P")
                assert result is None

    def test_generate_json_parses_response(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"Static Audit": 85}'}}],
            "usage": {},
        }

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            with patch.object(httpx, "post", return_value=mock_resp):
                client = LlmClient()
                result = client.generate_json(
                    system="Output JSON", prompt="Score content"
                )
                assert result == {"Static Audit": 85}

    def test_generate_json_strips_fences(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '```\n{"key": "value"}\n```'}}],
            "usage": {},
        }

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            with patch.object(httpx, "post", return_value=mock_resp):
                client = LlmClient()
                result = client.generate_json(system="S", prompt="P")
                assert result == {"key": "value"}

    def test_generate_json_invalid_returns_none(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "NOT JSON"}}],
            "usage": {},
        }

        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test"}, clear=True):
            with patch.object(httpx, "post", return_value=mock_resp):
                client = LlmClient()
                result = client.generate_json(system="S", prompt="P")
                assert result is None

    def test_uses_correct_model_key(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        }

        with patch.dict("os.environ", {"SILICONFLOW_API_KEY": "sk-test"}, clear=True):
            with patch.object(httpx, "post", return_value=mock_resp) as mock_post:
                client = LlmClient()
                client.generate(
                    system="S", prompt="P", model_key="reasoning"
                )
                call_kwargs = mock_post.call_args[1]
                assert "deepseek-ai/DeepSeek-R1" in str(
                    call_kwargs.get("json", {})
                )

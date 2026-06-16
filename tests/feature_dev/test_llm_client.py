from __future__ import annotations

from unittest.mock import MagicMock, patch

from maref.integration.feature_dev.llm_client import LlmClient, _first_key


class TestFirstKey:
    def test_first_found(self) -> None:
        assert _first_key("PATH") is not None

    def test_not_found(self) -> None:
        assert _first_key("NONEXISTENT_VAR_XYZ") is None

    def test_multiple_keys(self) -> None:
        assert _first_key("PATH", "HOME") is not None
        assert _first_key("NONEXISTENT_VAR_XYZ", "PATH") is not None
        assert _first_key("NONEXISTENT_A", "NONEXISTENT_B") is None


class TestLlmClient:
    @patch("httpx.post")
    def test_init_no_provider_when_no_key(self, mock_post: MagicMock) -> None:
        with patch.dict("os.environ", {}, clear=True):
            client = LlmClient()
            assert not client.available
            assert client.provider_name == "none"
            mock_post.assert_not_called()

    @patch("httpx.post")
    def test_init_with_key_but_provider_fails(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=True):
            client = LlmClient()
            assert not client.available
            assert mock_post.call_count == 1

    @patch("httpx.post")
    def test_init_with_working_provider(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}):
            client = LlmClient()
            assert client.available
            assert client.provider_name == "deepseek"

    @patch("httpx.post")
    def test_generate_not_available(self, mock_post: MagicMock) -> None:
        client = LlmClient.__new__(LlmClient)
        client._available = False
        client._provider = None
        result = client.generate(system="s", prompt="p")
        assert result is None
        mock_post.assert_not_called()

    @patch("httpx.post")
    def test_generate_success(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello world"}}],
            "usage": {"total_tokens": 10},
        }
        mock_post.return_value = mock_response

        client = LlmClient.__new__(LlmClient)
        client._available = True
        client._provider = {
            "name": "test",
            "base_url": "https://api.test.com/v1",
            "api_key": lambda: "test-key",
            "models": {"default": "test-model"},
        }

        result = client.generate(system="Be helpful", prompt="Say hi")
        assert result == "Hello world"
        mock_post.assert_called_once()

    @patch("httpx.post")
    def test_generate_http_error(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")
        mock_post.return_value = mock_response

        client = LlmClient.__new__(LlmClient)
        client._available = True
        client._provider = {
            "name": "test",
            "base_url": "https://api.test.com/v1",
            "api_key": lambda: "test-key",
            "models": {"default": "test-model"},
        }

        result = client.generate(system="s", prompt="p")
        assert result is None

    @patch("httpx.post")
    def test_generate_json_success(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"Static Audit": 85, "Reasoning": 70}'}}],
            "usage": {"total_tokens": 20},
        }
        mock_post.return_value = mock_response

        client = LlmClient.__new__(LlmClient)
        client._available = True
        client._provider = {
            "name": "test",
            "base_url": "https://api.test.com/v1",
            "api_key": lambda: "test-key",
            "models": {"default": "test-model"},
        }

        result = client.generate_json(system="s", prompt="p")
        assert result == {"Static Audit": 85, "Reasoning": 70}

    @patch("httpx.post")
    def test_generate_json_with_fences(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '```json\n{"key": "value"}\n```'}}],
            "usage": {},
        }
        mock_post.return_value = mock_response

        client = LlmClient.__new__(LlmClient)
        client._available = True
        client._provider = {
            "name": "test",
            "base_url": "https://api.test.com/v1",
            "api_key": lambda: "test-key",
            "models": {"default": "test-model"},
        }

        result = client.generate_json(system="s", prompt="p")
        assert result == {"key": "value"}

    @patch("httpx.post")
    def test_generate_json_invalid(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not json"}}],
            "usage": {},
        }
        mock_post.return_value = mock_response

        client = LlmClient.__new__(LlmClient)
        client._available = True
        client._provider = {
            "name": "test",
            "base_url": "https://api.test.com/v1",
            "api_key": lambda: "test-key",
            "models": {"default": "test-model"},
        }

        result = client.generate_json(system="s", prompt="p")
        assert result is None

    @patch("httpx.post")
    def test_generate_json_none_result(self, mock_post: MagicMock) -> None:
        client = LlmClient.__new__(LlmClient)
        client._available = True
        client._provider = {
            "name": "test",
            "base_url": "https://api.test.com/v1",
            "api_key": lambda: "test-key",
            "models": {"default": "test-model"},
        }
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("error")
        mock_post.return_value = mock_response

        result = client.generate_json(system="s", prompt="p")
        assert result is None

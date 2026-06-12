from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.integration.mcp_transport import JSONRPCResponse
from maref.recursive.claude_code_adapter import (
    ClaudeCodeAdapter,
    AdapterConfig,
    TaskResult,
)


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.register_server.return_value = None
    return client


class TestClaudeCodeAdapterInit:
    def test_default_config(self) -> None:
        adapter = ClaudeCodeAdapter()
        assert adapter.config.agent_id == "claude-code"
        assert adapter.is_connected is False

    def test_custom_config(self) -> None:
        config = AdapterConfig(agent_id="test-agent", request_timeout=60.0)
        adapter = ClaudeCodeAdapter(config=config)
        assert adapter.config.agent_id == "test-agent"
        assert adapter.config.request_timeout == 60.0


class TestClaudeCodeAdapterConnect:
    @pytest.fixture
    def adapter(self, mock_client: MagicMock) -> ClaudeCodeAdapter:
        return ClaudeCodeAdapter(mcp_client=mock_client)

    def test_connect_returns_false_when_no_server(self, adapter: ClaudeCodeAdapter) -> None:
        result = adapter.connect()
        assert result is False

    def test_disconnect_no_error(self, adapter: ClaudeCodeAdapter) -> None:
        adapter.disconnect()
        assert adapter.is_connected is False

    def test_connect_twice_returns_true_after_first(self, adapter: ClaudeCodeAdapter) -> None:
        adapter.set_connection(MagicMock())
        result = adapter.connect()
        assert result is True


class TestClaudeCodeAdapterTaskSubmission:
    @pytest.fixture
    def adapter(self, mock_client: MagicMock) -> ClaudeCodeAdapter:
        return ClaudeCodeAdapter(mcp_client=mock_client)

    def test_submit_returns_none_when_not_connected(self, adapter: ClaudeCodeAdapter) -> None:
        task_id = adapter.submit_task("read_file", {"path": "/tmp/test.py"})
        assert task_id is None

    def test_get_result_unknown(self, adapter: ClaudeCodeAdapter) -> None:
        result = adapter.get_result("nonexistent")
        assert result is None

    def test_recent_results_empty(self, adapter: ClaudeCodeAdapter) -> None:
        results = adapter.recent_results()
        assert results == []

    def test_submit_success_with_mock(self, adapter: ClaudeCodeAdapter) -> None:
        mock_conn = MagicMock()
        adapter.set_connection(mock_conn)
        adapter._mcp_client.call_tool.return_value = JSONRPCResponse(
            jsonrpc="2.0", result={"content": "ok"}, id="1"
        )
        task_id = adapter.submit_task("read_file", {"path": "/tmp/test.py"})
        assert task_id is not None
        result = adapter.get_result(task_id)
        assert result is not None
        assert result.success is True

    def test_submit_governance_denied_with_mock(self, adapter: ClaudeCodeAdapter) -> None:
        mock_conn = MagicMock()
        adapter.set_connection(mock_conn)
        adapter._mcp_client.call_tool.return_value = JSONRPCResponse(
            jsonrpc="2.0", result=None, error={"code": -32000, "message": "Governance denied"}, id="1"
        )
        task_id = adapter.submit_task("bash", {"command": "rm -rf /"})
        assert task_id is None


class TestTaskResult:
    def test_task_result_defaults(self) -> None:
        result = TaskResult(task_id="t1", success=True)
        assert result.task_id == "t1"
        assert result.success is True
        assert result.output == ""
        assert result.error == ""
        assert result.duration == 0.0

    def test_task_result_failure(self) -> None:
        result = TaskResult(task_id="t2", success=False, error="access denied")
        assert result.success is False
        assert result.error == "access denied"


class TestClaudeCodeAdapterConfig:
    def test_reconnect_flag(self) -> None:
        config = AdapterConfig(auto_reconnect=False)
        assert config.auto_reconnect is False

"""
Comprehensive tests for DashScope (百炼) API Client.

Covers:
- Dataclass construction and default values
- Public functions/methods with edge cases
- Mocked aiohttp, network I/O, and external API calls
- Error handling (timeout, connection errors, invalid responses)
- Configuration loading and validation
"""

from __future__ import annotations

import asyncio
import json
import os
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from research.dashscope_client import (
    BatchAnalysis,
    DashScopeClient,
    FindingAnalysis,
    LLMResponse,
)


# ============================================================================
# 1. Dataclass construction and default values
# ============================================================================

class TestDataclassConstruction:
    """Test dataclass construction and default values."""

    def test_llmresponse_full(self) -> None:
        resp = LLMResponse(
            content="hello",
            model="qwen-plus",
            usage={"input_tokens": 10, "output_tokens": 5},
            finish_reason="stop",
        )
        assert resp.content == "hello"
        assert resp.model == "qwen-plus"
        assert resp.usage == {"input_tokens": 10, "output_tokens": 5}
        assert resp.finish_reason == "stop"

    def test_llmresponse_empty_content(self) -> None:
        resp = LLMResponse(content="", model="", usage={}, finish_reason="")
        assert resp.content == ""
        assert resp.model == ""
        assert resp.usage == {}
        assert resp.finish_reason == ""

    def test_findinganalysis_full(self) -> None:
        analysis = FindingAnalysis(
            summary="summary text",
            significance="high",
            related_concepts=["c1", "c2"],
            suggested_experiments=["exp1"],
            confidence=0.95,
        )
        assert analysis.summary == "summary text"
        assert analysis.significance == "high"
        assert analysis.related_concepts == ["c1", "c2"]
        assert analysis.suggested_experiments == ["exp1"]
        assert analysis.confidence == 0.95

    def test_findinganalysis_defaults(self) -> None:
        analysis = FindingAnalysis(
            summary="",
            significance="",
            related_concepts=[],
            suggested_experiments=[],
            confidence=0.0,
        )
        assert analysis.summary == ""
        assert analysis.significance == ""
        assert analysis.related_concepts == []
        assert analysis.suggested_experiments == []
        assert analysis.confidence == 0.0

    def test_batchanalysis_full(self) -> None:
        batch = BatchAnalysis(
            batch_id=42,
            key_insights=["k1", "k2"],
            patterns_detected=["p1"],
            anomalies_flagged=["a1"],
            recommendations=["r1"],
            overall_assessment="good",
        )
        assert batch.batch_id == 42
        assert batch.key_insights == ["k1", "k2"]
        assert batch.patterns_detected == ["p1"]
        assert batch.anomalies_flagged == ["a1"]
        assert batch.recommendations == ["r1"]
        assert batch.overall_assessment == "good"

    def test_batchanalysis_defaults(self) -> None:
        batch = BatchAnalysis(
            batch_id=0,
            key_insights=[],
            patterns_detected=[],
            anomalies_flagged=[],
            recommendations=[],
            overall_assessment="",
        )
        assert batch.batch_id == 0
        assert batch.key_insights == []
        assert batch.patterns_detected == []
        assert batch.anomalies_flagged == []
        assert batch.recommendations == []
        assert batch.overall_assessment == ""


# ============================================================================
# 2. Configuration loading and validation
# ============================================================================

class TestConfigurationLoading:
    """Test configuration loading and validation."""

    def test_init_with_api_key(self) -> None:
        client = DashScopeClient(api_key="test-key")
        assert client._api_key == "test-key"
        assert client._base_url == DashScopeClient.DEFAULT_BASE_URL
        assert client._model == DashScopeClient.DEFAULT_MODEL
        assert client._timeout == 60.0

    def test_init_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DASHSCOPE_API_KEY", "env-key")
        client = DashScopeClient()
        assert client._api_key == "env-key"

    def test_init_missing_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        with pytest.raises(ValueError, match="DashScope API key required"):
            DashScopeClient()

    def test_init_custom_base_url(self) -> None:
        client = DashScopeClient(api_key="k", base_url="https://custom.example.com")
        assert client._base_url == "https://custom.example.com"

    def test_init_custom_model(self) -> None:
        client = DashScopeClient(api_key="k", model="qwen-max")
        assert client._model == "qwen-max"

    def test_init_custom_timeout(self) -> None:
        client = DashScopeClient(api_key="k", timeout=120.0)
        assert client._timeout == 120.0

    def test_init_api_key_takes_precedence_over_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DASHSCOPE_API_KEY", "env-key")
        client = DashScopeClient(api_key="arg-key")
        assert client._api_key == "arg-key"

    def test_init_empty_string_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        # Empty string is falsy, so it falls back to env, which is missing
        with pytest.raises(ValueError, match="DashScope API key required"):
            DashScopeClient(api_key="")

    def test_init_all_custom_params(self) -> None:
        client = DashScopeClient(
            api_key="k",
            base_url="https://x.com",
            model="qwen-turbo",
            timeout=30.0,
        )
        assert client._api_key == "k"
        assert client._base_url == "https://x.com"
        assert client._model == "qwen-turbo"
        assert client._timeout == 30.0


# ============================================================================
# 3. Session management
# ============================================================================

class TestSessionManagement:
    """Test _get_session, close, context managers."""

    @pytest.mark.asyncio
    async def test_get_session_creates_new(self) -> None:
        client = DashScopeClient(api_key="k")
        session = await client._get_session()
        assert session is not None
        assert isinstance(session, aiohttp.ClientSession)
        assert not session.closed
        assert session.headers["Authorization"] == "Bearer k"
        assert session.headers["Content-Type"] == "application/json"
        await client.close()

    @pytest.mark.asyncio
    async def test_get_session_reuses_existing(self) -> None:
        client = DashScopeClient(api_key="k")
        session1 = await client._get_session()
        session2 = await client._get_session()
        assert session1 is session2
        await client.close()

    @pytest.mark.asyncio
    async def test_get_session_recreates_after_close(self) -> None:
        client = DashScopeClient(api_key="k")
        session1 = await client._get_session()
        await client.close()
        session2 = await client._get_session()
        assert session1 is not session2
        assert not session2.closed
        await client.close()

    @pytest.mark.asyncio
    async def test_get_session_recreates_when_closed(self) -> None:
        client = DashScopeClient(api_key="k")
        session1 = await client._get_session()
        await session1.close()
        session2 = await client._get_session()
        assert session1 is not session2
        assert not session2.closed
        await client.close()

    @pytest.mark.asyncio
    async def test_close_sets_session_none(self) -> None:
        client = DashScopeClient(api_key="k")
        await client._get_session()
        await client.close()
        assert client._session is None

    @pytest.mark.asyncio
    async def test_close_no_session(self) -> None:
        client = DashScopeClient(api_key="k")
        # Should not raise
        await client.close()

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        async with DashScopeClient(api_key="k") as client:
            assert isinstance(client, DashScopeClient)
            session = await client._get_session()
            assert not session.closed
        assert client._session is None or client._session.closed

    @pytest.mark.asyncio
    async def test_context_manager_exception_cleanup(self) -> None:
        with pytest.raises(RuntimeError):
            async with DashScopeClient(api_key="k") as client:
                await client._get_session()
                raise RuntimeError("boom")
        assert client._session is None or client._session.closed

    def test_del_warns_if_session_open(self) -> None:
        client = DashScopeClient(api_key="k")
        # Manually set a mock session that is not closed
        mock_session = MagicMock()
        mock_session.closed = False
        client._session = mock_session
        with pytest.warns(ResourceWarning, match="session was not properly closed"):
            del client

    def test_del_no_warn_if_session_closed(self) -> None:
        client = DashScopeClient(api_key="k")
        mock_session = MagicMock()
        mock_session.closed = True
        client._session = mock_session
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            del client  # Should not raise

    def test_del_no_warn_if_no_session(self) -> None:
        client = DashScopeClient(api_key="k")
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            del client  # Should not raise


# ============================================================================
# 4. chat_completion tests
# ============================================================================

class TestChatCompletion:
    """Test chat_completion method with mocked aiohttp."""

    @pytest.fixture
    def client(self) -> DashScopeClient:
        return DashScopeClient(api_key="test-key")

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        session = MagicMock()
        session.closed = False
        return session

    @pytest.mark.asyncio
    async def test_chat_completion_success(self, client: DashScopeClient) -> None:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "model": "qwen-plus",
                "output": {
                    "choices": [
                        {
                            "message": {"content": "Hello!"},
                            "finish_reason": "stop",
                        }
                    ]
                },
                "usage": {"input_tokens": 5, "output_tokens": 2},
            }
        )

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMockContextManager(mock_response))

        client._session = mock_session

        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0.5,
            max_tokens=100,
        )

        assert isinstance(response, LLMResponse)
        assert response.content == "Hello!"
        assert response.model == "qwen-plus"
        assert response.usage == {"input_tokens": 5, "output_tokens": 2}
        assert response.finish_reason == "stop"

        # Verify payload
        call_args = mock_session.post.call_args
        assert call_args is not None
        url = call_args[0][0]
        payload = call_args[1]["json"]
        assert url == f"{client.DEFAULT_BASE_URL}/services/aigc/text-generation/generation"
        assert payload["model"] == client.DEFAULT_MODEL
        assert payload["input"]["messages"] == [{"role": "user", "content": "Hi"}]
        assert payload["parameters"]["temperature"] == 0.5
        assert payload["parameters"]["max_tokens"] == 100
        assert payload["parameters"]["result_format"] == "message"

    @pytest.mark.asyncio
    async def test_chat_completion_no_max_tokens(self, client: DashScopeClient) -> None:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "output": {
                    "choices": [
                        {
                            "message": {"content": "No max"},
                            "finish_reason": "length",
                        }
                    ]
                },
                "usage": {},
            }
        )

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMockContextManager(mock_response))
        client._session = mock_session

        response = await client.chat_completion(messages=[{"role": "user", "content": "test"}])

        assert response.content == "No max"
        assert response.finish_reason == "length"

        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        assert "max_tokens" not in payload["parameters"]

    @pytest.mark.asyncio
    async def test_chat_completion_api_error(self, client: DashScopeClient) -> None:
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.text = AsyncMock(return_value="Rate limited")

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMockContextManager(mock_response))
        client._session = mock_session

        with pytest.raises(RuntimeError, match="API error 429: Rate limited"):
            await client.chat_completion(messages=[{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_chat_completion_500_error(self, client: DashScopeClient) -> None:
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMockContextManager(mock_response))
        client._session = mock_session

        with pytest.raises(RuntimeError, match="API error 500: Internal Server Error"):
            await client.chat_completion(messages=[{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_chat_completion_missing_output(self, client: DashScopeClient) -> None:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"model": "qwen-plus"})

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMockContextManager(mock_response))
        client._session = mock_session

        with pytest.raises(RuntimeError, match="Unexpected API response"):
            await client.chat_completion(messages=[{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_chat_completion_empty_choices_raises(self, client: DashScopeClient) -> None:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "output": {"choices": []},
                "usage": {},
            }
        )

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMockContextManager(mock_response))
        client._session = mock_session

        with pytest.raises(IndexError):
            await client.chat_completion(messages=[{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_chat_completion_timeout(self, client: DashScopeClient) -> None:
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=asyncio.TimeoutError())
        client._session = mock_session

        with pytest.raises(asyncio.TimeoutError):
            await client.chat_completion(messages=[{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_chat_completion_connection_error(self, client: DashScopeClient) -> None:
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=aiohttp.ClientConnectionError("conn refused"))
        client._session = mock_session

        with pytest.raises(aiohttp.ClientConnectionError, match="conn refused"):
            await client.chat_completion(messages=[{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_chat_completion_default_temperature(self, client: DashScopeClient) -> None:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "output": {
                    "choices": [
                        {
                            "message": {"content": "ok"},
                            "finish_reason": "stop",
                        }
                    ]
                },
                "usage": {},
            }
        )

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMockContextManager(mock_response))
        client._session = mock_session

        await client.chat_completion(messages=[{"role": "user", "content": "test"}])

        call_args = mock_session.post.call_args
        payload = call_args[1]["json"]
        assert payload["parameters"]["temperature"] == 0.7


# ============================================================================
# 5. analyze_findings tests
# ============================================================================

class TestAnalyzeFindings:
    """Test analyze_findings method."""

    @pytest.fixture
    def client(self) -> DashScopeClient:
        return DashScopeClient(api_key="test-key")

    @pytest.mark.asyncio
    async def test_analyze_findings_empty_list(self, client: DashScopeClient) -> None:
        result = await client.analyze_findings([], "test_exp")
        assert isinstance(result, FindingAnalysis)
        assert result.summary == "No findings to analyze"
        assert result.significance == "low"
        assert result.related_concepts == []
        assert result.suggested_experiments == []
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_analyze_findings_success(self, client: DashScopeClient) -> None:
        json_response = json.dumps({
            "summary": "Important discovery",
            "significance": "high",
            "related_concepts": ["c1", "c2"],
            "suggested_experiments": ["e1"],
            "confidence": 0.9,
        })

        mock_response = LLMResponse(
            content=json_response,
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_findings(["finding1"], "random_walk")

        assert result.summary == "Important discovery"
        assert result.significance == "high"
        assert result.related_concepts == ["c1", "c2"]
        assert result.suggested_experiments == ["e1"]
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_analyze_findings_with_markdown_code_block(self, client: DashScopeClient) -> None:
        json_response = json.dumps({
            "summary": "MD block",
            "significance": "medium",
            "related_concepts": [],
            "suggested_experiments": [],
            "confidence": 0.8,
        })
        content = f"```json\n{json_response}\n```"

        mock_response = LLMResponse(
            content=content,
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_findings(["f1"], "test")

        assert result.summary == "MD block"
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_analyze_findings_with_plain_code_block(self, client: DashScopeClient) -> None:
        json_response = json.dumps({
            "summary": "Plain block",
            "significance": "low",
            "related_concepts": [],
            "suggested_experiments": [],
            "confidence": 0.7,
        })
        content = f"```\n{json_response}\n```"

        mock_response = LLMResponse(
            content=content,
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_findings(["f1"], "test")

        assert result.summary == "Plain block"

    @pytest.mark.asyncio
    async def test_analyze_findings_json_decode_error(self, client: DashScopeClient) -> None:
        mock_response = LLMResponse(
            content="not json",
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_findings(["f1"], "test")

        assert result.summary.startswith("Raw analysis:")
        assert result.significance == "medium"
        assert result.suggested_experiments == ["retry_analysis"]
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_analyze_findings_missing_fields(self, client: DashScopeClient) -> None:
        json_response = json.dumps({"summary": "Partial"})
        mock_response = LLMResponse(
            content=json_response,
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_findings(["f1"], "test")

        assert result.summary == "Partial"
        assert result.significance == "low"
        assert result.related_concepts == []
        assert result.suggested_experiments == []
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_analyze_findings_limits_to_20(self, client: DashScopeClient) -> None:
        findings = [f"finding_{i}" for i in range(25)]
        mock_response = LLMResponse(
            content=json.dumps({
                "summary": "ok",
                "significance": "low",
                "related_concepts": [],
                "suggested_experiments": [],
                "confidence": 0.5,
            }),
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response) as mock_chat:
            await client.analyze_findings(findings, "test")

        call_args = mock_chat.call_args
        messages = call_args[1]["messages"]
        prompt = messages[1]["content"]
        # Should only include first 20 findings
        assert "finding_19" in prompt
        assert "finding_20" not in prompt
        assert "finding_24" not in prompt

    @pytest.mark.asyncio
    async def test_analyze_findings_chat_params(self, client: DashScopeClient) -> None:
        mock_response = LLMResponse(
            content=json.dumps({
                "summary": "ok",
                "significance": "low",
                "related_concepts": [],
                "suggested_experiments": [],
                "confidence": 0.5,
            }),
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response) as mock_chat:
            await client.analyze_findings(["f1"], "test_exp")

        call_args = mock_chat.call_args
        assert call_args[1]["temperature"] == 0.3
        assert call_args[1]["max_tokens"] == 1000


# ============================================================================
# 6. analyze_batch tests
# ============================================================================

class TestAnalyzeBatch:
    """Test analyze_batch method."""

    @pytest.fixture
    def client(self) -> DashScopeClient:
        return DashScopeClient(api_key="test-key")

    @pytest.mark.asyncio
    async def test_analyze_batch_success(self, client: DashScopeClient) -> None:
        json_response = json.dumps({
            "key_insights": ["insight1"],
            "patterns_detected": ["pattern1"],
            "anomalies_flagged": ["anomaly1"],
            "recommendations": ["rec1"],
            "overall_assessment": "Good batch",
        })
        mock_response = LLMResponse(
            content=json_response,
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_batch(
                batch_id=1,
                experiment_results=[
                    {"experiment_type": "type_a", "findings": ["f1", "f2"]},
                    {"experiment_type": "type_b", "findings": ["f3"]},
                ],
                knowledge_graph_summary={"total_nodes": 100},
            )

        assert isinstance(result, BatchAnalysis)
        assert result.batch_id == 1
        assert result.key_insights == ["insight1"]
        assert result.patterns_detected == ["pattern1"]
        assert result.anomalies_flagged == ["anomaly1"]
        assert result.recommendations == ["rec1"]
        assert result.overall_assessment == "Good batch"

    @pytest.mark.asyncio
    async def test_analyze_batch_empty_results(self, client: DashScopeClient) -> None:
        json_response = json.dumps({
            "key_insights": [],
            "patterns_detected": [],
            "anomalies_flagged": [],
            "recommendations": [],
            "overall_assessment": "Empty",
        })
        mock_response = LLMResponse(
            content=json_response,
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_batch(
                batch_id=2,
                experiment_results=[],
                knowledge_graph_summary={},
            )

        assert result.batch_id == 2
        assert result.key_insights == []
        assert result.overall_assessment == "Empty"

    @pytest.mark.asyncio
    async def test_analyze_batch_json_decode_error(self, client: DashScopeClient) -> None:
        mock_response = LLMResponse(
            content="invalid json",
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_batch(
                batch_id=3,
                experiment_results=[{"experiment_type": "t", "findings": ["f"]}],
                knowledge_graph_summary={},
            )

        assert result.batch_id == 3
        assert result.key_insights == ["Error in LLM analysis, using fallback"]
        assert result.patterns_detected == []
        assert result.anomalies_flagged  # non-empty error description
        assert result.recommendations == ["Check API connectivity"]
        assert result.overall_assessment == "Analysis failed, manual review recommended"

    @pytest.mark.asyncio
    async def test_analyze_batch_missing_fields(self, client: DashScopeClient) -> None:
        json_response = json.dumps({"key_insights": ["only_key_insights"]})
        mock_response = LLMResponse(
            content=json_response,
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_batch(
                batch_id=4,
                experiment_results=[],
                knowledge_graph_summary={},
            )

        assert result.key_insights == ["only_key_insights"]
        assert result.patterns_detected == []
        assert result.anomalies_flagged == []
        assert result.recommendations == []
        assert result.overall_assessment == "Analysis complete"

    @pytest.mark.asyncio
    async def test_analyze_batch_limits_findings(self, client: DashScopeClient) -> None:
        findings = [f"finding_{i}" for i in range(20)]
        json_response = json.dumps({
            "key_insights": ["i1"],
            "patterns_detected": [],
            "anomalies_flagged": [],
            "recommendations": [],
            "overall_assessment": "ok",
        })
        mock_response = LLMResponse(
            content=json_response,
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response) as mock_chat:
            await client.analyze_batch(
                batch_id=5,
                experiment_results=[{"experiment_type": "t", "findings": findings}],
                knowledge_graph_summary={},
            )

        call_args = mock_chat.call_args
        messages = call_args[1]["messages"]
        prompt = messages[1]["content"]
        assert "finding_14" in prompt
        assert "finding_15" not in prompt

    @pytest.mark.asyncio
    async def test_analyze_batch_chat_params(self, client: DashScopeClient) -> None:
        mock_response = LLMResponse(
            content=json.dumps({
                "key_insights": [],
                "patterns_detected": [],
                "anomalies_flagged": [],
                "recommendations": [],
                "overall_assessment": "ok",
            }),
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response) as mock_chat:
            await client.analyze_batch(
                batch_id=6,
                experiment_results=[],
                knowledge_graph_summary={},
            )

        call_args = mock_chat.call_args
        assert call_args[1]["temperature"] == 0.4
        assert call_args[1]["max_tokens"] == 1500

    @pytest.mark.asyncio
    async def test_analyze_batch_with_markdown_block(self, client: DashScopeClient) -> None:
        json_response = json.dumps({
            "key_insights": ["i1"],
            "patterns_detected": [],
            "anomalies_flagged": [],
            "recommendations": [],
            "overall_assessment": "ok",
        })
        content = f"```json\n{json_response}\n```"
        mock_response = LLMResponse(
            content=content,
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_batch(
                batch_id=7,
                experiment_results=[],
                knowledge_graph_summary={},
            )

        assert result.key_insights == ["i1"]


# ============================================================================
# 7. Edge cases and integration-style tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and complex scenarios."""

    @pytest.fixture
    def client(self) -> DashScopeClient:
        return DashScopeClient(api_key="test-key")

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, client: DashScopeClient) -> None:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "output": {
                    "choices": [
                        {"message": {"content": "ok"}, "finish_reason": "stop"}
                    ]
                },
                "usage": {},
            }
        )

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMockContextManager(mock_response))
        client._session = mock_session

        tasks = [
            client.chat_completion(messages=[{"role": "user", "content": f"msg{i}"}])
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)

        assert all(isinstance(r, LLMResponse) for r in results)
        assert mock_session.post.call_count == 5

    @pytest.mark.asyncio
    async def test_unicode_content(self, client: DashScopeClient) -> None:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "output": {
                    "choices": [
                        {
                            "message": {"content": "你好世界 🌍"},
                            "finish_reason": "stop",
                        }
                    ]
                },
                "usage": {"input_tokens": 2},
            }
        )

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMockContextManager(mock_response))
        client._session = mock_session

        result = await client.chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert result.content == "你好世界 🌍"

    @pytest.mark.asyncio
    async def test_analyze_findings_with_unicode(self, client: DashScopeClient) -> None:
        json_response = json.dumps({
            "summary": "发现了重要模式",
            "significance": "high",
            "related_concepts": ["概念一", "概念二"],
            "suggested_experiments": ["实验A"],
            "confidence": 0.99,
        }, ensure_ascii=False)

        mock_response = LLMResponse(
            content=json_response,
            model="qwen-plus",
            usage={},
            finish_reason="stop",
        )

        with patch.object(client, "chat_completion", new_callable=AsyncMock, return_value=mock_response):
            result = await client.analyze_findings(["发现一"], "测试")

        assert result.summary == "发现了重要模式"
        assert result.related_concepts == ["概念一", "概念二"]

    @pytest.mark.asyncio
    async def test_large_response_content(self, client: DashScopeClient) -> None:
        large_content = "x" * 100000
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "output": {
                    "choices": [
                        {
                            "message": {"content": large_content},
                            "finish_reason": "length",
                        }
                    ]
                },
                "usage": {"input_tokens": 1, "output_tokens": 50000},
            }
        )

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMockContextManager(mock_response))
        client._session = mock_session

        result = await client.chat_completion(messages=[{"role": "user", "content": "go"}])
        assert result.content == large_content
        assert result.usage["output_tokens"] == 50000

    @pytest.mark.asyncio
    async def test_zero_timeout(self) -> None:
        client = DashScopeClient(api_key="k", timeout=0.0)
        assert client._timeout == 0.0

    @pytest.mark.asyncio
    async def test_negative_timeout(self) -> None:
        # aiohttp may reject negative timeout, but client stores it
        client = DashScopeClient(api_key="k", timeout=-1.0)
        assert client._timeout == -1.0


# ============================================================================
# Helper: async context manager mock
# ============================================================================

class AsyncMockContextManager:
    """Helper to mock `async with session.post(...) as response`."""

    def __init__(self, response: AsyncMock) -> None:
        self._response = response

    async def __aenter__(self) -> AsyncMock:
        return self._response

    async def __aexit__(self, *args: object) -> None:
        pass

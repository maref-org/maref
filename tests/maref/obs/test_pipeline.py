"""Tests for ObsPipeline."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from maref.obs import MarefObsClient, ObsPipeline, TelemetryLevel


@pytest.fixture
def tmp_base() -> Path:
    return Path(tempfile.mkdtemp(prefix="maref_pipeline_test_"))


@pytest.fixture
def client(tmp_base: Path) -> MarefObsClient:
    MarefObsClient.reset_default()
    return MarefObsClient(level=TelemetryLevel.STANDARD, base_dir=tmp_base)


@pytest.fixture
def client_with_events(client: MarefObsClient) -> MarefObsClient:
    for i in range(10):
        client.log_state_transition(f"STATE_{i}", f"STATE_{i + 1}", entropy=i)
    return client


class TestObsPipeline:
    def test_init_defaults(self) -> None:
        p = ObsPipeline()
        assert p._batch_size == 50
        assert p._max_retries == 5
        assert not p.running

    def test_pending_events(self, client_with_events: MarefObsClient) -> None:
        pipeline = ObsPipeline(client=client_with_events, batch_size=50)
        pending = pipeline._get_pending_events()
        assert len(pending) == 10
        seqs = [e["event_sequence"] for e in pending]
        assert seqs == list(range(10))

    def test_pending_after_synced(self, client_with_events: MarefObsClient) -> None:
        pipeline = ObsPipeline(client=client_with_events, batch_size=50)
        pipeline._mark_synced(4)
        pending = pipeline._get_pending_events()
        assert len(pending) == 5
        assert pending[0]["event_sequence"] == 5

    def test_mark_synced_persists(self, client_with_events: MarefObsClient) -> None:
        pipeline = ObsPipeline(client=client_with_events, batch_size=50)
        pipeline._mark_synced(7)
        assert pipeline._read_synced_seq() == 7

    def test_mark_synced_only_increases(self, client_with_events: MarefObsClient) -> None:
        pipeline = ObsPipeline(client=client_with_events, batch_size=50)
        pipeline._mark_synced(7)
        pipeline._mark_synced(3)
        assert pipeline._read_synced_seq() == 7

    def test_no_pending_when_off(self, tmp_base: Path) -> None:
        off_client = MarefObsClient(level=TelemetryLevel.OFF, base_dir=tmp_base)
        pipeline = ObsPipeline(client=off_client, batch_size=50)
        assert pipeline._get_pending_events() == []

    def test_flush_no_events(self, client: MarefObsClient) -> None:
        pipeline = ObsPipeline(client=client)
        sent = asyncio.run(pipeline.flush())
        assert sent == 0

    def test_send_batch_failure(self, client_with_events: MarefObsClient) -> None:
        pipeline = ObsPipeline(client=client_with_events, batch_size=50, max_retries=1, timeout=0.1)
        with patch.object(pipeline, "_get_http_client") as mock_get:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("mock failure"))
            mock_get.return_value = mock_client
            result = asyncio.run(pipeline._send_batch([{"event_sequence": 0}]))
            assert not result

    def test_send_batch_success(self, client_with_events: MarefObsClient) -> None:
        pipeline = ObsPipeline(client=client_with_events, batch_size=50, max_retries=1)
        mock_response = Mock(spec=httpx.Response)
        mock_response.is_success = True

        with patch.object(pipeline, "_get_http_client") as mock_get:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client
            result = asyncio.run(pipeline._send_batch([{"event_sequence": 0}]))
            assert result

    def test_send_batch_retries_on_failure(self) -> None:
        pipeline = ObsPipeline(batch_size=50, max_retries=3, timeout=0.05)
        attempt_count = 0

        async def failing_post(*args: object, **kwargs: object) -> httpx.Response:
            nonlocal attempt_count
            attempt_count += 1
            raise httpx.TimeoutException("timeout")

        with patch.object(pipeline, "_get_http_client") as mock_get:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.post = failing_post
            mock_get.return_value = mock_client
            result = asyncio.run(pipeline._send_batch([{"event_sequence": 0}]))
            assert not result
            assert attempt_count == 3

    def test_start_stop(self, client: MarefObsClient) -> None:
        pipeline = ObsPipeline(client=client)
        assert not pipeline.running
        pipeline.start()
        assert pipeline.running
        pipeline.stop()
        assert not pipeline.running

    def test_start_off_noop(self, tmp_base: Path) -> None:
        off_client = MarefObsClient(level=TelemetryLevel.OFF, base_dir=tmp_base)
        pipeline = ObsPipeline(client=off_client)
        pipeline.start()
        assert not pipeline.running

    def test_close_releases_http(self, client: MarefObsClient) -> None:
        pipeline = ObsPipeline(client=client)
        asyncio.run(pipeline.close())
        assert not pipeline.running

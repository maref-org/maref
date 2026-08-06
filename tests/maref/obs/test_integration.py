"""End-to-end integration tests for the maref-obs telemetry pipeline.

Tests the full flow:
  MarefObsClient → ObsPipeline → HTTP server (real, via stdlib threading)
"""

from __future__ import annotations

import asyncio
import gzip
import json
import tempfile
import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from maref.obs import MarefObsClient, ObsPipeline, TelemetryLevel


class _TestHandler(BaseHTTPRequestHandler):
    """Captures POST bodies for verification."""

    received_bodies: list[bytes] = []

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        _TestHandler.received_bodies.append(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')
        self.wfile.flush()

    def log_message(self, _format: str, *args: object) -> None:
        pass  # silence HTTP server logs


@pytest.fixture
def tmp_base() -> Path:
    return Path(tempfile.mkdtemp(prefix="maref_integration_"))


@pytest.fixture
def echo_server() -> Generator[tuple[int, threading.Thread], None, None]:
    _TestHandler.received_bodies.clear()
    server = HTTPServer(("127.0.0.1", 0), _TestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port, thread
    server.shutdown()
    thread.join(timeout=2)


class TestIntegration:
    def test_pipeline_sends_events_to_server(
        self, tmp_base: Path, echo_server: tuple[int, threading.Thread]
    ) -> None:
        """Verify end-to-end: MarefObsClient → ObsPipeline → HTTP server."""
        MarefObsClient.reset_default()
        port, _ = echo_server

        client = MarefObsClient(level=TelemetryLevel.STANDARD, base_dir=tmp_base)
        client.log_state_transition("INIT", "OBSERVE", entropy=1, reason="startup")
        client.log_state_transition("OBSERVE", "ANALYZE", entropy=2)
        client.log_breaker_trip("test_breaker", depth=1, entropy=3)
        client.log_oscillation(detected=True, rate=12.5, entropy=4)

        pipeline = ObsPipeline(
            client=client,
            endpoint=f"http://127.0.0.1:{port}",
            batch_size=50,
            max_retries=1,
            timeout=5.0,
        )
        sent = asyncio.run(pipeline.flush())

        assert sent == 4, f"Expected 4 events sent, got {sent}"
        assert len(_TestHandler.received_bodies) >= 1

        # Decode gzip body and verify content
        all_body = b"".join(_TestHandler.received_bodies)
        decompressed = gzip.decompress(all_body)
        data = json.loads(decompressed)

        assert "events" in data
        assert len(data["events"]) == 4

        event_types = {e["event_type"] for e in data["events"]}
        assert "state_transition" in event_types
        assert "breaker_trip" in event_types
        assert "oscillation_detected" in event_types

        # Verify standard-level hashing
        for event in data["events"]:
            meta = event.get("metadata", {})
            if event["event_type"] == "state_transition":
                assert "from" in meta
                assert len(meta["from"]) == 16
                assert "to" in meta
                assert len(meta["to"]) == 16

    def test_basic_level_sends_no_metadata(
        self, tmp_base: Path, echo_server: tuple[int, threading.Thread]
    ) -> None:
        """At BASIC level, server should receive events with empty metadata."""
        MarefObsClient.reset_default()
        port, _ = echo_server

        client = MarefObsClient(level=TelemetryLevel.BASIC, base_dir=tmp_base)
        client.log_state_transition("INIT", "OBSERVE", reason="startup")
        client.log_breaker_trip("test_breaker")

        pipeline = ObsPipeline(
            client=client,
            endpoint=f"http://127.0.0.1:{port}",
            batch_size=50,
            max_retries=1,
            timeout=5.0,
        )
        sent = asyncio.run(pipeline.flush())

        assert sent == 2
        all_body = b"".join(_TestHandler.received_bodies)
        data = json.loads(gzip.decompress(all_body))

        for event in data["events"]:
            assert event["metadata"] == {}

    def test_off_level_sends_nothing(self, tmp_base: Path) -> None:
        """At OFF level, pipeline should send zero events."""
        MarefObsClient.reset_default()
        client = MarefObsClient(level=TelemetryLevel.OFF, base_dir=tmp_base)
        pipeline = ObsPipeline(client=client)
        sent = asyncio.run(pipeline.flush())
        assert sent == 0

    def test_synced_file_tracks_progress(
        self, tmp_base: Path, echo_server: tuple[int, threading.Thread]
    ) -> None:
        """After successful flush, .synced file should reflect progress."""
        MarefObsClient.reset_default()
        port, _ = echo_server

        client = MarefObsClient(level=TelemetryLevel.STANDARD, base_dir=tmp_base)
        client.log_state_transition("INIT", "OBSERVE", entropy=1)
        client.log_state_transition("OBSERVE", "ANALYZE", entropy=2)

        pipeline = ObsPipeline(
            client=client,
            endpoint=f"http://127.0.0.1:{port}",
            batch_size=50,
            max_retries=1,
            timeout=5.0,
        )
        sent = asyncio.run(pipeline.flush())

        assert sent == 2

        # Verify .synced file
        synced_path = pipeline._synced_path
        assert synced_path is not None and synced_path.exists()
        raw = synced_path.read_text().strip()
        assert raw == "1"

        # No more pending events
        pending = pipeline._get_pending_events()
        assert len(pending) == 0

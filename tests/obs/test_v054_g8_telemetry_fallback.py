"""Tests for telemetry fallback (INC-2026-08-13-001 / G8)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

from maref.obs.pipeline import ObsPipeline


class TestOfflineFallback:
    def test_record_offline_writes_sqlite(self, tmp_path: Path) -> None:
        events = [
            {"event_type": "state_transition", "timestamp": 100.0, "actor": "sm"},
            {"event_type": "cost_event", "timestamp": 101.0, "model": "glm-5.2"},
        ]
        db_dir = tmp_path / "telemetry"
        with patch.dict(os.environ, {"MAREF_TELEMETRY_LOCAL_DIR": str(db_dir)}):
            ObsPipeline._record_offline(object(), events, reason="endpoint_unreachable")
            assert ObsPipeline.offline_event_count() == 2

        conn = sqlite3.connect(str(db_dir / "events.db"))
        try:
            rows = conn.execute(
                "SELECT event_type, offline_reason, payload FROM telemetry_events ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 2
        assert rows[0][0] == "state_transition"
        assert rows[0][1] == "endpoint_unreachable"
        assert json.loads(rows[0][2])["actor"] == "sm"

    def test_offline_event_count_zero_when_no_db(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"MAREF_TELEMETRY_LOCAL_DIR": str(tmp_path / "nope")}):
            assert ObsPipeline.offline_event_count() == 0

    def test_send_batch_fallback_persists(self, tmp_path: Path) -> None:
        """HTTP 失败后 fallback 落本地 SQLite 且返回 True（数据不丢）。"""
        events = [{"event_type": "cost_event", "timestamp": 200.0, "model": "glm-4.7"}]
        db_dir = tmp_path / "telemetry"

        class FakeClient:
            async def post(self, *a, **k):
                import httpx
                raise httpx.ConnectError("connect failed")  # noqa: BLE001

            async def aclose(self):
                pass

        class FakePipeline:
            _max_retries = 1
            _timeout = 1.0
            _endpoint = "https://example.invalid"
            _http_client = FakeClient()
            _synced_path = tmp_path / ".synced"
            _lock = __import__("threading").Lock()

            async def _get_http_client(self):
                return self._http_client

            def _record_offline(self, evts, reason):
                with patch.dict(os.environ, {"MAREF_TELEMETRY_LOCAL_DIR": str(db_dir)}):
                    ObsPipeline._record_offline(self, evts, reason)

        fp = FakePipeline()
        import asyncio
        result = asyncio.run(ObsPipeline._send_batch(fp, events))
        assert result is True
        with patch.dict(os.environ, {"MAREF_TELEMETRY_LOCAL_DIR": str(db_dir)}):
            assert ObsPipeline.offline_event_count() == 1

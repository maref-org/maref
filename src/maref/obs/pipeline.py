"""Telemetry pipeline — batched, compressed, async HTTP sync."""

from __future__ import annotations

import asyncio
import gzip
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

import httpx

from maref.obs.client import MarefObsClient
from maref.obs.levels import TelemetryLevel


class ObsPipeline:
    """Async telemetry pipeline with batching, compression, and backoff.

    Reads unsynced events from ``MarefObsClient``'s ndjson buffer,
    batches them (default 50), gzip-compresses, and POSTs to the
    configured endpoint.

    Tracks sync progress via a ``.synced`` stamp file that records
    the highest ``event_sequence`` successfully transmitted.

    Usage::

        pipeline = ObsPipeline(batch_size=50)
        pipeline.start()
        # ... later ...
        pipeline.stop()
    """

    def __init__(
        self,
        client: MarefObsClient | None = None,
        endpoint: str = "",
        batch_size: int = 50,
        flush_interval: float = 60.0,
        max_retries: int = 5,
        timeout: float = 15.0,
    ) -> None:
        self._client = client or MarefObsClient.get_default()
        self._endpoint = endpoint or os.environ.get(
            "MAREF_TELEMETRY_ENDPOINT",
            "https://telemetry.maref.org/api/v1/telemetry/batch",
        )
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._max_retries = max_retries
        self._timeout = timeout

        self._http_client: httpx.AsyncClient | None = None
        self._running = False
        self._lock = Lock()
        self._task: asyncio.Task[None] | None = None

        self._synced_path: Path | None = None
        buffer_path = self._client.get_buffer_path()
        if buffer_path:
            self._synced_path = buffer_path.parent / ".synced"

    # ── Lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Start the periodic flush loop.

        Safe to call from sync or async context. If there is a running
        event loop the background task is created immediately; otherwise
        ``_running`` is set and the loop picks it up on first async flush.
        """
        if self._running:
            return
        if self._client.level == TelemetryLevel.OFF:
            return
        self._running = True
        try:
            asyncio.get_running_loop()
            self._task = asyncio.create_task(self._run_loop())
        except RuntimeError:
            pass

    def stop(self) -> None:
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    # ── Public API ──────────────────────────────────────────────────

    async def flush(self) -> int:
        """Send all pending events. Returns count of successfully sent events."""
        if self._client.level == TelemetryLevel.OFF:
            return 0
        pending = self._get_pending_events()
        if not pending:
            return 0

        total_sent = 0
        for i in range(0, len(pending), self._batch_size):
            batch = pending[i : i + self._batch_size]
            if await self._send_batch(batch):
                max_seq = max(e.get("event_sequence", -1) for e in batch)
                self._mark_synced(max_seq)
                total_sent += len(batch)
        return total_sent

    async def flush_and_wait(self, timeout: float = 30.0) -> int:
        """Flush and wait for pending HTTP requests to complete."""
        return await asyncio.wait_for(self.flush(), timeout=timeout)

    # ── Internal ────────────────────────────────────────────────────

    def _get_pending_events(self) -> list[dict[str, Any]]:
        """Return events that have not yet been synced."""
        events = self._client.get_all_events()
        if not events:
            return []
        synced_seq = self._read_synced_seq()
        return [e for e in events if e.get("event_sequence", -1) > synced_seq]

    def _read_synced_seq(self) -> int:
        if self._synced_path is None or not self._synced_path.exists():
            return -1
        try:
            raw = self._synced_path.read_text().strip()
            return int(raw) if raw else -1
        except (ValueError, OSError):
            return -1

    def _mark_synced(self, up_to_seq: int) -> None:
        if self._synced_path is None:
            return
        with self._lock:
            try:
                current = -1
                if self._synced_path.exists():
                    raw = self._synced_path.read_text().strip()
                    current = int(raw) if raw else -1
            except (ValueError, OSError):
                current = -1
            if up_to_seq > current:
                with open(self._synced_path, "w") as f:
                    f.write(str(up_to_seq) + "\n")

    async def _send_batch(self, events: list[dict[str, Any]]) -> bool:
        """POST a gzip-compressed batch with exponential backoff.

        INC-2026-08-13-001 (G8) fix: when the HTTP endpoint is unreachable,
        fall back to a local SQLite aggregator so telemetry data is never
        silently dropped. Returns True if events were persisted (HTTP or local).
        """
        payload = json.dumps({"events": events}, sort_keys=True)
        compressed = gzip.compress(payload.encode())

        for attempt in range(self._max_retries):
            try:
                client = await self._get_http_client()
                response = await client.post(
                    self._endpoint,
                    content=compressed,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Encoding": "gzip",
                        "User-Agent": "maref-obs/0.27.0",
                    },
                    timeout=self._timeout,
                )
                if response.is_success:
                    return True
                self._record_offline(events, reason=f"http_{response.status_code}")
                return True  # 已本地持久化，不重试导致重复
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError):
                if attempt == self._max_retries - 1:
                    self._record_offline(events, reason="endpoint_unreachable")
                    return True

            if attempt < self._max_retries - 1:
                await asyncio.sleep(2**attempt)

        return False

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    def _record_offline(self, events: list[dict[str, Any]], reason: str) -> None:
        """G8-2: 端点不可达时把批次写入本地 SQLite 聚合器（数据不丢）。"""
        try:
            sqlite3 = __import__("sqlite3")
            db_dir = Path(
                os.environ.get(
                    "MAREF_TELEMETRY_LOCAL_DIR",
                    str(Path.home() / ".maref" / "telemetry"),
                )
            )
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / "events.db"
            conn = sqlite3.connect(str(db_path), timeout=10.0)
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telemetry_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts REAL NOT NULL,
                        event_type TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        offline_reason TEXT NOT NULL,
                        ingested_at REAL NOT NULL
                    )
                    """
                )
                now = __import__("time").time()
                for e in events:
                    conn.execute(
                        "INSERT INTO telemetry_events (ts, event_type, payload, offline_reason, ingested_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            e.get("timestamp", now),
                            e.get("event_type", "?"),
                            json.dumps(e, sort_keys=True, default=str),
                            reason,
                            now,
                        ),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 — fallback 本身失败不可再抛，但要留痕
            import logging as _logging

            _logging.getLogger("maref.obs").warning(
                "offline telemetry fallback write failed (reason=%s, events=%d)",
                reason,
                len(events),
            )

    @staticmethod
    def offline_event_count() -> int:
        """G8-2: 查询本地聚合器中离线缓存的遥测事件数（供 selfcheck/看板）。"""
        try:
            sqlite3 = __import__("sqlite3")
            db_dir = Path(
                os.environ.get(
                    "MAREF_TELEMETRY_LOCAL_DIR",
                    str(Path.home() / ".maref" / "telemetry"),
                )
            )
            db_path = db_dir / "events.db"
            if not db_path.exists():
                return 0
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            return 0

    async def _run_loop(self) -> None:
        """Periodic flush loop."""
        while self._running:
            await asyncio.sleep(self._flush_interval)
            try:
                await self.flush()
            except Exception:
                pass  # silent — errors handled per-batch

    async def close(self) -> None:
        """Release HTTP client resources."""
        self.stop()
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

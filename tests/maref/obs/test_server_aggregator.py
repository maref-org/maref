"""Tests for the telemetry-server OscillationAggregator."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

from maref.obs.aggregator import ObsAggregator

# telemetry-server/ dir has a hyphen, so add it to sys.path manually
_ts_path = Path(__file__).resolve().parent.parent.parent.parent / "telemetry-server"
if _ts_path.exists():
    sys.path.insert(0, str(_ts_path))
else:
    cwd_ts = Path.cwd() / "telemetry-server"
    if cwd_ts.exists():
        sys.path.insert(0, str(cwd_ts))


@pytest.fixture(scope="class")
def aggregator_module():
    import importlib

    try:
        return importlib.import_module("aggregator")
    except ModuleNotFoundError:
        # Last resort: try relative to workspace root
        for p in [Path.cwd(), Path.cwd().parent, Path.cwd().parent.parent]:
            ts = p / "telemetry-server"
            if ts.exists():
                sys.path.insert(0, str(ts))
                return importlib.import_module("aggregator")
        raise


class TestOscillationAggregator:
    def setup_method(self) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '',
                timestamp REAL NOT NULL,
                received_at REAL NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_version ON events(version);

            CREATE TABLE IF NOT EXISTS aggregated_params (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                param_name TEXT NOT NULL UNIQUE,
                param_value TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '',
                sample_size INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            );
        """)
        self._conn.commit()

    def _insert_event(self, event_type: str, version: str = "0.27.0") -> None:
        self._conn.execute(
            """INSERT INTO events (session_id, event_type, version, timestamp, received_at, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("test-session", event_type, version, time.time(), time.time(), "{}"),
        )
        self._conn.commit()

    def teardown_method(self) -> None:
        self._conn.close()

    def test_aggregate_no_events(self) -> None:
        from aggregator import OscillationAggregator

        agg = OscillationAggregator(min_samples=1)
        result = agg.aggregate(self._conn)
        assert result["versions_processed"] == 0
        assert result["recommendations_written"] == 0

    def test_aggregate_insufficient_samples(self) -> None:
        from aggregator import OscillationAggregator

        self._insert_event("oscillation_detected", "0.27.0")
        agg = OscillationAggregator(min_samples=5)
        result = agg.aggregate(self._conn)
        v = result["per_version"]["0.27.0"]
        assert not v["recommended"]
        assert v["reason"] == "insufficient_samples"

    def test_aggregate_generates_recommendation(self) -> None:
        from aggregator import OscillationAggregator

        for _ in range(10):
            self._insert_event("oscillation_detected", "0.27.0")
            self._insert_event("state_transition", "0.27.0")

        agg = OscillationAggregator(min_samples=5, iqr_multiplier=1.5)
        result = agg.aggregate(self._conn)

        v = result["per_version"]["0.27.0"]
        assert v["recommended"]
        assert v["recommended_max_rate"] > 0
        assert v["oscillation_rate"] == 1.0
        assert v["sample_size"] == 10

    def test_aggregate_writes_to_params_table(self) -> None:
        from aggregator import OscillationAggregator

        for _ in range(10):
            self._insert_event("oscillation_detected", "0.27.0")
            self._insert_event("state_transition", "0.27.0")

        agg = OscillationAggregator(min_samples=5)
        agg.aggregate(self._conn)

        rows = self._conn.execute(
            "SELECT param_name, param_value FROM aggregated_params"
        ).fetchall()
        params = {r["param_name"]: r["param_value"] for r in rows}
        assert "recommended_max_rate" in params
        assert "sample_size" in params

    def test_aggregate_multiple_versions(self) -> None:
        from aggregator import OscillationAggregator

        for _ in range(10):
            self._insert_event("oscillation_detected", "0.26.0")
            self._insert_event("state_transition", "0.26.0")
            self._insert_event("oscillation_detected", "0.27.0")
            self._insert_event("state_transition", "0.27.0")

        agg = OscillationAggregator(min_samples=5)
        result = agg.aggregate(self._conn)
        assert result["versions_processed"] == 2
        assert result["recommendations_written"] == 2

    def test_zero_transitions_no_division_by_zero(self) -> None:
        from aggregator import OscillationAggregator

        for _ in range(10):
            self._insert_event("oscillation_detected", "0.27.0")

        agg = OscillationAggregator(min_samples=5)
        result = agg.aggregate(self._conn)
        v = result["per_version"]["0.27.0"]
        assert not v["recommended"]

    def test_aggregator_config_reflects_updated_params(self) -> None:
        from aggregator import OscillationAggregator

        for _ in range(10):
            self._insert_event("oscillation_detected", "0.27.0")
            self._insert_event("state_transition", "0.27.0")

        agg = OscillationAggregator(min_samples=5)
        agg.aggregate(self._conn)

        rows = self._conn.execute(
            "SELECT param_name, param_value, sample_size FROM aggregated_params ORDER BY param_name"
        ).fetchall()
        assert len(rows) >= 2

"""MAREF Telemetry Aggregation Server — minimal FastAPI skeleton."""

from __future__ import annotations

import gzip
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="MAREF Telemetry",
    version="0.1.0",
    description="Privacy-first telemetry aggregation for the MAREF governance layer.",
)

allowed_origins = [
    origin.strip()
    for origin in os.environ.get("MAREF_TELEMETRY_ALLOWED_ORIGINS", "http://localhost:3000").split(
        ","
    )
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

DB_PATH = os.environ.get(
    "MAREF_TELEMETRY_DB", str(Path.home() / ".maref" / "telemetry" / "events.db")
)

_conn: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = Path(DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(path))
        _conn.row_factory = sqlite3.Row
        init_db(_conn)
    return _conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
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
        CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);

        CREATE TABLE IF NOT EXISTS aggregated_params (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            param_name TEXT NOT NULL UNIQUE,
            param_value TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '',
            sample_size INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL
        );
    """)
    conn.commit()


# ── Helpers ──────────────────────────────────────────────────────────


def _now() -> float:
    return time.time()


# ── Endpoints ────────────────────────────────────────────────────────


@app.get("/api/v1/telemetry/config")
async def get_config(version: str = "") -> dict[str, Any]:
    """Return aggregated parameters derived from community telemetry."""
    conn = get_db()
    rows = conn.execute(
        "SELECT param_name, param_value, sample_size FROM aggregated_params ORDER BY param_name"
    ).fetchall()

    parameters: dict[str, Any] = {}
    meta: dict[str, Any] = {
        "updated_at": _now(),
        "version_filter": version or "all",
    }

    for row in rows:
        key = row["param_name"]
        raw = row["param_value"]
        try:
            parameters[key] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            parameters[key] = raw
        meta[f"{key}_sample_size"] = row["sample_size"]

    return {
        "meta": meta,
        "parameters": parameters,
    }


@app.post("/api/v1/telemetry/batch")
async def receive_batch(request: Request) -> dict[str, Any]:
    """Receive and store a batch of governance events.

    Accepts gzip-compressed or plain JSON.
    """
    raw = await request.body()
    content_encoding = request.headers.get("content-encoding", "")

    if "gzip" in content_encoding:
        try:
            raw = gzip.decompress(raw)
        except Exception:
            return {"ok": False, "error": "invalid_gzip"}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid_json"}

    events = data if isinstance(data, list) else data.get("events", [])
    if not events:
        return {"ok": False, "error": "empty_batch"}

    conn = get_db()
    received_at = _now()
    count = 0

    for event in events:
        try:
            conn.execute(
                """INSERT INTO events (session_id, event_type, version, timestamp, received_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event.get("session_id", ""),
                    event.get("event_type", "unknown"),
                    event.get("version", ""),
                    event.get("timestamp", received_at),
                    received_at,
                    json.dumps(event.get("metadata", {}), sort_keys=True),
                ),
            )
            count += 1
        except Exception:
            pass

    conn.commit()
    return {"ok": True, "received": count}


@app.post("/api/v1/telemetry/aggregate")
async def run_aggregation() -> dict[str, Any]:
    """Trigger oscillation parameter aggregation and write recommendations."""
    from aggregator import OscillationAggregator

    conn = get_db()
    agg = OscillationAggregator()
    result = agg.aggregate(conn)
    return result


@app.get("/api/v1/telemetry/stats")
async def get_stats() -> dict[str, Any]:
    """Basic query endpoint for debugging."""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
    by_type = conn.execute(
        "SELECT event_type, COUNT(*) as c FROM events GROUP BY event_type ORDER BY c DESC"
    ).fetchall()
    by_version = conn.execute(
        "SELECT version, COUNT(*) as c FROM events GROUP BY version ORDER BY c DESC"
    ).fetchall()

    return {
        "total_events": total,
        "by_type": {r["event_type"]: r["c"] for r in by_type},
        "by_version": {r["version"]: r["c"] for r in by_version},
    }


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "maref-telemetry"}

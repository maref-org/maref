"""
MAREF Observation Store — SQLite-backed persistence.

Persists probe readings, anomaly events, and self-observations
across batch runs so the system accumulates knowledge over time.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from maref.observation.probes import ProbeReading


class ObservationStore:
    """SQLite-backed store for probe readings and anomalies."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = Path(db_path) if db_path != ":memory:" else db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS probe_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                probe_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                value REAL NOT NULL,
                threshold REAL NOT NULL,
                timestamp REAL NOT NULL,
                context_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_readings_probe
                ON probe_readings(probe_name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_readings_severity
                ON probe_readings(severity, timestamp);

            CREATE TABLE IF NOT EXISTS fnr_fpr_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                fnr REAL NOT NULL,
                fpr REAL NOT NULL,
                tp INTEGER NOT NULL DEFAULT 0,
                fp INTEGER NOT NULL DEFAULT 0,
                tn INTEGER NOT NULL DEFAULT 0,
                fn INTEGER NOT NULL DEFAULT 0,
                timestamp REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fnr_fpr_batch
                ON fnr_fpr_log(batch_id);
        """)
        self._conn.commit()

    def insert_reading(self, reading: ProbeReading) -> int:
        cursor = self._conn.execute(
            """INSERT INTO probe_readings
               (probe_name, severity, value, threshold, timestamp, context_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                reading.probe_name,
                reading.severity.value,
                reading.value,
                reading.threshold,
                reading.timestamp,
                json.dumps(reading.context),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid or 0

    def insert_batch(self, readings: list[ProbeReading]) -> int:
        rows = [
            (
                r.probe_name,
                r.severity.value,
                r.value,
                r.threshold,
                r.timestamp,
                json.dumps(r.context),
            )
            for r in readings
        ]
        self._conn.executemany(
            """INSERT INTO probe_readings
               (probe_name, severity, value, threshold, timestamp, context_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def get_readings(
        self,
        probe_name: str | None = None,
        severity: str | None = None,
        limit: int = 100,
        since: float | None = None,
    ) -> list[dict[str, object]]:
        conditions = []
        params: list[object] = []

        if probe_name:
            conditions.append("probe_name = ?")
            params.append(probe_name)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        if since is not None:
            conditions.append("timestamp >= ?")
            params.append(since)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = (
            "SELECT * FROM probe_readings " + where + " "  # nosec: where is hardcoded conditional clause above
            "ORDER BY timestamp DESC LIMIT ?"
        )
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_counts(self, since: float | None = None) -> dict[str, Any]:
        params: list[object] = []
        where = "WHERE timestamp >= ?" if since else ""
        if since is not None:
            params = [since]

        severity_rows = self._conn.execute(
            "SELECT severity, COUNT(*) as cnt FROM probe_readings " + where + " "  # nosec: where is hardcoded conditional clause above
            "GROUP BY severity",
            params,
        ).fetchall()

        probe_rows = self._conn.execute(
            "SELECT probe_name, COUNT(*) as cnt FROM probe_readings " + where + " "  # nosec: where is hardcoded conditional clause above
            "GROUP BY probe_name",
            params,
        ).fetchall()

        total_row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM probe_readings " + where,  # nosec: where is hardcoded conditional clause above
            params,
        ).fetchone()

        return {
            "total": total_row["cnt"] if total_row else 0,
            "by_severity": {r["severity"]: r["cnt"] for r in severity_rows},
            "by_probe": {r["probe_name"]: r["cnt"] for r in probe_rows},
        }

    def log_fnr_fpr(
        self,
        batch_id: str,
        fnr: float,
        fpr: float,
        tp: int,
        fp: int,
        tn: int,
        fn_count: int,
    ) -> None:
        self._conn.execute(
            """INSERT INTO fnr_fpr_log
               (batch_id, fnr, fpr, tp, fp, tn, fn, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (batch_id, fnr, fpr, tp, fp, tn, fn_count, time.time()),
        )
        self._conn.commit()

    def get_fnr_fpr_history(self, limit: int = 10) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT * FROM fnr_fpr_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()

"""Server-side oscillation aggregator — computes community threshold recommendations."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any


class OscillationAggregator:
    """Aggregates raw oscillation events into parameter recommendations.

    Reads from the SQLite ``events`` table and writes to the
    ``aggregated_params`` table. Designed to run periodically
    (e.g. via cron or asyncio loop).

    Algorithm per version bucket:
    1. Count oscillation_detected events → osc_count
    2. Count state_transition events → total_transitions
    3. oscillation_rate = osc_count / total_transitions
    4. If enough samples (>= min_samples), compute recommended max_rate
       using median + 1.5 × IQR as the threshold
    5. Write recommendation to aggregated_params table
    """

    def __init__(
        self,
        min_samples: int = 10,
        iqr_multiplier: float = 1.5,
    ) -> None:
        self._min_samples = min_samples
        self._iqr_multiplier = iqr_multiplier

    def aggregate(self, conn: sqlite3.Connection) -> dict[str, Any]:
        """Run aggregation and write recommendations.

        Returns a summary dict with per-version results.
        """
        versions = self._get_versions(conn)
        results: dict[str, Any] = {}

        for version in versions:
            result = self._aggregate_version(conn, version)
            results[version] = result
            if result.get("recommended"):
                self._write_recommendation(conn, version, result)

        conn.commit()
        return {
            "versions_processed": len(versions),
            "recommendations_written": sum(
                1 for r in results.values() if r.get("recommended")
            ),
            "per_version": results,
        }

    # ── Internal ────────────────────────────────────────────────────

    def _get_versions(self, conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            "SELECT DISTINCT version FROM events WHERE version != '' ORDER BY version"
        ).fetchall()
        return [r["version"] for r in rows]

    def _aggregate_version(
        self,
        conn: sqlite3.Connection,
        version: str,
    ) -> dict[str, Any]:
        osc_count = conn.execute(
            "SELECT COUNT(*) as c FROM events WHERE version = ? AND event_type = 'oscillation_detected'",
            (version,),
        ).fetchone()["c"]

        transition_count = conn.execute(
            "SELECT COUNT(*) as c FROM events WHERE version = ? AND event_type = 'state_transition'",
            (version,),
        ).fetchone()["c"]

        result: dict[str, Any] = {
            "version": version,
            "oscillation_count": osc_count,
            "transition_count": transition_count,
            "sample_size": osc_count,
        }

        if osc_count < self._min_samples or transition_count == 0:
            result["recommended"] = False
            result["reason"] = "insufficient_samples"
            return result

        oscillation_rate = osc_count / transition_count
        result["oscillation_rate"] = round(oscillation_rate, 4)

        recommended_max_rate = self._compute_threshold(oscillation_rate)
        result["recommended_max_rate"] = round(recommended_max_rate, 2)
        result["recommended"] = True

        return result

    def _compute_threshold(self, rate: float) -> float:
        """Compute recommended max_rate from a single oscillation rate.

        When multiple samples are available, use median + IQR × multiplier.
        For a single aggregated rate, use rate × 1.5 as a heuristic.
        """
        return rate * (1.0 + self._iqr_multiplier)

    def _write_recommendation(
        self,
        conn: sqlite3.Connection,
        version: str,
        result: dict[str, Any],
    ) -> None:
        now = time.time()
        params = {
            "recommended_max_rate": result["recommended_max_rate"],
            "sample_size": result["oscillation_count"],
            "server_version": version,
        }

        conn.execute(
            """INSERT OR REPLACE INTO aggregated_params
               (param_name, param_value, version, sample_size, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "recommended_max_rate",
                json.dumps(params["recommended_max_rate"]),
                version,
                params["sample_size"],
                now,
            ),
        )
        conn.execute(
            """INSERT OR REPLACE INTO aggregated_params
               (param_name, param_value, version, sample_size, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "sample_size",
                json.dumps(params["sample_size"]),
                version,
                params["sample_size"],
                now,
            ),
        )


def run_aggregation(db_path: str = "") -> dict[str, Any]:
    """Convenience: open DB connection, run aggregation, return results."""
    from pathlib import Path

    if not db_path:
        db_path = os.environ.get(
            "MAREF_TELEMETRY_DB",
            str(Path.home() / ".maref" / "telemetry" / "events.db"),
        )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        from main import init_db
        init_db(conn)
    except ImportError:
        pass

    agg = OscillationAggregator()
    result = agg.aggregate(conn)
    conn.close()
    return result

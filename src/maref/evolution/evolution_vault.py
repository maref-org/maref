"""Evolution vault — YAML-based daily report storage + SQLite round metrics.

Two classes:
- EvolutionVault (YAML): daily report storage, used by DailyEvolutionLoop
- RoundVault (SQLite): per-round system metrics for trend analysis
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

# ── YAML-based vault (original, used by DailyEvolutionLoop) ──────────

class EvolutionVault:
    def __init__(self, base_dir: str | Path = ".evolution_vault") -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def start_day(self, day: str) -> Path:
        day_dir = self._base_dir / day
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def load_day(self, day: str) -> dict[str, Any]:
        day_dir = self._base_dir / day
        if not day_dir.exists():
            return {}
        loaded: dict[str, Any] = {}
        for name in ("metrics_snapshot", "experiment", "report", "next_plan"):
            path = day_dir / f"{name}.yaml"
            if path.exists():
                loaded[name] = self._read_yaml(path)
        return loaded

    def write_metrics_snapshot(self, day_dir: Path, snapshot: dict[str, Any]) -> None:
        self._write_yaml(day_dir / "metrics_snapshot.yaml", snapshot)

    def write_experiment_result(self, day_dir: Path, result: Any) -> None:
        self._write_yaml(day_dir / "experiment.yaml", {"result": str(result)})

    def write_daily_report(self, day: str, report: Any) -> None:
        path = self._base_dir / day / "report.yaml"
        self._write_yaml(path, report.to_dict() if hasattr(report, "to_dict") else {"report": str(report)})

    def write_next_plan(self, day_dir: Path, plan: Any) -> None:
        self._write_yaml(day_dir / "next_plan.yaml", plan if isinstance(plan, dict) else {"plan": str(plan)})

    @staticmethod
    def _read_yaml(path: str | Path) -> dict[str, Any]:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _write_yaml(path: str | Path, data: Any) -> None:
        import yaml
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)


# ── SQLite-based vault (new, for round-level metrics) ────────────────

_ROUND_SCHEMA = """
CREATE TABLE IF NOT EXISTS rounds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    round_num       INTEGER NOT NULL,
    cycle_id        TEXT NOT NULL,
    timestamp       REAL NOT NULL,
    fnr             REAL,
    fpr             REAL,
    test_pass_rate  REAL,
    coverage_pct    REAL,
    total_tests     INTEGER,
    source_files    INTEGER,
    total_lines     INTEGER,
    git_commits_30d INTEGER,
    module_count    INTEGER,
    governance_state TEXT,
    cb_state        TEXT,
    stop_reason     TEXT,
    meta_json       TEXT
);
"""


class RoundVault:
    """Cross-round persistence for evolution metrics and decisions.

    Stores per-round system snapshots, FNR/FPR, coverage, and metadata
    in SQLite for trend analysis. Complements EvolutionVault (YAML).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        if self._db_path.suffix not in (".db", ".sqlite"):
            self._db_path = self._db_path / "evolution.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.executescript(_ROUND_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self._db_path))
        c.row_factory = sqlite3.Row
        return c

    def record_round(self, round_num: int, cycle_id: str, metrics: dict[str, Any],
                     stop_reason: str = "") -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                """INSERT INTO rounds (round_num, cycle_id, timestamp, fnr, fpr,
                   test_pass_rate, coverage_pct, total_tests, source_files,
                   total_lines, git_commits_30d, module_count, governance_state,
                   cb_state, stop_reason, meta_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (round_num, cycle_id, time.time(),
                 metrics.get("fnr"), metrics.get("fpr"),
                 metrics.get("test_pass_rate"), metrics.get("coverage_pct"),
                 metrics.get("total_tests"), metrics.get("source_file_count"),
                 metrics.get("total_lines"), metrics.get("git_commit_count_30d"),
                 metrics.get("module_count"), metrics.get("governance_state"),
                 metrics.get("cb_state"), stop_reason,
                 json.dumps(metrics)),
            )
            conn.commit()
            return cur.lastrowid or 0
        finally:
            conn.close()

    def get_latest_round(self) -> dict[str, Any] | None:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_trend(self, metric: str, last_n: int = 20) -> list[dict[str, Any]]:
        valid = {"fnr", "fpr", "test_pass_rate", "coverage_pct", "total_tests",
                 "source_files", "total_lines", "git_commits_30d"}
        if metric not in valid:
            return []
        conn = self._conn()
        try:
            rows = conn.execute(
                f"SELECT round_num, {metric} AS val, timestamp FROM rounds "
                f"WHERE {metric} IS NOT NULL ORDER BY id DESC LIMIT ?", (last_n,)
            ).fetchall()
            return [{"round": r["round_num"], "value": r["val"], "timestamp": r["timestamp"]}
                    for r in reversed(rows)]
        finally:
            conn.close()

    def get_all_rounds(self) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM rounds ORDER BY id").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def close(self) -> None:
        pass


__all__ = ["EvolutionVault", "RoundVault"]

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


def _default_db_path() -> Path:
    return Path.home() / ".maref" / "metrics.db"


TABLES = {
    "governance_metrics": "CREATE TABLE IF NOT EXISTS governance_metrics (id INTEGER PRIMARY KEY, timestamp TEXT, name TEXT, value REAL, labels TEXT, agent_id TEXT)",
    "guardrail_metrics": "CREATE TABLE IF NOT EXISTS guardrail_metrics (id INTEGER PRIMARY KEY, timestamp TEXT, name TEXT, value REAL, labels TEXT, agent_id TEXT)",
    "cost_metrics": "CREATE TABLE IF NOT EXISTS cost_metrics (id INTEGER PRIMARY KEY, timestamp TEXT, name TEXT, value REAL, labels TEXT, agent_id TEXT)",
    "telemetry_metrics": "CREATE TABLE IF NOT EXISTS telemetry_metrics (id INTEGER PRIMARY KEY, timestamp TEXT, name TEXT, value REAL, labels TEXT, agent_id TEXT)",
}


def _validate_table(table: str) -> str:
    if table not in TABLES:
        msg = f"Unknown table '{table}'. Valid: {', '.join(TABLES)}"
        raise ValueError(msg)
    return table


class MetricStore:
    """SQLite-backed metric store with four predefined metric tables.

    Supports recording and querying governance, guardrail, cost, and telemetry
    metrics. Uses WAL journal mode for concurrent read/write performance.

    Attributes:
        _path: Path to the SQLite database file.
        _conn: Cached SQLite connection (lazy initialized).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize the metric store.

        Creates the database directory and initializes all four metric tables
        if they do not already exist.

        Args:
            db_path: Path to the SQLite database file. Defaults to ~/.maref/metrics.db.
        """
        self._path = Path(db_path) if db_path else _default_db_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        for _table, ddl in TABLES.items():
            conn.execute(ddl)
        conn.commit()

    def record(
        self,
        name: str,
        value: float,
        labels: dict[str, Any] | None = None,
        agent_id: str | None = None,
        table: str = "telemetry_metrics",
    ) -> None:
        """Record a metric entry.

        Inserts a row with the current UTC timestamp into the specified table.

        Args:
            name: Metric name (e.g. 'guardrail_check', 'cost').
            value: Numeric value of the metric.
            labels: Optional dimension labels as key-value pairs.
            agent_id: Optional agent identifier for the metric.
            table: Target table name. Must be one of TABLES keys.

        Raises:
            ValueError: If table name is not recognized.
        """
        _validate_table(table)
        conn = self._get_conn()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        labels_json = json.dumps(labels or {}, separators=(",", ":"))
        conn.execute(
            f"INSERT INTO {table} (timestamp, name, value, labels, agent_id) VALUES (?, ?, ?, ?, ?)",
            (now, name, value, labels_json, agent_id or ""),
        )
        conn.commit()

    def query(
        self,
        name: str,
        since: str | None = None,
        until: str | None = None,
        agent_id: str | None = None,
        limit: int = 1000,
        table: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query metric entries by name with optional filters.

        Searches across all tables or a specific table, sorted by timestamp
        descending.

        Args:
            name: Metric name to filter by.
            since: ISO 8601 timestamp for the lower bound (inclusive).
            until: ISO 8601 timestamp for the upper bound (inclusive).
            agent_id: Filter by agent identifier.
            limit: Maximum number of results to return (default 1000).
            table: Optional table name to restrict the search.

        Returns:
            List of metric dictionaries with id, timestamp, name, value,
            labels, and agent_id keys.
        """
        conn = self._get_conn()
        results: list[dict[str, Any]] = []
        tables_to_search = [table] if table else list(TABLES)
        for tbl in tables_to_search:
            _validate_table(tbl)
            parts = ["SELECT * FROM", tbl, "WHERE name = ?"]
            params: list[Any] = [name]
            if since:
                parts.append("AND timestamp >= ?")
                params.append(since)
            if until:
                parts.append("AND timestamp <= ?")
                params.append(until)
            if agent_id:
                parts.append("AND agent_id = ?")
                params.append(agent_id)
            parts.append("ORDER BY timestamp DESC LIMIT ?")
            params.append(limit)
            query = " ".join(parts)
            rows = conn.execute(query, params).fetchall()
            for row in rows:
                results.append(
                    {
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "name": row["name"],
                        "value": row["value"],
                        "labels": json.loads(row["labels"]) if row["labels"] else {},
                        "agent_id": row["agent_id"],
                    }
                )
        results.sort(key=lambda r: r["timestamp"], reverse=True)
        return results[:limit]

    def query_aggregate(
        self,
        name: str,
        operation: str = "avg",
        since: str | None = None,
        table: str | None = None,
    ) -> float:
        """Run an aggregate query (AVG, SUM, MAX, MIN, COUNT) on a metric.

        Args:
            name: Metric name to aggregate.
            operation: Aggregate function — 'avg', 'sum', 'max', 'min', or 'count'.
            since: Optional ISO 8601 lower bound timestamp.
            table: Optional table name to restrict the search.

        Returns:
            The aggregate value as a float.
        """
        conn = self._get_conn()
        op_map = {"avg": "AVG", "sum": "SUM", "max": "MAX", "min": "MIN", "count": "COUNT"}
        sql_op = op_map.get(operation, "AVG")
        tables_to_search = [table] if table else list(TABLES)
        selects: list[str] = []
        params: list[Any] = []
        for tbl in tables_to_search:
            _validate_table(tbl)
            selects.append(f"SELECT value FROM {tbl} WHERE name = ?")
            params.append(name)
            if since:
                selects[-1] += " AND timestamp >= ?"
                params.append(since)
        if not selects:
            return 0.0
        union_query = f"SELECT {sql_op}(value) as agg FROM ({' UNION ALL '.join(selects)})"
        row = conn.execute(union_query, params).fetchone()
        return row["agg"] if row and row["agg"] is not None else 0.0

    def prune(self, retention_days: int = 90) -> int:
        """Delete metric entries older than the retention period.

        Args:
            retention_days: Number of days to retain (default 90).

        Returns:
            Total number of rows deleted across all tables.
        """
        conn = self._get_conn()
        cutoff = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - retention_days * 86400)
        )
        total = 0
        for table in TABLES:
            cursor = conn.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,))
            total += cursor.rowcount
        conn.commit()
        return total

    def get_table_stats(self) -> dict[str, int]:
        """Get row counts for all metric tables.

        Returns:
            Dictionary mapping table names to their row counts.
        """
        conn = self._get_conn()
        stats: dict[str, int] = {}
        for table in TABLES:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[table] = row["cnt"] if row else 0
        return stats

    def close(self) -> None:
        """Close the database connection, if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

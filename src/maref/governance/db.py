"""
MAREF 标准数据库接口

封装 SQLite 连接管理、连接池和迁移机制。
解决审计问题 P6：5 处裸 SQLite 违规。
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class DatabaseManager:
    """
    Thread-local SQLite connection manager with automatic commit/rollback.

    Usage:
        db = DatabaseManager("/path/to/db.sqlite")
        with db.connection() as conn:
            conn.execute("SELECT ...")
        # Or use convenience methods:
        db.execute("INSERT INTO ...", (value,))
        rows = db.fetchall("SELECT * FROM ...")
    """

    def __init__(self, db_path: str | Path, pool_size: int = 5) -> None:
        self._db_path = str(db_path)
        self._pool_size = pool_size
        self._local = threading.local()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self):
        """Yield a thread-local SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        try:
            yield self._local.conn
        except Exception:
            self._local.conn.rollback()
            raise

    def execute(
        self, sql: str, parameters: tuple[Any, ...] | list[Any] | None = None
    ) -> sqlite3.Cursor:
        """Execute SQL with automatic connection management."""
        with self.connection() as conn:
            if parameters is None:
                cur = conn.execute(sql)
            elif isinstance(parameters, list):
                # List of tuples -> executemany; plain list -> single execute with tuple()
                if parameters and isinstance(parameters[0], tuple):
                    cur = conn.executemany(sql, parameters)
                else:
                    cur = conn.execute(sql, parameters)
            else:
                cur = conn.execute(sql, parameters)
            conn.commit()
            return cur

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        """Execute a SQL script."""
        with self.connection() as conn:
            cur = conn.executescript(sql_script)
            conn.commit()
            return cur

    def fetchall(self, sql: str, parameters: tuple[Any, ...] | None = None) -> list[sqlite3.Row]:
        """Execute SELECT and return all rows."""
        cur = self.execute(sql, parameters)
        return cur.fetchall()

    def fetchone(self, sql: str, parameters: tuple[Any, ...] | None = None) -> sqlite3.Row | None:
        """Execute SELECT and return first row."""
        cur = self.execute(sql, parameters)
        return cur.fetchone()

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        row = self.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return row is not None

    def close(self) -> None:
        """Close the thread-local connection if open."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # --- Schema Migration Support ---

    def _ensure_migrations_table(self) -> None:
        """Create the schema_migrations tracking table if not exists."""
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at REAL NOT NULL,
                description TEXT
            )
            """
        )

    def current_schema_version(self) -> int:
        """Return the current schema version (0 if no migrations applied)."""
        self._ensure_migrations_table()
        if not self.table_exists("schema_migrations"):
            return 0
        row = self.fetchone("SELECT MAX(version) as max_version FROM schema_migrations")
        return row["max_version"] or 0 if row is not None else 0

    def migrate(
        self,
        target_version: int,
        migrations: dict[int, str],
        descriptions: dict[int, str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute schema migrations from current_version + 1 to target_version.

        Args:
            target_version: Desired schema version.
            migrations: Mapping version -> SQL script to execute.
            descriptions: Optional mapping version -> human-readable description.

        Returns:
            List of applied migration records.
        """
        import time

        self._ensure_migrations_table()
        current = self.current_schema_version()
        applied: list[dict[str, Any]] = []

        for version in range(current + 1, target_version + 1):
            if version not in migrations:
                raise ValueError(f"Migration script for version {version} not found")

            sql = migrations[version]
            self.executescript(sql)
            self.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (
                    version,
                    time.time(),
                    descriptions.get(version, "") if descriptions else "",
                ),
            )
            applied.append(
                {
                    "version": version,
                    "description": descriptions.get(version, "") if descriptions else "",
                }
            )

        return applied

    def rollback(
        self,
        target_version: int,
        rollbacks: dict[int, str],
    ) -> list[dict[str, Any]]:
        """
        Rollback schema migrations from current_version down to target_version.

        Args:
            target_version: Desired schema version after rollback.
            rollbacks: Mapping version -> SQL script to execute for rollback.

        Returns:
            List of rolled back migration records.
        """
        current = self.current_schema_version()
        rolled_back: list[dict[str, Any]] = []

        for version in range(current, target_version, -1):
            if version not in rollbacks:
                raise ValueError(f"Rollback script for version {version} not found")

            sql = rollbacks[version]
            self.executescript(sql)
            self.execute(
                "DELETE FROM schema_migrations WHERE version = ?",
                (version,),
            )
            rolled_back.append({"version": version})

        return rolled_back

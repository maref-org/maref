"""
DatabaseManager 测试

覆盖审计问题 P6 扩展：连接管理、迁移机制、回滚支持。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from maref.governance.db import DatabaseManager


class TestConnectionManagement:
    def test_execute_create_table(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        assert db.table_exists("test")

    def test_execute_insert_and_select(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        db.execute("INSERT INTO test (name) VALUES (?)", ("alice",))
        rows = db.fetchall("SELECT * FROM test")
        assert len(rows) == 1
        assert rows[0]["name"] == "alice"

    def test_fetchone(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        db.execute("INSERT INTO test (name) VALUES (?)", ("alice",))
        row = db.fetchone("SELECT * FROM test WHERE name = ?", ("alice",))
        assert row is not None
        assert row["name"] == "alice"

    def test_fetchone_no_result(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        row = db.fetchone("SELECT * FROM test WHERE name = ?", ("nobody",))
        assert row is None

    def test_executescript(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        db.executescript("""
            CREATE TABLE t1 (id INTEGER);
            CREATE TABLE t2 (id INTEGER);
        """)
        assert db.table_exists("t1")
        assert db.table_exists("t2")

    def test_table_exists_false(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        assert db.table_exists("nonexistent") is False

    def test_close(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        db.execute("CREATE TABLE test (id INTEGER)")
        db.close()
        # Should be able to reconnect after close
        db.execute("INSERT INTO test (id) VALUES (1)")
        rows = db.fetchall("SELECT * FROM test")
        assert len(rows) == 1


class TestSchemaMigration:
    def test_initial_version(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        assert db.current_schema_version() == 0

    def test_migrate_single(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        migrations = {
            1: "CREATE TABLE users (id INTEGER PRIMARY KEY);",
        }
        applied = db.migrate(1, migrations)
        assert len(applied) == 1
        assert applied[0]["version"] == 1
        assert db.current_schema_version() == 1
        assert db.table_exists("users")

    def test_migrate_multiple(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        migrations = {
            1: "CREATE TABLE t1 (id INTEGER);",
            2: "CREATE TABLE t2 (id INTEGER);",
            3: "CREATE TABLE t3 (id INTEGER);",
        }
        applied = db.migrate(3, migrations)
        assert len(applied) == 3
        assert db.current_schema_version() == 3

    def test_migrate_idempotent(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        migrations = {
            1: "CREATE TABLE t1 (id INTEGER);",
        }
        db.migrate(1, migrations)
        applied = db.migrate(1, migrations)
        assert len(applied) == 0  # Already at version 1

    def test_migrate_with_descriptions(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        migrations = {1: "CREATE TABLE t1 (id INTEGER);"}
        descriptions = {1: "Initial schema"}
        applied = db.migrate(1, migrations, descriptions)
        assert applied[0]["description"] == "Initial schema"

    def test_migrate_missing_script(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        with pytest.raises(ValueError, match="Migration script for version 2 not found"):
            db.migrate(2, {1: ""})

    def test_rollback(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        migrations = {
            1: "CREATE TABLE t1 (id INTEGER);",
            2: "ALTER TABLE t1 ADD COLUMN name TEXT;",
        }
        rollbacks = {
            2: "ALTER TABLE t1 DROP COLUMN name;",
        }
        db.migrate(2, migrations)
        assert db.current_schema_version() == 2
        rolled = db.rollback(1, rollbacks)
        assert len(rolled) == 1
        assert db.current_schema_version() == 1

    def test_rollback_missing_script(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        db.migrate(1, {1: "CREATE TABLE t1 (id INTEGER);"})
        with pytest.raises(ValueError, match="Rollback script for version 1 not found"):
            db.rollback(0, {})

    def test_migrations_table_created(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db = DatabaseManager(f.name)
        db._ensure_migrations_table()
        assert db.table_exists("schema_migrations")

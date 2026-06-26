#!/usr/bin/env python3
"""MAREF Database Migration Script — standardized migration framework.

Usage:
    python scripts/migration.py --version      # Show current schema version
    python scripts/migration.py --upgrade      # Apply pending migrations
    python scripts/migration.py --downgrade     # Rollback last migration
    python scripts/migration.py --history       # Show migration history

Migrations are stored in scripts/migrations/ as numbered SQL files.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MAREF_DB_DIRS = [
    Path.home() / ".maref",
    Path.cwd() / "data",
]


def _get_db_paths() -> list[Path]:
    paths = []
    for d in MAREF_DB_DIRS:
        if d.exists():
            for f in d.glob("*.db"):
                paths.append(f)
    return paths


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_migrations ("
        "  version INTEGER PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  applied_at TEXT NOT NULL,"
        "  checksum TEXT"
        ")"
    )
    conn.commit()


def _list_migrations() -> list[dict[str, Any]]:
    migrations = []
    if not MIGRATIONS_DIR.exists():
        return migrations
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        parts = f.stem.split("_", 1)
        migrations.append({
            "version": int(parts[0]),
            "name": parts[1] if len(parts) > 1 else f.stem,
            "path": f,
        })
    return migrations


def show_version() -> None:
    db_paths = _get_db_paths()
    if not db_paths:
        print("No MAREF databases found.")
        return

    for db_path in db_paths:
        print(f"\nDatabase: {db_path}")
        try:
            conn = sqlite3.connect(str(db_path))
            _ensure_migrations_table(conn)
            row = conn.execute(
                "SELECT version, name, applied_at FROM _schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
            if row:
                print(f"  Schema version: {row[0]} ({row[1]}) — applied {row[2]}")
            else:
                print("  Schema version: 0 (no migrations applied)")
            conn.close()
        except sqlite3.Error as e:
            print(f"  Error: {e}")


def show_history() -> None:
    db_paths = _get_db_paths()
    for db_path in db_paths:
        print(f"\nDatabase: {db_path}")
        try:
            conn = sqlite3.connect(str(db_path))
            _ensure_migrations_table(conn)
            rows = conn.execute(
                "SELECT version, name, applied_at FROM _schema_migrations ORDER BY version"
            ).fetchall()
            if rows:
                for row in rows:
                    print(f"  [{row[0]}] {row[1]} ({row[2]})")
            else:
                print("  No migration history.")
            conn.close()
        except sqlite3.Error as e:
            print(f"  Error: {e}")


def upgrade() -> None:
    migrations = _list_migrations()
    if not migrations:
        print("No migrations found in scripts/migrations/.")
        return

    db_paths = _get_db_paths()
    if not db_paths:
        print("No MAREF databases found to upgrade.")
        return

    for db_path in db_paths:
        print(f"\nUpgrading: {db_path}")
        try:
            conn = sqlite3.connect(str(db_path))
            _ensure_migrations_table(conn)
            current = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM _schema_migrations"
            ).fetchone()[0]

            for m in migrations:
                if m["version"] <= current:
                    continue
                sql = m["path"].read_text()
                print(f"  Applying [{m['version']}] {m['name']}...")
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO _schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (m["version"], m["name"], datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                print("    Done.")

            conn.close()
        except sqlite3.Error as e:
            print(f"  Error: {e}")
            return

    print("\nUpgrade complete.")


def downgrade() -> None:
    db_paths = _get_db_paths()
    if not db_paths:
        print("No MAREF databases found.")
        return

    for db_path in db_paths:
        print(f"\nReverting last migration on: {db_path}")
        try:
            conn = sqlite3.connect(str(db_path))
            _ensure_migrations_table(conn)
            last = conn.execute(
                "SELECT version, name FROM _schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
            if not last:
                print("  No migrations to revert.")
                conn.close()
                continue

            revert_sql_path = MIGRATIONS_DIR / f"{last[0]}_{last[1]}.revert.sql"
            if not revert_sql_path.exists():
                print(f"  No revert script found for [{last[0]}] {last[1]}.")
                print(f"  Expected: {revert_sql_path}")
                conn.close()
                continue

            sql = revert_sql_path.read_text()
            print(f"  Reverting [{last[0]}] {last[1]}...")
            conn.executescript(sql)
            conn.execute("DELETE FROM _schema_migrations WHERE version = ?", (last[0],))
            conn.commit()
            print("    Done.")
            conn.close()
        except sqlite3.Error as e:
            print(f"  Error: {e}")
            return

    print("\nDowngrade complete.")


def _ensure_migrations_dir() -> None:
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    readme = MIGRATIONS_DIR / "README.md"
    if not readme.exists():
        readme.write_text(
            "# MAREF Database Migrations\n\n"
            "Format: `<version>_<description>.sql`\n"
            "Revert: `<version>_<description>.revert.sql`\n\n"
            "Example:\n"
            "  - `001_add_governance_table.sql`\n"
            "  - `001_add_governance_table.revert.sql`\n"
        )
        print(f"Created {readme}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MAREF Database Migration Tool")
    parser.add_argument("--version", action="store_true", help="Show current schema version")
    parser.add_argument("--history", action="store_true", help="Show migration history")
    parser.add_argument("--upgrade", action="store_true", help="Apply pending migrations")
    parser.add_argument("--downgrade", action="store_true", help="Rollback last migration")
    parser.add_argument("--init", action="store_true", help="Initialize migrations directory")
    args = parser.parse_args()

    if args.init:
        _ensure_migrations_dir()
        print(f"Migration directory ready: {MIGRATIONS_DIR}")
        return

    if args.version:
        show_version()
        return

    if args.history:
        show_history()
        return

    if args.upgrade:
        upgrade()
        return

    if args.downgrade:
        downgrade()
        return

    parser.print_help()


if __name__ == "__main__":
    main()

"""SQLite helpers and data-directory layout for the local corpus."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

_EXTERNAL_DIR = Path("/Volumes") / "1TB-M2" / "local" / "maref-corpus"
_DEFAULT_DIR = (
    _EXTERNAL_DIR if _EXTERNAL_DIR.parent.exists() else Path.home() / ".local/share/maref-corpus"
)
DEFAULT_DATA_DIR = Path(os.environ.get("MAREF_CORPUS_DIR") or _DEFAULT_DIR)
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def data_dir() -> Path:
    """Return the corpus data directory (never inside the git repo)."""
    return Path(os.environ.get("MAREF_CORPUS_DIR", str(DEFAULT_DATA_DIR)))


def db_path() -> Path:
    return data_dir() / "corpus.db"


def ensure_dirs() -> Path:
    root = data_dir()
    for name in ("raw", "snap", "exports", "logs", "backups"):
        (root / name).mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def connect_readonly(path: Path | str) -> sqlite3.Connection:
    """Open an external DB read-only; never blocks the writer under WAL."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def start_run(conn: sqlite3.Connection, source: str) -> int:
    cur = conn.execute("INSERT INTO run(source, started_at) VALUES(?, ?)", (source, time.time()))
    conn.commit()
    return int(cur.lastrowid or 0)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    rows_in: int,
    rows_new: int,
    status: str = "ok",
    error: str = "",
) -> None:
    conn.execute(
        "UPDATE run SET finished_at=?, rows_in=?, rows_new=?, status=?, error=? WHERE id=?",
        (time.time(), rows_in, rows_new, status, error, run_id),
    )
    conn.commit()


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ("event", "episode", "signature", "label"):
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        counts[table] = int(row["n"]) if row else 0
    return counts

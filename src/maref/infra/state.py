#!/usr/bin/env python3
"""
OpenClawState — unified state persistence for all daemons and scripts.

Replaces ad-hoc JSON file state management with a consistent SQLite-backed store.

Features:
  - retry_count / last_error / status tracking per operation
  - Auto-cleanup of old records (configurable retention)
  - Thread-safe (SQLite WAL mode)
  - Dict-like API for simple key-value state
  - Cycle/run history for status reporting

Usage:
    from maref.infra.state import OpenClawState

    state = OpenClawState("leak-scanner")
    state.set("last_scan", time.time())
    state.record_cycle(status="ok", files_scanned=142)
    state.record_error("git ls-files failed")
    print(state.get_summary())
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from datetime import datetime

try:  # py<3.11 无 datetime.UTC（meta-audit-gate 跑 python3.10 / 系统 python3=3.9 兼容）
    from datetime import UTC
except ImportError:  # pragma: no cover
    from datetime import timezone

    UTC = timezone.utc

from pathlib import Path
from typing import Any


class OpenClawState:
    """
    Persistent state store for MAREF daemons/scripts.

    Uses a single SQLite database at .openclaw/state/store.db with per-agent tables.
    """

    _db_lock = threading.Lock()
    _instances: dict[tuple[str, str], OpenClawState] = {}
    _initialized: bool = False

    def __new__(cls, agent_name: str, state_dir: str | Path | None = None) -> OpenClawState:
        # 单例 key 含 state_dir，避免同 agent 名不同目录静默串库
        key = (agent_name, str(Path(state_dir).resolve()) if state_dir else "default")
        if key not in cls._instances:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[key] = instance
        return cls._instances[key]

    def __init__(self, agent_name: str, state_dir: str | Path | None = None) -> None:
        if self._initialized:
            return
        self._initialized = True
        self.agent_name = agent_name
        if state_dir is None:
            # P1-1 双 state 收敛：默认跟随 get_meta_base()（env/项目根），
            # 消除「包路径推导固定落 repo/.openclaw」导致的 split-brain。
            try:
                from maref._paths import get_meta_base

                state_dir = get_meta_base() / "state"
            except Exception:
                state_dir = (
                    Path(__file__).resolve().parent.parent.parent.parent / ".openclaw" / "state"
                )
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "store.db"
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path),
                timeout=10,
                check_same_thread=False,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @staticmethod
    def _safe_name(name: str) -> str:
        # 白名单化，剥离引号/分号等字符，杜绝表名拼接注入面
        return re.sub(r"[^A-Za-z0-9_]", "_", name)

    def _tn(self, table: str) -> str:
        return f'"{self._safe_name(self.agent_name)}_{table}"'

    def _init_db(self) -> None:
        with self._db_lock:
            conn = self._get_conn()
            conn.executescript(f"""
                CREATE TABLE IF NOT EXISTS {self._tn("kv")} (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {self._tn("cycles")} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unknown', duration_ms REAL DEFAULT 0,
                    details TEXT DEFAULT '{{}}'
                );
                CREATE TABLE IF NOT EXISTS {self._tn("errors")} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL,
                    error TEXT NOT NULL, context TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS "idx_{self._safe_name(self.agent_name)}_cycles_time"
                    ON {self._tn("cycles")}(timestamp DESC);
                CREATE INDEX IF NOT EXISTS "idx_{self._safe_name(self.agent_name)}_errors_time"
                    ON {self._tn("errors")}(timestamp DESC);
                -- 全局事件总线：跨 agent 的统一事故/成功事件（STATE BUS 事件出口）
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{{}}',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_topic_created
                    ON events(topic, created_at DESC);
                -- 全局调度状态：统一 Loop 契约 schema（last_run/next_run_at/status/last_error）
                CREATE TABLE IF NOT EXISTS loop_schedule (
                    loop_id TEXT PRIMARY KEY,
                    last_run REAL NOT NULL DEFAULT 0,
                    next_run_at REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'unknown',
                    last_error TEXT NOT NULL DEFAULT '',
                    interval_seconds REAL NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_loop_schedule_next_run
                    ON loop_schedule(next_run_at);
            """)
            conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                f"SELECT value FROM {self._tn('kv')} WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return default
        val = row["value"]
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    def set(self, key: str, value: Any) -> None:
        if isinstance(value, (dict, list, bool, int, float)):
            val_str = json.dumps(value, ensure_ascii=False)
        else:
            val_str = str(value)
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                f"INSERT OR REPLACE INTO {self._tn('kv')} (key, value, updated_at) "
                "VALUES (?, ?, ?)",
                (key, val_str, time.time()),
            )
            conn.commit()

    def delete(self, key: str) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute(f"DELETE FROM {self._tn('kv')} WHERE key = ?", (key,))
            conn.commit()

    def get_all_kv(self) -> dict[str, Any]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(f"SELECT key, value FROM {self._tn('kv')}").fetchall()
        result = {}
        for row in rows:
            val = row["value"]
            try:
                result[row["key"]] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                result[row["key"]] = val
        return result

    def record_cycle(self, status: str = "ok", **details: Any) -> int:
        details_json = json.dumps(details, ensure_ascii=False, default=str)
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                f"INSERT INTO {self._tn('cycles')} (timestamp, status, duration_ms, details) "
                "VALUES (?, ?, ?, ?)",
                (time.time(), status, details.get("duration_ms", 0), details_json),
            )
            conn.commit()
            return cur.lastrowid or 0

    # ── 全局事件总线（STATE BUS）────────────────────────────────────

    def record_event(self, topic: str, payload: dict[str, Any] | None = None) -> int:
        """写一条全局事件（失败/成功/调度）。返回事件 id。"""
        payload_json = json.dumps(payload or {}, ensure_ascii=False, default=str)
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO events (topic, payload, created_at) VALUES (?, ?, ?)",
                (topic, payload_json, time.time()),
            )
            conn.commit()
            return cur.lastrowid or 0

    def get_recent_events(
        self,
        topic: str | None = None,
        limit: int = 50,
        after_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """取最近事件；after_id 为游标（仅返回 id > after_id 的事件），增量消费积压不丢失。"""
        with self._lock:
            conn = self._get_conn()
            if after_id is not None:
                # 游标模式按 id 升序返回最早一批，确保积压按序消费不跳过中间事件
                if topic:
                    rows = conn.execute(
                        "SELECT id, topic, payload, created_at FROM events "
                        "WHERE topic = ? AND id > ? ORDER BY id ASC LIMIT ?",
                        (topic, after_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, topic, payload, created_at FROM events "
                        "WHERE id > ? ORDER BY id ASC LIMIT ?",
                        (after_id, limit),
                    ).fetchall()
            elif topic:
                rows = conn.execute(
                    "SELECT id, topic, payload, created_at FROM events "
                    "WHERE topic = ? ORDER BY id DESC LIMIT ?",
                    (topic, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, topic, payload, created_at FROM events ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(row["payload"])
            except (json.JSONDecodeError, TypeError):
                item["payload"] = row["payload"]
            item["created_at_iso"] = datetime.fromtimestamp(row["created_at"], tz=UTC).isoformat()
            results.append(item)
        return results

    # ── 全局调度状态（统一 Loop 契约 schema）────────────────────────

    def set_schedule(
        self,
        loop_id: str,
        *,
        last_run: float = 0.0,
        next_run_at: float = 0.0,
        status: str = "unknown",
        last_error: str = "",
        interval_seconds: float = 0.0,
    ) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO loop_schedule "
                "(loop_id, last_run, next_run_at, status, last_error, interval_seconds, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(loop_id) DO UPDATE SET "
                "last_run=excluded.last_run, next_run_at=excluded.next_run_at, "
                "status=excluded.status, last_error=excluded.last_error, "
                "interval_seconds=excluded.interval_seconds, updated_at=excluded.updated_at",
                (loop_id, last_run, next_run_at, status, last_error, interval_seconds, time.time()),
            )
            conn.commit()

    def get_schedule(self, loop_id: str) -> dict[str, Any] | None:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT loop_id, last_run, next_run_at, status, last_error, "
                "interval_seconds, updated_at FROM loop_schedule WHERE loop_id = ?",
                (loop_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_due_loops(self, now: float | None = None) -> list[dict[str, Any]]:
        now = time.time() if now is None else now
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT loop_id, last_run, next_run_at, status, last_error, "
                "interval_seconds, updated_at FROM loop_schedule "
                "WHERE next_run_at <= ? ORDER BY next_run_at ASC",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_error(self, error: str, context: str = "") -> int:
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                f"INSERT INTO {self._tn('errors')} (timestamp, error, context) VALUES (?, ?, ?)",
                (time.time(), error[:1000], context[:500]),
            )
            conn.commit()
            return cur.lastrowid or 0

    def get_recent_cycles(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                f"SELECT id, timestamp, status, duration_ms, details "
                f"FROM {self._tn('cycles')} ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(row["details"])
            except (json.JSONDecodeError, TypeError):
                item["details"] = row["details"]
            item["timestamp_iso"] = datetime.fromtimestamp(row["timestamp"], tz=UTC).isoformat()
            results.append(item)
        return results

    def get_recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                f"SELECT id, timestamp, error, context "
                f"FROM {self._tn('errors')} ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["timestamp_iso"] = datetime.fromtimestamp(row["timestamp"], tz=UTC).isoformat()
            results.append(item)
        return results

    def get_retry_count(self, operation: str) -> int:
        return self.get(f"retry_{operation}", 0)

    def increment_retry(self, operation: str) -> int:
        current = self.get_retry_count(operation)
        new_count = current + 1
        self.set(f"retry_{operation}", new_count)
        self.set(f"retry_{operation}_last", time.time())
        return new_count

    def reset_retry(self, operation: str) -> None:
        self.set(f"retry_{operation}", 0)
        self.set(f"retry_{operation}_last", None)

    def get_last_error(self, operation: str) -> str | None:
        return self.get(f"last_error_{operation}", None)

    def set_last_error(self, operation: str, error: str) -> None:
        self.set(f"last_error_{operation}", error)

    def get_status(self) -> str:
        return self.get("status", "unknown")

    def set_status(self, status: str) -> None:
        self.set("status", status)

    def get_summary(self) -> dict[str, Any]:
        recent_cycles = self.get_recent_cycles(5)
        recent_errors = self.get_recent_errors(5)
        kv = self.get_all_kv()
        last_cycle = recent_cycles[0] if recent_cycles else None
        consecutive = 0
        for c in recent_cycles:
            if c["status"] == "error":
                consecutive += 1
            else:
                break
        return {
            "agent": self.agent_name,
            "status": self.get_status(),
            "last_cycle": last_cycle,
            "recent_cycles": len(recent_cycles),
            "recent_errors": len(recent_errors),
            "consecutive_errors": consecutive,
            "kv_count": len(kv),
        }

    def cleanup_old_cycles(self, max_cycles: int = 1000) -> int:
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                f"SELECT id FROM {self._tn('cycles')} ORDER BY id DESC LIMIT 1 OFFSET ?",
                (max_cycles,),
            ).fetchone()
            if row is None:
                return 0
            threshold = row["id"]
            cur = conn.execute(f"DELETE FROM {self._tn('cycles')} WHERE id <= ?", (threshold,))
            conn.commit()
            return cur.rowcount

    def cleanup_old_errors(self, max_age_days: int = 30) -> int:
        cutoff = time.time() - max_age_days * 86400
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(f"DELETE FROM {self._tn('errors')} WHERE timestamp < ?", (cutoff,))
            conn.commit()
            return cur.rowcount

    def __getitem__(self, key: str) -> Any:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __del__(self) -> None:
        self.close()

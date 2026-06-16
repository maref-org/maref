from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from maref.executor.types import Task, TaskPriority, TaskStatus


class TaskQueueError(RuntimeError):
    pass


_ALLOWED_UPDATE_FIELDS = {
    "name",
    "description",
    "priority",
    "status",
    "payload",
    "metadata",
    "tags",
    "session_id",
    "error_message",
    "retry_count",
    "max_retries",
    "timeout_seconds",
    "started_at",
    "completed_at",
}


class TaskQueue:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = self._connect()
        self._create_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _create_tables(self) -> None:
        with self._lock:
            cur = self._conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    priority INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    payload TEXT NOT NULL DEFAULT '{}',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    timeout_seconds REAL,
                    max_retries INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    session_id TEXT,
                    tags TEXT NOT NULL DEFAULT '[]'
                )
            """)
            cur.close()
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS dead_letter_queue (
                    id TEXT PRIMARY KEY,
                    original_task_id TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    priority INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'failed',
                    payload TEXT NOT NULL DEFAULT '{}',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    timeout_seconds REAL,
                    max_retries INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    session_id TEXT,
                    tags TEXT NOT NULL DEFAULT '[]',
                    dlq_reason TEXT NOT NULL DEFAULT '',
                    dlq_moved_at TEXT NOT NULL
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)
            """)
            self._conn.commit()

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            priority=TaskPriority(row["priority"]),
            status=TaskStatus(row["status"]),
            payload=json.loads(row["payload"]),
            metadata=json.loads(row["metadata"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            timeout_seconds=row["timeout_seconds"],
            max_retries=row["max_retries"],
            retry_count=row["retry_count"],
            error_message=row["error_message"],
            session_id=row["session_id"],
            tags=json.loads(row["tags"]),
        )

    def _task_to_row(self, task: Task) -> dict[str, Any]:
        return {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "priority": task.priority.value,
            "status": task.status.value,
            "payload": json.dumps(task.payload),
            "metadata": json.dumps(task.metadata),
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "timeout_seconds": task.timeout_seconds,
            "max_retries": task.max_retries,
            "retry_count": task.retry_count,
            "error_message": task.error_message,
            "session_id": task.session_id,
            "tags": json.dumps(task.tags),
        }

    def enqueue(self, task: Task) -> str:
        task.status = TaskStatus.QUEUED
        task.updated_at = _now()
        row = self._task_to_row(task)
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO tasks
                    (id, name, description, priority, status, payload, metadata,
                     created_at, updated_at, started_at, completed_at,
                     timeout_seconds, max_retries, retry_count, error_message,
                     session_id, tags)
                    VALUES (:id, :name, :description, :priority, :status, :payload, :metadata,
                            :created_at, :updated_at, :started_at, :completed_at,
                            :timeout_seconds, :max_retries, :retry_count, :error_message,
                            :session_id, :tags)""",
                    row,
                )
                self._conn.commit()
            except sqlite3.IntegrityError as e:
                raise TaskQueueError(f"Task {task.id} already exists") from e
        return task.id

    def dequeue(self, limit: int = 1) -> list[Task]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM tasks
                WHERE status = 'queued'
                ORDER BY priority DESC, created_at ASC
                LIMIT ?""",
                (limit,),
            ).fetchall()
            if not rows:
                return []
            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in ids)
            now = _now()
            self._conn.execute(
                f"""UPDATE tasks SET status = 'running', updated_at = ?, started_at = ?
                WHERE id IN ({placeholders})""",
                (now, now, *ids),
            )
            self._conn.commit()
            tasks = [self._row_to_task(r) for r in rows]
            for t in tasks:
                t.status = TaskStatus.RUNNING
                t.started_at = now
                t.updated_at = now
            return tasks

    def peek(self, limit: int = 1) -> list[Task]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM tasks
                WHERE status = 'queued'
                ORDER BY priority DESC, created_at ASC
                LIMIT ?""",
                (limit,),
            ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def update_status(self, task_id: str, status: TaskStatus, **updates: Any) -> bool:
        now = _now()
        fields = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status.value, now]
        if status == TaskStatus.RUNNING and "started_at" not in updates:
            fields.append("started_at = ?")
            values.append(now)
        if status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.CANCELLED,
        ):
            if "completed_at" not in updates:
                fields.append("completed_at = ?")
                values.append(now)
        for key, val in updates.items():
            if key not in _ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"Invalid update field: {key}")
            if key in ("payload", "metadata", "tags"):
                val = json.dumps(val)
            fields.append(f"{key} = ?")  # nosec: field from _ALLOWED_UPDATE_FIELDS whitelist
            values.append(val)
        values.append(task_id)
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tasks SET " + ", ".join(fields) + " WHERE id = ?",  # nosec: fields built from whitelist above
                values,
            )
            self._conn.commit()
            return cur.rowcount > 0

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_task(row)

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        limit: int = 100,
        offset: int = 0,
        session_id: str | None = None,
        tag: str | None = None,
    ) -> list[Task]:
        with self._lock:
            conditions: list[str] = []
            params: list[Any] = []
            if status is not None:
                conditions.append("status = ?")
                params.append(status.value)
            if priority is not None:
                conditions.append("priority = ?")
                params.append(priority.value)
            if session_id is not None:
                conditions.append("session_id = ?")
                params.append(session_id)
            if tag is not None:
                conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')
            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            rows = self._conn.execute(
                f"""SELECT * FROM tasks {where_clause}
                ORDER BY priority DESC, created_at ASC
                LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def count_tasks(
        self,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        session_id: str | None = None,
        tag: str | None = None,
    ) -> int:
        with self._lock:
            conditions: list[str] = []
            params: list[Any] = []
            if status is not None:
                conditions.append("status = ?")
                params.append(status.value)
            if priority is not None:
                conditions.append("priority = ?")
                params.append(priority.value)
            if session_id is not None:
                conditions.append("session_id = ?")
                params.append(session_id)
            if tag is not None:
                conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')
            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            row = self._conn.execute(
                f"SELECT COUNT(*) as c FROM tasks {where_clause}",
                params,
            ).fetchone()
            return row["c"]

    def delete(self, task_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def move_to_dlq(self, task_id: str, reason: str = "") -> bool:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return False
            task_dict = dict(row)
            now = _now()
            self._conn.execute(
                """INSERT OR REPLACE INTO dead_letter_queue
                (id, original_task_id, name, description, priority, status,
                 payload, metadata, created_at, updated_at, started_at, completed_at,
                 timeout_seconds, max_retries, retry_count, error_message,
                 session_id, tags, dlq_reason, dlq_moved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_dict["id"],
                    task_dict["id"],
                    task_dict["name"],
                    task_dict["description"],
                    task_dict["priority"],
                    "failed",
                    task_dict["payload"],
                    task_dict["metadata"],
                    task_dict["created_at"],
                    now,
                    task_dict["started_at"],
                    now,
                    task_dict["timeout_seconds"],
                    task_dict["max_retries"],
                    task_dict["retry_count"],
                    task_dict["error_message"],
                    task_dict["session_id"],
                    task_dict["tags"],
                    reason,
                    now,
                ),
            )
            self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self._conn.commit()
            return True

    def list_dlq(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM dead_letter_queue
                ORDER BY dlq_moved_at DESC
                LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
            result: list[dict[str, Any]] = []
            for r in rows:
                item = dict(r)
                item["payload"] = json.loads(item["payload"])
                item["metadata"] = json.loads(item["metadata"])
                item["tags"] = json.loads(item["tags"])
                result.append(item)
            return result

    def retry_dlq(self, task_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM dead_letter_queue WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return False
            task = self._row_to_task(row)
            task.status = TaskStatus.QUEUED
            task.retry_count = 0
            task.error_message = None
            task.started_at = None
            task.completed_at = None
            task.updated_at = _now()
            self._conn.execute("DELETE FROM dead_letter_queue WHERE id = ?", (task_id,))
            new_row = self._task_to_row(task)
            self._conn.execute(
                """INSERT INTO tasks
                (id, name, description, priority, status, payload, metadata,
                 created_at, updated_at, started_at, completed_at,
                 timeout_seconds, max_retries, retry_count, error_message,
                 session_id, tags)
                VALUES (:id, :name, :description, :priority, :status, :payload, :metadata,
                        :created_at, :updated_at, :started_at, :completed_at,
                        :timeout_seconds, :max_retries, :retry_count, :error_message,
                        :session_id, :tags)""",
                new_row,
            )
            self._conn.commit()
            return True

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) as c FROM tasks").fetchone()["c"]
            by_status: dict[str, int] = {}
            for row in self._conn.execute(
                "SELECT status, COUNT(*) as c FROM tasks GROUP BY status"
            ).fetchall():
                by_status[row["status"]] = row["c"]
            dlq_count = self._conn.execute(
                "SELECT COUNT(*) as c FROM dead_letter_queue"
            ).fetchone()["c"]
            return {
                "total": total,
                "by_status": by_status,
                "dead_letter_queue": dlq_count,
                "db_path": self._db_path,
            }

    def clear(self, status: TaskStatus | None = None) -> int:
        with self._lock:
            if status is not None:
                cur = self._conn.execute("DELETE FROM tasks WHERE status = ?", (status.value,))
            else:
                cur = self._conn.execute(
                    "DELETE FROM tasks WHERE status IN ('completed', 'failed', 'cancelled', 'timeout')"
                )
            deleted = cur.rowcount
            self._conn.commit()
            return deleted

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

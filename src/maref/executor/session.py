from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from maref.executor.queue import TaskQueue


class Session:
    def __init__(
        self,
        id: str,
        status: str = "active",
        created_at: str | None = None,
        last_heartbeat: str | None = None,
        closed_at: str | None = None,
        ttl: float = 3600.0,
        metadata: dict[str, Any] | None = None,
        task_ids: list[str] | None = None,
    ) -> None:
        now = _now()
        self.id = id
        self.status = status
        self.created_at = created_at or now
        self.last_heartbeat = last_heartbeat or now
        self.closed_at = closed_at
        self.ttl = ttl
        self.metadata = metadata or {}
        self.task_ids = task_ids or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "last_heartbeat": self.last_heartbeat,
            "closed_at": self.closed_at,
            "ttl": self.ttl,
            "metadata": self.metadata,
            "task_ids": self.task_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        return cls(
            id=data["id"],
            status=data.get("status", "active"),
            created_at=data.get("created_at"),
            last_heartbeat=data.get("last_heartbeat"),
            closed_at=data.get("closed_at"),
            ttl=data.get("ttl", 3600.0),
            metadata=data.get("metadata", {}),
            task_ids=data.get("task_ids", []),
        )


class SessionManager:
    def __init__(self, task_queue: TaskQueue, heartbeat_interval: float = 30.0) -> None:
        self._queue = task_queue
        self._heartbeat_interval = heartbeat_interval
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        session_id: str | None = None,
        ttl: float = 3600.0,
        metadata: dict[str, Any] | None = None,
        task_ids: list[str] | None = None,
    ) -> Session:
        sid = session_id or str(uuid.uuid4())
        session = Session(id=sid, ttl=ttl, metadata=metadata, task_ids=task_ids)
        with self._lock:
            self._sessions[sid] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            return copy.deepcopy(session)

    def update_heartbeat(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.last_heartbeat = _now()
            return True

    def check_timeouts(self) -> list[str]:
        now = _now()
        now_dt = datetime.fromisoformat(now)
        expired: list[str] = []
        with self._lock:
            for sid, session in self._sessions.items():
                if session.status in ("expired", "closed"):
                    continue
                hb_dt = datetime.fromisoformat(session.last_heartbeat)
                elapsed = (now_dt - hb_dt).total_seconds()
                if elapsed > session.ttl:
                    session.status = "expired"
                    expired.append(sid)
        return expired

    def close_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.status = "closed"
            session.closed_at = _now()
            return True

    def list_sessions(self, status: str | None = None) -> list[Session]:
        with self._lock:
            if status is None:
                return copy.deepcopy(list(self._sessions.values()))
            return [
                copy.deepcopy(s)
                for s in self._sessions.values()
                if s.status == status
            ]

    def recover_session(self, session_id: str) -> Session | None:
        with self._lock:
            old = self._sessions.get(session_id)
            if old is None:
                return None
            task_ids = list(old.task_ids)
            session = Session(
                id=session_id,
                ttl=old.ttl,
                metadata=dict(old.metadata),
                task_ids=task_ids,
            )
            self._sessions[session_id] = session
            return copy.deepcopy(session)

    def stats(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for s in self._sessions.values():
                counts[s.status] = counts.get(s.status, 0) + 1
            return counts


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

"""Level 2 — Persistent audit store (v0.49 P4).

SQLite persistence for the distributed audit bus, reusing the standard
:class:`maref.governance.db.DatabaseManager` interface (v0.47 F4 pattern).
Audit events survive process restarts and can be replayed / integrity-verified.

Usage::

    from maref.level2.audit_store import PersistentAuditStore
    from maref.level2.audit_bus_mvp import DistributedAuditBus

    store = PersistentAuditStore("/tmp/audit.db")
    bus = DistributedAuditBus(secret_key=b"secret", store=store)
    bus.publish_cross_framework("agent_action", "agent-1", "tool.call")
    # ... restart ...
    store2 = PersistentAuditStore("/tmp/audit.db")
    events = store2.replay()          # events survived the restart
    report = store2.verify_integrity(b"secret")   # all signatures valid
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maref.governance.db import DatabaseManager
from maref.level2.audit_bus_mvp import FrameworkAuditEvent


class PersistentAuditStore:
    """SQLite-backed append-only store for :class:`FrameworkAuditEvent`."""

    def __init__(self, db_path: str | Path) -> None:
        self._db = DatabaseManager(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type       TEXT NOT NULL,
                actor            TEXT NOT NULL,
                action           TEXT NOT NULL,
                framework        TEXT NOT NULL,
                metadata         TEXT NOT NULL,
                timestamp        REAL NOT NULL,
                digest           TEXT NOT NULL,
                signature        TEXT NOT NULL,
                signature_scheme TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events (event_type);
            CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events (actor);
            CREATE INDEX IF NOT EXISTS idx_audit_framework ON audit_events (framework);
            """
        )

    def append(self, event: FrameworkAuditEvent) -> int:
        """Persist one event; returns the new row id."""
        last_id: int | None = self._db.execute(
            "INSERT INTO audit_events "
            "(event_type, actor, action, framework, metadata, timestamp, "
            "digest, signature, signature_scheme) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_type,
                event.actor,
                event.action,
                event.framework,
                json.dumps(normalise_metadata_for_json(event.metadata)),
                event.timestamp,
                event.canonical_digest(),
                event.signature,
                event.signature_scheme,
            ),
        ).lastrowid
        if last_id is None:
            return 0
        return int(last_id)

    def count(self) -> int:
        row = self._db.fetchone("SELECT COUNT(*) AS n FROM audit_events")
        return int(row["n"]) if row is not None else 0

    def query(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
        actor: str | None = None,
        framework: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return matching events as dicts (newest first)."""
        sql = "SELECT * FROM audit_events WHERE 1=1"
        params: list[Any] = []
        if event_type is not None:
            sql += " AND event_type = ?"
            params.append(event_type)
        if actor is not None:
            sql += " AND actor = ?"
            params.append(actor)
        if framework is not None:
            sql += " AND framework = ?"
            params.append(framework)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [
            {
                "id": r["id"],
                "event_type": r["event_type"],
                "actor": r["actor"],
                "action": r["action"],
                "framework": r["framework"],
                "metadata": json.loads(r["metadata"]),
                "timestamp": r["timestamp"],
                "digest": r["digest"],
                "signature": r["signature"],
                "signature_scheme": r["signature_scheme"],
            }
            for r in self._db.fetchall(sql, tuple(params))
        ]

    def replay(self) -> list[FrameworkAuditEvent]:
        """Reconstruct all persisted events in insertion order."""
        rows = self._db.fetchall("SELECT * FROM audit_events ORDER BY id ASC")
        return [
            FrameworkAuditEvent(
                event_type=r["event_type"],
                actor=r["actor"],
                action=r["action"],
                framework=r["framework"],
                metadata=json.loads(r["metadata"]),
                timestamp=r["timestamp"],
                signature=r["signature"],
                signature_scheme=r["signature_scheme"],
            )
            for r in rows
        ]

    def verify_integrity(
        self,
        secret_key: bytes,
        framework: str | None = None,
    ) -> dict[str, Any]:
        """Verify every stored signature against the bus secret key.

        Returns ``{"valid": int, "invalid": int, "first_invalid_id": int|None}``.
        Tampered events (altered fields, or a signature replayed across
        frameworks) fail verification.
        """
        from maref.level2.audit_bus_mvp import DistributedAuditBus

        bus = DistributedAuditBus(secret_key=secret_key)
        events = self.replay()
        invalid: list[int] = []
        for event in events:
            if not bus.verify_event_signature(event, framework=framework):
                # Locate the offending row id by matching content.
                row = self._db.fetchone(
                    "SELECT id FROM audit_events WHERE actor=? AND action=? "
                    "AND framework=? AND timestamp=? LIMIT 1",
                    (event.actor, event.action, event.framework, event.timestamp),
                )
                if row is not None:
                    invalid.append(int(row["id"]))
        return {
            "valid": len(events) - len(invalid),
            "invalid": len(invalid),
            "first_invalid_id": invalid[0] if invalid else None,
        }

    def close(self) -> None:
        self._db.close()


def normalise_metadata_for_json(metadata: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe copy of an already-normalised metadata dict."""
    from maref.level2.audit_bus_mvp import normalise_metadata

    normalised = normalise_metadata(metadata)
    assert isinstance(normalised, dict)
    return normalised


__all__ = [
    "PersistentAuditStore",
    "normalise_metadata_for_json",
]

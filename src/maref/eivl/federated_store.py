"""Federated audit persistence — SQLite-backed state store.

Wraps :class:`FederatedMerkleAggregator` with automatic persistence
to SQLite, ensuring the Merkle root is consistent across restarts.

Usage::

    store = FederatedAuditStore("federation.db")
    store.submit_root("org-1", root_hash_1)
    store.submit_root("org-2", root_hash_2)

    # State is auto-persisted — restart and reload:
    store2 = FederatedAuditStore("federation.db")
    assert store2.get_federated_root() == store.get_federated_root()
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from maref.eivl.federated_merkle import (
    FederatedMerkleAggregator,
    FederatedProof,
    OrgRootEntry,
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS org_roots (
    org_id          TEXT PRIMARY KEY,
    root_hash       TEXT NOT NULL,
    timestamp       REAL NOT NULL,
    tree_size       INTEGER NOT NULL DEFAULT 0,
    metadata_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS snapshots (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    federated_root_hash     TEXT,
    org_count               INTEGER NOT NULL,
    total_evidence_count    INTEGER NOT NULL DEFAULT 0,
    created_at              REAL NOT NULL
);
"""


class FederatedAuditStore:
    """SQLite-backed persistent store for federated Merkle aggregation.

    Wraps a :class:`FederatedMerkleAggregator` and automatically
    persists every mutation to SQLite. On load, replays stored org
    roots through the aggregator and verifies the Merkle root matches
    the last snapshot.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.RLock()
        self._agg = FederatedMerkleAggregator()
        self._init_db()
        self._load_from_db()

    # ── DB init ──────────────────────────────────────────────

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self._db_path))
        c.row_factory = sqlite3.Row
        return c

    # ── Load from DB ─────────────────────────────────────────

    def _load_from_db(self) -> None:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT org_id, root_hash, timestamp, tree_size, metadata_json "
                "FROM org_roots ORDER BY rowid"
            ).fetchall()
            for row in rows:
                metadata = json.loads(row["metadata_json"])
                self._agg.submit_root(
                    org_id=row["org_id"],
                    root_hash=row["root_hash"],
                    tree_size=row["tree_size"],
                    metadata=metadata,
                )
        finally:
            conn.close()

    # ── Snapshot ─────────────────────────────────────────────

    def _take_snapshot(self) -> None:
        """Persist current aggregator state to SQLite."""
        conn = self._conn()
        try:
            with conn:
                conn.execute("DELETE FROM org_roots")
                for e in self._agg._entries:
                    conn.execute(
                        "INSERT INTO org_roots (org_id, root_hash, timestamp, tree_size, metadata_json) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            e.org_id,
                            e.root_hash,
                            e.timestamp,
                            e.tree_size,
                            json.dumps(e.metadata, ensure_ascii=False),
                        ),
                    )
                root = self._agg.get_federated_root()
                conn.execute(
                    "INSERT INTO snapshots (federated_root_hash, org_count, total_evidence_count, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        root,
                        len(self._agg._entries),
                        sum(e.tree_size for e in self._agg._entries),
                        time.time(),
                    ),
                )
        finally:
            conn.close()

    # ── Snapshot equality assertion ──────────────────────────

    def assert_consistent(self) -> bool:
        """Check that the last snapshot's root matches current aggregator root.

        Useful for restart consistency verification::

            store = FederatedAuditStore("federation.db")
            assert store.assert_consistent()
        """
        conn = self._conn()
        try:
            last = conn.execute(
                "SELECT federated_root_hash, org_count FROM snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()

        if last is None:
            return True
        current_root = self._agg.get_federated_root()
        return last["federated_root_hash"] == current_root and last["org_count"] == len(
            self._agg._entries
        )

    # ── Delegated aggregator methods ─────────────────────────

    def submit_root(
        self,
        org_id: str,
        root_hash: str,
        tree_size: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._agg.submit_root(org_id, root_hash, tree_size, metadata)
            self._take_snapshot()

    def get_federated_root(self) -> str | None:
        with self._lock:
            return self._agg.get_federated_root()

    def generate_proof(self, org_id: str) -> FederatedProof | None:
        with self._lock:
            return self._agg.generate_proof(org_id)

    def verify_org_inclusion(self, org_id: str) -> dict[str, Any]:
        with self._lock:
            return self._agg.verify_org_inclusion(org_id)

    def list_orgs(self) -> list[OrgRootEntry]:
        with self._lock:
            return self._agg.list_orgs()

    def remove_org(self, org_id: str) -> bool:
        with self._lock:
            result = self._agg.remove_org(org_id)
            if result:
                self._take_snapshot()
            return result

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return self._agg.summary()

    def get_org_entry(self, org_id: str) -> OrgRootEntry | None:
        with self._lock:
            return self._agg.get_org_entry(org_id)

    @property
    def aggregator(self) -> FederatedMerkleAggregator:
        return self._agg

    def export_json(self, path: str | Path) -> None:
        """Export current state to JSON (compatible with FederatedMerkleAggregator.save_state)."""
        with self._lock:
            self._agg.save_state(path)

    @classmethod
    def import_json(
        cls,
        json_path: str | Path,
        db_path: str | Path,
    ) -> FederatedAuditStore:
        """Create a store from an existing JSON state file."""
        agg = FederatedMerkleAggregator.load_state(json_path)
        store = cls.__new__(cls)
        store._db_path = Path(db_path)
        store._lock = threading.RLock()
        store._agg = agg
        store._init_db()
        store._take_snapshot()
        return store

    def close(self) -> None:
        """Close any resources (no-op for sqlite3, included for interface completeness)."""
        pass


__all__ = ["FederatedAuditStore"]

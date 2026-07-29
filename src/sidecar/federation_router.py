"""Federated audit API — Sidecar REST endpoints for cross-org Merkle aggregation.

Persistence is handled by :class:`FederatedAuditStore` (SQLite).
A JSON fallback is provided for backward compatibility.

Configure via environment variables:
    MAREF_FEDERATED_DB:      Path to SQLite database (default: ~/.maref/federation.db)
    MAREF_FEDERATED_STATE:   Path to JSON state file (legacy fallback)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from maref.eivl.federated_store import FederatedAuditStore

router = APIRouter(prefix="/api/v1/federation")

_DEFAULT_STATE_DIR = Path.home() / ".maref"
_store: FederatedAuditStore | None = None


def _get_db_path() -> Path:
    env_db = os.environ.get("MAREF_FEDERATED_DB")
    if env_db:
        return Path(env_db)
    return _DEFAULT_STATE_DIR / "federation.db"


def _maybe_migrate_json(db_path: Path) -> None:
    if db_path.exists():
        return
    json_path_str = os.environ.get("MAREF_FEDERATED_STATE")
    json_path = Path(json_path_str) if json_path_str else _DEFAULT_STATE_DIR / "federated-state.json"
    if json_path.exists():
        FederatedAuditStore.import_json(json_path, db_path)
        json_path.rename(json_path.with_suffix(".json.migrated"))


def _get_store() -> FederatedAuditStore:
    global _store
    if _store is None:
        db_path = _get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _maybe_migrate_json(db_path)
        _store = FederatedAuditStore(db_path)
    return _store


@router.get("/status")
def federation_status() -> dict[str, Any]:
    store = _get_store()
    summary = store.summary()
    orgs = [
        {"org_id": e.org_id, "root_hash": e.root_hash, "tree_size": e.tree_size, "timestamp": e.timestamp}
        for e in store.list_orgs()
    ]
    return {
        "storage": "sqlite",
        "consistent": store.assert_consistent(),
        "federated_root": summary["federated_root"],
        "org_count": summary["org_count"],
        "last_aggregated": summary["last_aggregated"],
        "total_evidence_count": summary["total_evidence_count"],
        "organizations": orgs,
    }


@router.post("/submit")
def federation_submit(body: dict[str, Any]) -> dict[str, Any]:
    org_id = body.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id is required")
    root_hash = body.get("root_hash")
    if not root_hash:
        raise HTTPException(status_code=400, detail="root_hash is required")

    store = _get_store()
    store.submit_root(
        org_id=org_id,
        root_hash=root_hash,
        tree_size=body.get("tree_size", 0),
        metadata=body.get("metadata", {}),
    )

    summary = store.summary()
    return {
        "status": "submitted",
        "org_id": org_id,
        "federated_root": summary["federated_root"],
        "org_count": summary["org_count"],
    }


@router.get("/proof/{org_id}")
def federation_proof(org_id: str) -> dict[str, Any]:
    store = _get_store()
    proof = store.generate_proof(org_id)
    if proof is None:
        raise HTTPException(status_code=404, detail=f"Org not found: {org_id}")
    return proof.to_dict()


@router.delete("/proof/{org_id}")
def federation_delete_proof(org_id: str) -> dict[str, Any]:
    store = _get_store()
    if not store.remove_org(org_id):
        raise HTTPException(status_code=404, detail=f"Org not found: {org_id}")
    return {"status": "removed", "org_id": org_id}


@router.get("/root")
def federation_root() -> dict[str, Any]:
    store = _get_store()
    root = store.get_federated_root()
    return {
        "federated_root": root,
        "org_count": store.summary()["org_count"],
    }


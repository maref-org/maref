"""Federated audit API — Sidecar REST endpoints for cross-org Merkle aggregation."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from maref.eivl.federated_merkle import FederatedMerkleAggregator

router = APIRouter(prefix="/api/v1/federation")

_DEFAULT_STATE_PATH = os.environ.get(
    "MAREF_FEDERATED_STATE",
    str(Path.cwd() / ".maref" / "federated-state.json"),
)


def _load_aggregator() -> FederatedMerkleAggregator:
    path = Path(_DEFAULT_STATE_PATH)
    if path.exists():
        return FederatedMerkleAggregator.load_state(str(path))
    return FederatedMerkleAggregator()


def _save_aggregator(agg: FederatedMerkleAggregator) -> None:
    path = Path(_DEFAULT_STATE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    agg.save_state(str(path))


@router.get("/status")
def federation_status() -> dict[str, Any]:
    agg = _load_aggregator()
    summary = agg.summary()
    orgs = [
        {"org_id": e.org_id, "root_hash": e.root_hash, "tree_size": e.tree_size, "timestamp": e.timestamp}
        for e in agg.list_orgs()
    ]
    return {
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

    agg = _load_aggregator()
    agg.submit_root(
        org_id=org_id,
        root_hash=root_hash,
        tree_size=body.get("tree_size", 0),
        metadata=body.get("metadata", {}),
    )
    _save_aggregator(agg)

    summary = agg.summary()
    return {
        "status": "submitted",
        "org_id": org_id,
        "federated_root": summary["federated_root"],
        "org_count": summary["org_count"],
    }


@router.get("/proof/{org_id}")
def federation_proof(org_id: str) -> dict[str, Any]:
    agg = _load_aggregator()
    proof = agg.generate_proof(org_id)
    if proof is None:
        raise HTTPException(status_code=404, detail=f"Org not found: {org_id}")
    return proof.to_dict()

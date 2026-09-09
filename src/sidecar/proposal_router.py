"""提案接收端点 — 双向提案同步桥梁

Phase Alpha A8: 接收 OpenClaw 侧提案 + 提供提案查询
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/proposal")

_PROPOSAL_DIR = Path("data/proposals")
_PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)
_INDEX_FILE = _PROPOSAL_DIR / "proposals_index.jsonl"


@router.post("/ingest")
def proposal_ingest(payload: dict[str, Any]) -> dict[str, Any]:
    proposal_id = payload.get("proposal_id")
    if not proposal_id:
        raise HTTPException(status_code=400, detail="proposal_id is required")

    entry = {
        "proposal_id": proposal_id,
        "source": payload.get("source", "unknown"),
        "action": payload.get("action", "unknown"),
        "agent": payload.get("agent", ""),
        "risk_level": payload.get("risk_level", "unknown"),
        "domain_weight": payload.get("domain_weight", 1),
        "verdict": payload.get("verdict", "unknown"),
        "details": payload.get("details", ""),
        "created_at": payload.get("created_at", datetime.now(timezone.utc).isoformat()),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(_INDEX_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    detail_file = _PROPOSAL_DIR / f"{proposal_id}.json"
    with open(detail_file, "w") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)

    logger.info("proposal ingested: id=%s source=%s", proposal_id, entry["source"])
    return {"status": "ok", "proposal_id": proposal_id, "stored_in": str(detail_file)}


@router.get("/count")
def proposal_count() -> dict[str, Any]:
    if not _INDEX_FILE.exists():
        return {"total": 0, "by_source": {}, "by_risk_level": {}, "by_verdict": {}}

    total = 0
    by_source: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    by_verdict: dict[str, int] = {}
    with open(_INDEX_FILE) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                total += 1
                s = entry.get("source", "unknown")
                by_source[s] = by_source.get(s, 0) + 1
                r = entry.get("risk_level", "unknown")
                by_risk[r] = by_risk.get(r, 0) + 1
                v = entry.get("verdict", "unknown")
                by_verdict[v] = by_verdict.get(v, 0) + 1
            except json.JSONDecodeError:
                pass

    return {"total": total, "by_source": by_source, "by_risk_level": by_risk, "by_verdict": by_verdict}


@router.get("/{proposal_id}")
def proposal_get(proposal_id: str) -> dict[str, Any]:
    detail_file = _PROPOSAL_DIR / f"{proposal_id}.json"
    if not detail_file.exists():
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
    with open(detail_file) as f:
        return json.load(f)
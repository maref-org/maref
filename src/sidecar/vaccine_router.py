"""疫苗注入 + 批次管理 (Phase Gamma C1+C2+C3)

C1: POST /api/vaccine/inject — 接收疫苗 JSON，写入 SafetyGate 规则库
C2: 批次注入 + A/B 测量
C3: 误伤率监控 + 自动回滚
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vaccine")

_VACCINE_DIR = Path("data/vaccines")
_VACCINE_DIR.mkdir(parents=True, exist_ok=True)
_BATCH_LOG = _VACCINE_DIR / "injection_log.jsonl"
_SAFETYGATE_DIR = _VACCINE_DIR / "safetygate_rules"
_SAFETYGATE_DIR.mkdir(parents=True, exist_ok=True)
_FPR_LOG = _VACCINE_DIR / "false_positive_log.jsonl"

FPR_AUTO_ROLLBACK_THRESHOLD = 0.05
_ROLLBACK_HISTORY = _VACCINE_DIR / "rollback_history.jsonl"


@router.post("/inject")
def vaccine_inject(payload: dict[str, Any]) -> dict[str, Any]:
    batch_id = payload.get("batch_id")
    vaccines = payload.get("vaccines", [])
    merkle_root = payload.get("merkle_root", "")
    auto_rollback = payload.get("auto_rollback", {})

    if not batch_id or not vaccines:
        raise HTTPException(status_code=400, detail="batch_id and vaccines are required")

    batch = {
        "batch_id": batch_id,
        "vaccines": vaccines,
        "merkle_root": merkle_root,
        "auto_rollback": auto_rollback,
        "status": "injected",
        "injected_at": datetime.now(timezone.utc).isoformat(),
        "vaccine_count": len(vaccines),
    }

    batch_file = _VACCINE_DIR / f"batch_{batch_id}.json"
    with open(batch_file, "w") as f:
        json.dump(batch, f, indent=2, ensure_ascii=False)

    with open(_BATCH_LOG, "a") as f:
        f.write(json.dumps({"event": "injected", "batch_id": batch_id, "count": len(vaccines), "time": batch["injected_at"]}) + "\n")

    rules_injected = 0
    for vaccine in vaccines:
        rule = vaccine.get("safetygate_rule", {})
        if rule:
            rule_file = _SAFETYGATE_DIR / f"{vaccine.get('vaccine_id', 'unknown')}.json"
            with open(rule_file, "w") as f:
                json.dump(rule, f, ensure_ascii=False)
            rules_injected += 1

    logger.info("vaccine batch injected: %s (%d vaccines, %d rules)", batch_id, len(vaccines), rules_injected)
    return {"status": "ok", "batch_id": batch_id, "vaccines": len(vaccines), "rules_written": rules_injected, "stored_in": str(batch_file)}


@router.post("/report-fpr")
def report_false_positive(payload: dict[str, Any]) -> dict[str, Any]:
    vaccine_id = payload.get("vaccine_id")
    batch_id = payload.get("batch_id")
    if not vaccine_id:
        raise HTTPException(status_code=400, detail="vaccine_id is required")

    entry = {
        "vaccine_id": vaccine_id,
        "batch_id": batch_id,
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "details": payload.get("details", ""),
    }
    with open(_FPR_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    fpr = _compute_fpr()
    if fpr > FPR_AUTO_ROLLBACK_THRESHOLD:
        _rollback_latest_batch()
        return {"status": "rolled_back", "fpr": fpr, "threshold": FPR_AUTO_ROLLBACK_THRESHOLD}

    return {"status": "recorded", "fpr": fpr, "threshold": FPR_AUTO_ROLLBACK_THRESHOLD}


@router.get("/status")
def vaccine_status() -> dict[str, Any]:
    batches = sorted(_VACCINE_DIR.glob("batch_*.json"), reverse=True)
    active_rules = list(_SAFETYGATE_DIR.glob("*.json"))
    fpr = _compute_fpr()

    return {
        "total_batches": len(batches),
        "active_rules": len(active_rules),
        "current_fpr": fpr,
        "auto_rollback_threshold": FPR_AUTO_ROLLBACK_THRESHOLD,
        "latest_batch": str(batches[0]) if batches else None,
    }


@router.get("/rules")
def list_vaccine_rules() -> list[dict[str, Any]]:
    rules = []
    for f in sorted(_SAFETYGATE_DIR.glob("*.json")):
        try:
            with open(f) as fh:
                rules.append(json.load(fh))
        except json.JSONDecodeError:
            pass
    return rules


def _compute_fpr() -> float:
    if not _FPR_LOG.exists():
        return 0.0
    with open(_FPR_LOG) as _fpr_file:
        fp_count = sum(1 for _ in _fpr_file)
    if fp_count == 0:
        return 0.0
    total_decisions = 1
    try:
        with open(_BATCH_LOG) as f:
            for _line in f:
                total_decisions += 1
    except FileNotFoundError:
        pass
    return fp_count / max(total_decisions, 1)


def _rollback_latest_batch():
    batches = sorted(_VACCINE_DIR.glob("batch_*.json"), reverse=True)
    if not batches:
        return
    latest = batches[0]
    with open(latest) as f:
        batch = json.load(f)
    batch["status"] = "rolled_back"
    batch["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
    with open(latest, "w") as f:
        json.dump(batch, f, indent=2, ensure_ascii=False)

    with open(_ROLLBACK_HISTORY, "a") as f:
        f.write(json.dumps({"batch_id": batch["batch_id"], "time": batch["rolled_back_at"]}) + "\n")
    logger.warning("auto-rollback triggered for batch %s", batch["batch_id"])

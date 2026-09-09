"""配置推送端点 — MAREF 治理配置 → OpenClaw 侧热加载

Phase Beta B3+B6: 阈值配置推送到此端点，OpenClaw 侧从中拉取最新阈值
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/config")

_CONFIG_DIR = Path("data/configs")
_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
_THRESHOLDS_FILE = _CONFIG_DIR / "active_probe_thresholds.json"


@router.post("/probe-thresholds")
def set_probe_thresholds(payload: dict[str, Any]) -> dict[str, Any]:
    config_id = payload.get("config_id")
    if not config_id:
        raise HTTPException(status_code=400, detail="config_id is required")

    probes = payload.get("probes", {})
    if not probes:
        raise HTTPException(status_code=400, detail="probes is required")

    active_config = {
        "config_id": config_id,
        "probes": probes,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(_THRESHOLDS_FILE, "w") as f:
        json.dump(active_config, f, indent=2, ensure_ascii=False)

    logger.info("probe thresholds updated: %s", config_id)
    return {"status": "ok", "config_id": config_id, "stored_in": str(_THRESHOLDS_FILE)}


@router.get("/probe-thresholds")
def get_probe_thresholds() -> dict[str, Any]:
    if not _THRESHOLDS_FILE.exists():
        raise HTTPException(status_code=404, detail="No probe thresholds configured. POST /api/config/probe-thresholds first.")

    with open(_THRESHOLDS_FILE) as f:
        return json.load(f)
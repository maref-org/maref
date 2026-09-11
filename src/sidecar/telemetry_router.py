"""遥测接收端点 — OpenClaw → MAREF 遥测数据桥梁

Phase Alpha A7: 接收 OpenClaw 侧看门狗/飞轮/进化遥测数据
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telemetry")

_TELEMETRY_DIR = Path("data/telemetry")
_TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
_MAX_TELEMETRY_AGE_HOURS = 24


@router.post("/ingest")
def telemetry_ingest(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source", "unknown")
    telemetry_type = payload.get("telemetry_type", "unknown")
    timestamp = payload.get("timestamp", datetime.now(timezone.utc).isoformat())
    data = payload.get("data", {})

    if not source or not telemetry_type:
        raise HTTPException(status_code=400, detail="source and telemetry_type are required")

    entry = {
        "source": source,
        "telemetry_type": telemetry_type,
        "timestamp": timestamp,
        "data": data,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }

    daily_file = _TELEMETRY_DIR / f"telemetry_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
    with open(daily_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    logger.info("telemetry ingested: source=%s type=%s", source, telemetry_type)
    return {"status": "ok", "stored_in": str(daily_file)}


@router.get("/status")
def telemetry_status() -> dict[str, Any]:
    files = sorted(_TELEMETRY_DIR.glob("telemetry_*.jsonl"), reverse=True)
    if not files:
        return {"status": "no_data", "latest_file": None, "total_files": 0}

    latest = files[0]
    line_count = 0
    types_seen: dict[str, int] = {}
    sources_seen: dict[str, int] = {}
    with open(latest) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                line_count += 1
                t = entry.get("telemetry_type", "unknown")
                types_seen[t] = types_seen.get(t, 0) + 1
                s = entry.get("source", "unknown")
                sources_seen[s] = sources_seen.get(s, 0) + 1
            except json.JSONDecodeError:
                pass

    # 检查数据新鲜度
    fresh = False
    if line_count > 0:
        with open(latest) as f:
            last_line = None
            for line in f:
                last_line = line
            if last_line:
                try:
                    entry = json.loads(last_line.strip())
                    ingested = entry.get("ingested_at", "")
                    if ingested:
                        t = datetime.fromisoformat(ingested).replace(tzinfo=timezone.utc)
                        age = (datetime.now(timezone.utc) - t).total_seconds() / 3600
                        fresh = age < _MAX_TELEMETRY_AGE_HOURS
                except (json.JSONDecodeError, ValueError):
                    pass

    return {
        "status": "fresh" if fresh else "stale",
        "latest_file": str(latest),
        "total_files": len(files),
        "latest_line_count": line_count,
        "types_distribution": types_seen,
        "sources_distribution": sources_seen,
        "freshness": f"{'<24h' if fresh else '>24h'}",
    }

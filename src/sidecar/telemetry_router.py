"""遥测接收端点 — OpenClaw / MarefObsClient → MAREF 遥测数据桥梁

增强版 v2:
- HMAC-SHA256 签名验证 (fail-closed)
- JSON Schema 校验
- 幂等去重 (dedup_key)
- 结构化存储 (按 source/telemetry_type 分区)
- 批量写入优化
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telemetry")

_TELEMETRY_ROOT = Path(os.environ.get("MAREF_TELEMETRY_DIR", "data/telemetry"))
_TELEMETRY_ROOT.mkdir(parents=True, exist_ok=True)
_MAX_TELEMETRY_AGE_HOURS = 24

# HMAC 密钥 (与发送端一致)
_HMAC_KEY = os.environ.get("MAREF_TELEMETRY_HMAC_KEY", "").encode("utf-8")
if not _HMAC_KEY:
    # 允许从文件读取
    for cand in (Path.cwd() / ".maref_telemetry_hmac_key", Path.home() / ".maref_telemetry_hmac_key"):
        try:
            _HMAC_KEY = cand.read_text().strip().encode("utf-8")
            if _HMAC_KEY:
                break
        except OSError:
            continue

# 幂等去重: 保存最近 N 个 dedup_key (内存 + 持久化)
_DEDUP_CACHE_SIZE = 100000
_dedup_cache: set[str] = set()
_dedup_cache_file = _TELEMETRY_ROOT / ".dedup_cache.json"
if _dedup_cache_file.exists():
    try:
        with open(_dedup_cache_file) as f:
            _dedup_cache = set(json.load(f))
    except Exception:
        _dedup_cache = set()

# JSON Schema 定义
TELEMETRY_SCHEMA = {
    "type": "object",
    "required": ["source", "telemetry_type", "timestamp", "data"],
    "properties": {
        "source": {"type": "string", "minLength": 1, "maxLength": 128},
        "telemetry_type": {"type": "string", "minLength": 1, "maxLength": 64},
        "timestamp": {"type": "number", "minimum": 0},
        "data": {"type": "object"},
        "signature": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "dedup_key": {"type": "string", "maxLength": 256},
    },
    "additionalProperties": True,
}

OBS_EVENT_BATCH_SCHEMA = {
    "type": "object",
    "required": ["events", "batch_id", "session_id"],
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["session_id", "event_type", "timestamp", "event_sequence"],
                "properties": {
                    "session_id": {"type": "string"},
                    "event_type": {"type": "string"},
                    "version": {"type": "string"},
                    "timestamp": {"type": "number"},
                    "event_sequence": {"type": "integer"},
                    "metadata": {"type": "object"},
                },
            },
            "minItems": 1,
            "maxItems": 1000,
        },
        "batch_id": {"type": "string", "minLength": 1},
        "session_id": {"type": "string", "minLength": 1},
        "client_version": {"type": "string"},
    },
}


def _verify_hmac(payload: dict[str, Any], signature: str) -> bool:
    """验证 HMAC-SHA256 签名 (fail-closed: 无密钥或验证失败均拒绝)"""
    if not _HMAC_KEY:
        logger.error("HMAC key not configured — rejecting request (fail-closed)")
        return False
    if not signature:
        return False

    # 规范化 payload: 排除 signature 字段本身
    verify_payload = {k: v for k, v in payload.items() if k != "signature"}
    canonical = json.dumps(verify_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected = hmac.new(_HMAC_KEY, canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _validate_schema(payload: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, str]:
    """简单的 JSON Schema 校验 (无外部依赖)"""
    # required fields
    for field in schema.get("required", []):
        if field not in payload:
            return False, f"missing required field: {field}"

    props = schema.get("properties", {})
    for field, rules in props.items():
        if field not in payload:
            continue
        value = payload[field]
        expected_type = rules.get("type")

        if expected_type == "string" and not isinstance(value, str):
            return False, f"field '{field}' must be string"
        if expected_type == "number" and not isinstance(value, (int, float)):
            return False, f"field '{field}' must be number"
        if expected_type == "object" and not isinstance(value, dict):
            return False, f"field '{field}' must be object"
        if expected_type == "array" and not isinstance(value, list):
            return False, f"field '{field}' must be array"
        if expected_type == "integer" and not isinstance(value, int):
            return False, f"field '{field}' must be integer"

        if "minLength" in rules and isinstance(value, str) and len(value) < rules["minLength"]:
            return False, f"field '{field}' too short"
        if "maxLength" in rules and isinstance(value, str) and len(value) > rules["maxLength"]:
            return False, f"field '{field}' too long"
        if "minimum" in rules and isinstance(value, (int, float)) and value < rules["minimum"]:
            return False, f"field '{field}' below minimum"
        if "pattern" in rules and isinstance(value, str):
            import re
            if not re.match(rules["pattern"], value):
                return False, f"field '{field}' pattern mismatch"

    return True, ""


def _check_dedup(dedup_key: str | None) -> bool:
    """检查并记录 dedup_key，返回 True 表示重复"""
    if not dedup_key:
        return False
    if dedup_key in _dedup_cache:
        return True
    _dedup_cache.add(dedup_key)
    # 限制缓存大小
    if len(_dedup_cache) > _DEDUP_CACHE_SIZE:
        # 简单清理：移除一半 (实际生产建议用 LRU)
        _dedup_cache.clear()
    _persist_dedup_cache()
    return False


def _persist_dedup_cache() -> None:
    """持久化去重缓存"""
    try:
        with open(_dedup_cache_file, "w") as f:
            json.dump(list(_dedup_cache), f)
    except Exception:
        pass


def _get_storage_path(source: str, telemetry_type: str) -> Path:
    """获取分区存储路径: data/telemetry/{source}/{telemetry_type}/YYYYMMDD.jsonl"""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    safe_source = source.replace("/", "_").replace("\\", "_")
    safe_type = telemetry_type.replace("/", "_").replace("\\", "_")
    dir_path = _TELEMETRY_ROOT / safe_source / safe_type
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / f"{date_str}.jsonl"


def _write_batch(entries: list[dict[str, Any]]) -> tuple[int, int]:
    """批量写入，按 source/type 分区。返回 (成功数, 失败数)"""
    if not entries:
        return 0, 0

    # 按 source/type 分组
    grouped: dict[tuple[str, str], list[dict]] = {}
    for entry in entries:
        source = entry.get("source", "unknown")
        ttype = entry.get("telemetry_type", "unknown")
        grouped.setdefault((source, ttype), []).append(entry)

    success = 0
    failed = 0
    for (source, ttype), batch in grouped.items():
        path = _get_storage_path(source, ttype)
        try:
            with open(path, "a") as f:
                for entry in batch:
                    f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
            success += len(batch)
        except Exception as e:
            logger.error("Failed to write telemetry batch for %s/%s: %s", source, ttype, e)
            failed += len(batch)

    return success, failed


@router.post("/ingest")
async def telemetry_ingest(request: Request) -> dict[str, Any]:
    """接收遥测数据 (单条或批量)

    支持两种格式:
    1. 单条: {source, telemetry_type, timestamp, data, signature?, dedup_key?}
    2. ObsEvent 批量: {source, telemetry_type="obs_event_batch", timestamp, data: {events: [...], batch_id, session_id}, signature?, dedup_key?}
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # 1. 基础 Schema 校验
    ok, err = _validate_schema(payload, TELEMETRY_SCHEMA)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Schema validation failed: {err}")

    # 2. HMAC 签名验证 (fail-closed)
    signature = payload.get("signature", "")
    if not _verify_hmac(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid or missing HMAC signature")

    # 3. 幂等去重
    dedup_key = payload.get("dedup_key")
    if _check_dedup(dedup_key):
        logger.warning("Duplicate telemetry rejected: dedup_key=%s", dedup_key)
        raise HTTPException(status_code=409, detail="Duplicate request (dedup_key)")

    source = payload["source"]
    telemetry_type = payload["telemetry_type"]
    timestamp = payload["timestamp"]
    data = payload["data"]

    # 4. 如果是 ObsEvent 批量，展开写入
    if telemetry_type == "obs_event_batch":
        ok, err = _validate_schema(data, OBS_EVENT_BATCH_SCHEMA)
        if not ok:
            raise HTTPException(status_code=400, detail=f"ObsEvent batch schema failed: {err}")

        events = data["events"]
        batch_id = data["batch_id"]
        session_id = data["session_id"]

        # 转换为统一存储格式
        entries = []
        for ev in events:
            entries.append({
                "source": source,
                "telemetry_type": ev["event_type"],
                "timestamp": ev["timestamp"],
                "data": {
                    "session_id": ev["session_id"],
                    "event_sequence": ev["event_sequence"],
                    "version": ev.get("version", ""),
                    "metadata": ev.get("metadata", {}),
                    "batch_id": batch_id,
                    "client_session_id": session_id,
                },
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            })

        success, failed = _write_batch(entries)
        logger.info("ObsEvent batch ingested: source=%s batch_id=%s events=%d success=%d failed=%d",
                    source, batch_id, len(events), success, failed)
        return {"status": "ok", "batch_id": batch_id, "events_received": len(events), "stored": success}

    # 5. 普通单条/自定义数据
    entry = {
        "source": source,
        "telemetry_type": telemetry_type,
        "timestamp": timestamp,
        "data": data,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    if dedup_key:
        entry["dedup_key"] = dedup_key

    success, failed = _write_batch([entry])
    logger.info("Telemetry ingested: source=%s type=%s success=%d", source, telemetry_type, success)
    return {"status": "ok", "stored": success}


@router.post("/ingest/batch")
async def telemetry_ingest_batch(request: Request) -> dict[str, Any]:
    """批量接收多条遥测 (数组格式)，统一验签/去重/存储"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="Batch endpoint expects JSON array")

    if len(payload) > 1000:
        raise HTTPException(status_code=400, detail="Batch too large (max 1000)")

    results = []
    for item in payload:
        # 复用单条逻辑
        ok, err = _validate_schema(item, TELEMETRY_SCHEMA)
        if not ok:
            results.append({"status": "error", "error": err})
            continue
        if not _verify_hmac(item, item.get("signature", "")):
            results.append({"status": "error", "error": "Invalid signature"})
            continue
        if _check_dedup(item.get("dedup_key")):
            results.append({"status": "error", "error": "Duplicate"})
            continue
        results.append({"status": "ok"})

    # 批量写入
    valid_entries = [item for item, r in zip(payload, results) if r["status"] == "ok"]
    success, failed = _write_batch(valid_entries)

    return {"total": len(payload), "accepted": success, "rejected": failed, "details": results}


@router.get("/status")
def telemetry_status() -> dict[str, Any]:
    """遥测存储状态概览"""
    files = sorted(_TELEMETRY_ROOT.rglob("*.jsonl"), reverse=True)
    if not files:
        return {"status": "no_data", "total_files": 0, "total_size_mb": 0}

    total_lines = 0
    total_size = 0
    types_seen: dict[str, int] = {}
    sources_seen: dict[str, int] = {}
    latest_time = None

    for f in files[:10]:  # 只扫描最新 10 个文件
        total_size += f.stat().st_size
        try:
            with open(f) as fh:
                for line in fh:
                    try:
                        entry = json.loads(line.strip())
                        total_lines += 1
                        t = entry.get("telemetry_type", "unknown")
                        types_seen[t] = types_seen.get(t, 0) + 1
                        s = entry.get("source", "unknown")
                        sources_seen[s] = sources_seen.get(s, 0) + 1
                        ingested = entry.get("ingested_at")
                        if ingested and latest_time is None:
                            latest_time = ingested
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    fresh = False
    if latest_time:
        try:
            t = datetime.fromisoformat(latest_time).replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - t).total_seconds() / 3600
            fresh = age < _MAX_TELEMETRY_AGE_HOURS
        except Exception:
            pass

    return {
        "status": "fresh" if fresh else "stale",
        "total_files": len(files),
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "estimated_lines": total_lines,
        "types_distribution": types_seen,
        "sources_distribution": sources_seen,
        "freshness": f"{'<24h' if fresh else '>24h'}",
        "dedup_cache_size": len(_dedup_cache),
    }


@router.get("/query")
def telemetry_query(
    source: str | None = None,
    telemetry_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """简单查询接口 (按源/类型/时间范围过滤)"""
    files = sorted(_TELEMETRY_ROOT.rglob("*.jsonl"), reverse=True)

    # 时间过滤
    since_ts = None
    until_ts = None
    if since:
        try:
            since_ts = datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    if until:
        try:
            until_ts = datetime.fromisoformat(until.replace("Z", "+00:00")).timestamp()
        except Exception:
            pass

    results = []
    scanned = 0

    for f in files:
        if len(results) >= limit + offset:
            break
        try:
            with open(f) as fh:
                for line in fh:
                    scanned += 1
                    try:
                        entry = json.loads(line.strip())
                        if source and entry.get("source") != source:
                            continue
                        if telemetry_type and entry.get("telemetry_type") != telemetry_type:
                            continue
                        ts = entry.get("timestamp")
                        if since_ts and ts and ts < since_ts:
                            continue
                        if until_ts and ts and ts > until_ts:
                            continue
                        if offset > 0:
                            offset -= 1
                            continue
                        results.append(entry)
                        if len(results) >= limit:
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    return {"results": results, "total_scanned": scanned, "returned": len(results)}


__all__ = ["router"]
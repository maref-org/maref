#!/usr/bin/env python3
"""把 Claude Code 本地 jsonl 的真实 assistant usage 桥接进 cost_events.ndjson。

M4 telemetry_liveness 要求近 24h 有 cost_event。unified_proxy 仅在成功 POST 时写入，
而近端 LLM 流量大量走 claude/opencode 不经 proxy → 遥测断裂。

本脚本只搬运**已发生**的 usage（非伪造）：
  - 扫描 ~/.claude/projects/**/*.jsonl 中 type=assistant 且带 message.usage 的行
  - 以 uuid 做幂等去重（state 落 ~/.maref/audit/cost_bridge_state.json）
  - HMAC 签名追加写入 ~/.maref/audit/cost_events.ndjson（与 cost_guard 对齐）
  - actor=cost_bridge_real_traffic, source=claude_jsonl

用法:
    python3 scripts/cost_bridge_claude.py            # 桥近 24h
    python3 scripts/cost_bridge_claude.py --hours 6
    python3 scripts/cost_bridge_claude.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _audit_base() -> Path:
    return Path(os.environ.get("UP_AUDIT_DIR", str(Path.home() / ".maref" / "audit")))


def _state_path() -> Path:
    return _audit_base() / "cost_bridge_state.json"


def _events_path() -> Path:
    return _audit_base() / "cost_events.ndjson"


def _audit_key() -> bytes:
    env_key = os.environ.get("MAREF_HMAC_SECRET_KEY", "") or ""
    if env_key:
        return env_key.encode()
    for cand in (Path.home() / ".maraf_hmac_key", Path.cwd() / ".maraf_hmac_key"):
        try:
            key = cand.read_text().strip()
            if key:
                return key.encode()
        except OSError:
            continue
    return b""


def _claude_roots() -> list[Path]:
    base = Path.home() / ".claude" / "projects"
    return [base] if base.is_dir() else []


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(_state_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {"bridged_ids": []}


def _save_state(state: dict[str, Any]) -> None:
    # 只保留近 7 天 id，防 state 无限膨胀
    cutoff = time.time() - 7 * 86400
    kept = [e for e in state.get("bridged_ids", []) if isinstance(e, dict) and e.get("ts", 0) >= cutoff]
    state = {"bridged_ids": kept, "updated_at": time.time()}
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    os.replace(tmp, path)


def _parse_ts(ts: str) -> float | None:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    except (ValueError, AttributeError):
        return None


def _usage_to_record(obj: dict[str, Any], event_id: str, ts: float) -> dict[str, Any] | None:
    msg = obj.get("message") or {}
    usage = msg.get("usage") or {}
    if not usage:
        return None
    model = msg.get("model") or "unknown"
    in_tok = int(usage.get("input_tokens") or 0)
    out_tok = int(usage.get("output_tokens") or 0)
    cache_r = int(usage.get("cache_read_input_tokens") or 0)
    cache_c = int(usage.get("cache_creation_input_tokens") or 0)
    # 与既有 bridge 行字段对齐（chars≈4B/token 粗估，保持可比）
    return {
        "event_type": "cost_event",
        "timestamp": ts,
        "model": model,
        "input_chars": (in_tok + cache_r + cache_c) * 4,
        "output_chars": out_tok * 4,
        "wall_ms": 0,
        "guard": "none",
        "actor": "cost_bridge_real_traffic",
        "source": "claude_jsonl",
        "bridge_id": event_id,
        "tokens_in": in_tok + cache_r + cache_c,
        "tokens_out": out_tok,
    }


def _append_signed(path: Path, record: dict[str, Any]) -> bool:
    key = _audit_key()
    if not key:
        print("[cost-bridge] no HMAC key — fail-closed, skip write", file=sys.stderr)
        return False
    payload = json.dumps(record, ensure_ascii=False, default=str)
    sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    line = json.dumps({**record, "hmac_signature": sig}, ensure_ascii=False)
    with path.open("a") as f:
        f.write(line + "\n")
        f.flush()
    return True


def collect_events(hours: float, seen_ids: set[str]) -> list[tuple[str, dict[str, Any]]]:
    cutoff = time.time() - hours * 3600
    out: list[tuple[str, dict[str, Any]]] = []
    for root in _claude_roots():
        for jsonl in root.rglob("*.jsonl"):
            try:
                text = jsonl.read_text(errors="replace")
            except OSError:
                continue
            for raw in text.splitlines():
                raw = raw.strip()
                if not raw or '"assistant"' not in raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                uuid = obj.get("uuid") or ""
                ts = _parse_ts(obj.get("timestamp") or "")
                if ts is None or ts < cutoff:
                    continue
                event_id = uuid or hashlib.sha1(
                    f"{ts}:{json.dumps(obj.get('message', {}), sort_keys=True)[:200]}".encode()
                ).hexdigest()[:16]
                if event_id in seen_ids:
                    continue
                rec = _usage_to_record(obj, event_id, ts)
                if rec is None:
                    continue
                out.append((event_id, rec))
    out.sort(key=lambda x: x[1]["timestamp"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge Claude jsonl usage → cost_events.ndjson")
    parser.add_argument("--hours", type=float, default=24.0, help="Lookback window (hours)")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no write")
    args = parser.parse_args()

    events_path = _events_path()
    events_path.parent.mkdir(parents=True, exist_ok=True)
    state = _load_state()
    seen = {e["id"] for e in state.get("bridged_ids", []) if isinstance(e, dict) and "id" in e}

    batch = collect_events(args.hours, seen)
    if not batch:
        print(f"[cost-bridge] no new events in {args.hours}h (seen={len(seen)})")
        return 0

    written = 0
    now = time.time()
    for event_id, rec in batch:
        if args.dry_run:
            print(f"[dry-run] {event_id} ts={rec['timestamp']:.0f} model={rec['model']}")
            continue
        if _append_signed(events_path, rec):
            written += 1
            state.setdefault("bridged_ids", []).append({"id": event_id, "ts": now})

    if not args.dry_run:
        _save_state(state)

    # 自检近 24h 事件数（与 check_cost 同口径）
    n24 = 0
    if events_path.exists():
        for ln in events_path.read_text().splitlines():
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            ts = d.get("timestamp", 0)
            if isinstance(ts, (int, float)) and now - ts <= 86400:
                n24 += 1

    print(f"[cost-bridge] bridged={written} events_24h={n24} path={events_path}")
    return 0 if (args.dry_run or written > 0 or n24 > 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())

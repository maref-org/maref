#!/usr/bin/env python3
"""审计生产链每日心跳 (P1-C) — 补位缺失的生产写入方

根因报告: docs/audit-reports/audit-stale-rootcause-verification-20260923.md

写入目标（与 audit_health_check inventory 对齐）:
1. openclaw_state_machine — runtime/.governance/governance_audit.jsonl
   使用 state_machine 同构 HMAC chain（保持链连续，可被 _last_chain_hash 续写）
2. recursive_production — runtime/recursive_governance_audit.jsonl
   使用 AuditLogger（HMAC-SHA256 签名）
3. sidecar_claimed — runtime/governance_audit.jsonl
   使用 AuditLogger（sidecar 启动/管线链）

心跳元数据 source=heartbeat，健康检查据此区分 heartbeat_only 与 real_traffic。
心跳证明管道通畅，不能替代真实决策流量（P0 报告 §5 语义）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from pathlib import Path

from maref_config import REPO_DIR, RUNTIME_DIR


def _load_env_keys(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def _resolve_hmac_key() -> bytes | None:
    env_key = os.environ.get("MAREF_HMAC_SECRET_KEY", "").strip()
    if env_key:
        return env_key.encode("utf-8")
    file_key = os.environ.get("MAREF_HMAC_KEY_FILE", "").strip()
    candidates = [Path(file_key)] if file_key else []
    candidates.extend(
        [
            RUNTIME_DIR / ".maraf_hmac_key",
            REPO_DIR / ".maraf_hmac_key",
            Path.home() / ".maref.env",
        ]
    )
    for cand in candidates:
        if not cand.exists():
            continue
        try:
            if cand.suffix == ".env" or cand.name.endswith(".env"):
                v = _load_env_keys(cand).get("MAREF_HMAC_SECRET_KEY", "").strip()
                if v:
                    return v.encode("utf-8")
            else:
                v = cand.read_text().strip()
                if v:
                    return v.encode("utf-8")
        except OSError:
            continue
    return None


def _append_state_machine_heartbeat(path: Path, hmac_key: bytes) -> dict:
    """按 state_machine _write_state_transition 同构格式追加心跳，保持 chain 连续。"""
    previous_hash = ""
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 65536))
                tail = fh.read().decode("utf-8", errors="replace")
                for line in reversed(tail.splitlines()):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        prev = json.loads(line)
                        previous_hash = prev.get("chain_hash", prev.get("id", ""))
                        break
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

    now = time.time()
    entry_id = f"audit_{uuid.uuid4().hex[:8]}"
    payload = json.dumps(
        {
            "id": entry_id,
            "timestamp": now,
            "event_type": "state_transition",
            "actor": "state_machine",
            "action": "DAILY_CYCLE_HEARTBEAT",
            "details": "P1-C production writer heartbeat (daily governance cycle)",
            "metadata": {
                "source": "heartbeat",
                "kind": "daily_cycle_heartbeat",
                "previous_hash": previous_hash,
            },
            "previous_hash": previous_hash,
        },
        ensure_ascii=False,
        default=str,
    )
    chain_hash = hmac.new(hmac_key, payload.encode(), hashlib.sha256).hexdigest()
    record = json.loads(payload)
    record["chain_hash"] = chain_hash

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return record


def _append_auditlogger_heartbeat(path: Path, hmac_key: bytes) -> dict:
    """按 AuditEntry._payload_for_signing 同构格式写 HMAC 心跳（不 import 框架，兼容 py3.9）。"""
    previous_hash = ""
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 65536))
                tail = fh.read().decode("utf-8", errors="replace")
                for line in reversed(tail.splitlines()):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        prev = json.loads(line)
                        previous_hash = prev.get("chain_hash", "")
                        break
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

    now = time.time()
    entry_id = f"audit_{uuid.uuid4().hex[:8]}"
    metadata = {
        "source": "heartbeat",
        "kind": "daily_cycle_heartbeat",
        "verdict": "allow",
    }
    # AuditEntry._payload_for_signing 子集（无 tenant/layer/round 时）
    payload_obj = {
        "id": entry_id,
        "timestamp": now,
        "event_type": "governance_decision",
        "actor": "daily_cycle",
        "action": "daily_cycle_heartbeat",
        "details": "P1-C production writer heartbeat (heartbeat_only traffic)",
        "metadata": metadata,
        "previous_hash": previous_hash,
    }
    payload = json.dumps(payload_obj, sort_keys=True, ensure_ascii=False, default=str)
    chain_hash = hashlib.sha256(previous_hash.encode("utf-8") + payload.encode("utf-8")).hexdigest()
    sig = hmac.new(hmac_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    record = dict(payload_obj)
    record["chain_hash"] = chain_hash
    record["hmac_signature"] = sig

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return record


def main() -> int:
    print("=" * 60)
    print("审计生产链每日心跳 (P1-C)")
    print("=" * 60)

    hmac_key = _resolve_hmac_key()
    if not hmac_key:
        print("❌ 缺少 MAREF_HMAC_SECRET_KEY — fail-closed，跳过心跳写入")
        return 1

    results: list[dict] = []

    # 1. openclaw state_machine 主链（HMAC chain 同构）
    sm_path = RUNTIME_DIR / ".governance" / "governance_audit.jsonl"
    try:
        rec = _append_state_machine_heartbeat(sm_path, hmac_key)
        results.append(
            {"chain": "openclaw_state_machine", "path": str(sm_path), "id": rec.get("id"), "ok": True}
        )
        print(f"  ✅ openclaw_state_machine → {sm_path}")
    except Exception as e:
        results.append({"chain": "openclaw_state_machine", "ok": False, "error": str(e)})
        print(f"  ❌ openclaw_state_machine: {e}")

    # 2. recursive 生产链（AuditLogger）
    rec_path = RUNTIME_DIR / "recursive_governance_audit.jsonl"
    try:
        _append_auditlogger_heartbeat(rec_path, hmac_key)
        results.append({"chain": "recursive_production", "path": str(rec_path), "ok": True})
        print(f"  ✅ recursive_production → {rec_path}")
    except Exception as e:
        results.append({"chain": "recursive_production", "ok": False, "error": str(e)})
        print(f"  ❌ recursive_production: {e}")

    # 3. sidecar 声称路径（AuditLogger；sidecar 启动也会写）
    side_path = RUNTIME_DIR / "governance_audit.jsonl"
    try:
        _append_auditlogger_heartbeat(side_path, hmac_key)
        results.append({"chain": "sidecar_claimed", "path": str(side_path), "ok": True})
        print(f"  ✅ sidecar_claimed → {side_path}")
    except Exception as e:
        results.append({"chain": "sidecar_claimed", "ok": False, "error": str(e)})
        print(f"  ❌ sidecar_claimed: {e}")

    ok_count = sum(1 for r in results if r.get("ok"))
    print(f"\n心跳完成: {ok_count}/{len(results)} 条链写入成功")
    print("语义: metadata.source=heartbeat → 健康检查标 heartbeat_only（管道通 ≠ 真实决策流量）")
    return 0 if ok_count >= 2 else 1


if __name__ == "__main__":
    sys.exit(main())

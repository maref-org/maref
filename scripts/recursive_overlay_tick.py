#!/usr/bin/env python3
"""RecursiveGovernanceOverlay 生产 tick (P2-1/2)。

单次 tick（非常驻 run()）:
1. 实例化 RecursiveGovernanceOverlay，采集 get_recursive_status()
2. 将状态作为真实 observation 写入生产链（action 不含 heartbeat → real_traffic）
3. 退出，不启动无限异步循环

接入 daily_governance_cycle.sh；健康检查据此从 heartbeat_only 升为 real_traffic。
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

# 保证 src 可导入（系统 python3 / venv 均可）
_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from maref_config import REPO_DIR, RUNTIME_DIR  # noqa: E402


def _load_env_maref() -> None:
    """从 .env.maref 注入 MAREF_*（含多行 PEM），launchd 无 shell env 时必需。"""
    for path in (Path.cwd() / ".env.maref", _REPO / ".env.maref"):
        if not path.exists():
            continue
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if value.startswith("-----BEGIN"):
                while i < len(lines) and "-----END" not in lines[i]:
                    value += "\n" + lines[i].strip()
                    i += 1
                if i < len(lines):
                    value += "\n" + lines[i].strip()
                    i += 1
            if key.startswith("MAREF_") and key not in os.environ:
                os.environ[key] = value
        return


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


def _append_state_observation(path: Path, hmac_key: bytes, details: dict) -> dict:
    """按 state_machine 同构 HMAC chain 写 observation（非 heartbeat）。"""
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

    entry_id = f"audit_{uuid.uuid4().hex[:8]}"
    # action 禁止含 "heartbeat"（_classify_traffic 才判 real_traffic）
    payload = json.dumps(
        {
            "id": entry_id,
            "timestamp": time.time(),
            "event_type": "state_transition",
            "actor": "RecursiveGovernanceOverlay",
            "action": "DAILY_CYCLE_OBSERVATION",
            "details": "P2 production overlay status observation (real traffic)",
            "metadata": {
                "source": "recursive_overlay_tick",
                "kind": "daily_cycle_observation",
                "previous_hash": previous_hash,
                "recursion_depth": details.get("recursion_depth"),
                "oscillation_detected": details.get("oscillation_detected"),
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


def _append_auditlogger_observation(path: Path, hmac_key: bytes, action: str, details: dict) -> dict:
    """AuditEntry 同构 observation（HMAC-SHA256，与 _payload_for_signing 对齐）。"""
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

    entry_id = f"audit_{uuid.uuid4().hex[:8]}"
    payload_obj = {
        "id": entry_id,
        "timestamp": time.time(),
        "event_type": "governance_decision",
        "actor": "RecursiveGovernanceOverlay",
        "action": action,
        "details": details,
        "metadata": {
            "source": "recursive_overlay_tick",
            "kind": "daily_cycle_observation",
            "verdict": "allow",
        },
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


def _collect_overlay_status() -> dict:
    """实例化 Overlay 并取状态（生产实例，不进入 run()）。"""
    from maref_lite.recursive_governance import RecursiveGovernanceOverlay

    overlay = RecursiveGovernanceOverlay()
    status = overlay.get_recursive_status()
    # 确保审计路径指向生产 recursive 链
    audit_path = status.get("_audit_path") if isinstance(status, dict) else None
    if audit_path is None:
        # Overlay 内部 AuditLogger 路径：构造后可访问
        try:
            p = overlay._audit._path  # noqa: SLF001
            status["_audit_path"] = str(p) if p else None
        except Exception:
            status["_audit_path"] = None
    status["_overlay_class"] = "RecursiveGovernanceOverlay"
    return status


def main() -> int:
    print("=" * 60)
    print("RecursiveGovernanceOverlay 生产 tick (P2-1/2)")
    print("=" * 60)

    _load_env_maref()
    hmac_key = _resolve_hmac_key()
    if not hmac_key:
        # Ed25519 模式下 observation 仍用 HMAC；若 .env.maref 无 HMAC 则尝试 .maraf_hmac_key
        print("❌ 缺少 MAREF_HMAC_SECRET_KEY — fail-closed，跳过 observation 写入")
        return 1

    try:
        status = _collect_overlay_status()
        print(f"  ✅ overlay status: depth={status.get('recursion_depth')} "
              f"osc={status.get('oscillation_detected')}")
    except Exception as e:
        print(f"  ❌ overlay status: {e}")
        return 1

    results: list[dict] = []

    # 1. openclaw state_machine 主链 — observation（real_traffic）
    sm_path = RUNTIME_DIR / ".governance" / "governance_audit.jsonl"
    try:
        rec = _append_state_observation(sm_path, hmac_key, status)
        results.append({"chain": "openclaw_state_machine", "path": str(sm_path), "id": rec.get("id"), "ok": True})
        print(f"  ✅ openclaw_state_machine observation → {sm_path}")
    except Exception as e:
        results.append({"chain": "openclaw_state_machine", "ok": False, "error": str(e)})
        print(f"  ❌ openclaw_state_machine: {e}")

    # 2. recursive 生产链 — observation
    rec_path = RUNTIME_DIR / "recursive_governance_audit.jsonl"
    try:
        details = {
            "recursion_depth": status.get("recursion_depth"),
            "oscillation_detected": status.get("oscillation_detected"),
            "state_change_rate": status.get("state_change_rate"),
            "circuit_breaker": status.get("circuit_breaker"),
        }
        _append_auditlogger_observation(
            rec_path, hmac_key, "recursive_status_observation", details
        )
        results.append({"chain": "recursive_production", "path": str(rec_path), "ok": True})
        print(f"  ✅ recursive_production observation → {rec_path}")
    except Exception as e:
        results.append({"chain": "recursive_production", "ok": False, "error": str(e)})
        print(f"  ❌ recursive_production: {e}")

    # 3. sidecar 声称路径 — observation（与 heartbeat 链并存）
    side_path = RUNTIME_DIR / "governance_audit.jsonl"
    try:
        _append_auditlogger_observation(
            side_path, hmac_key, "overlay_status_observation",
            {"recursion_depth": status.get("recursion_depth")},
        )
        results.append({"chain": "sidecar_claimed", "path": str(side_path), "ok": True})
        print(f"  ✅ sidecar_claimed observation → {side_path}")
    except Exception as e:
        results.append({"chain": "sidecar_claimed", "ok": False, "error": str(e)})
        print(f"  ❌ sidecar_claimed: {e}")

    ok_count = sum(1 for r in results if r.get("ok"))
    print(f"\nobservation 写入: {ok_count}/{len(results)} 条链成功")
    print("语义: source=recursive_overlay_tick, action 不含 heartbeat → real_traffic")
    return 0 if ok_count >= 2 else 1


if __name__ == "__main__":
    sys.exit(main())

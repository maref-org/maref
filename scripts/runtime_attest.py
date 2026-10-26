#!/usr/bin/env python3
"""Emit a signed runtime health attestation.

The attestation contains only a sanitized aggregate of the meta-monitor
report (booleans, counts, rates) — no paths, hostnames or alert text — plus
``generated_at`` and a SHA-256 of the source report. It is signed with
Ed25519 so a public-checkout CI job can verify it without a self-hosted
runner.

Usage:
    MAREF_ATTEST_PRIVATE_KEY="$(cat ~/.maref/attest_ed25519.pem)" \\
        python3 scripts/runtime_attest.py --out reports/runtime_attest.json
    python3 scripts/runtime_attest.py --report .governance/meta/meta-monitor-report.json \\
        --private-key ~/.maref/attest_ed25519.pem

Exit codes: 0 = written and self-verified, 1 = runtime/signing failure,
2 = tooling or configuration error.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SCHEMA = "maref.runtime_attestation/v1"
DEFAULT_OUT = Path("reports/runtime_attest.json")


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _load_private_key(path: str | None) -> Ed25519PrivateKey:
    if path:
        data = Path(path).expanduser().read_bytes()
    else:
        pem = os.environ.get("MAREF_ATTEST_PRIVATE_KEY", "")
        if not pem:
            raise ValueError("no signing key: pass --private-key or set MAREF_ATTEST_PRIVATE_KEY")
        data = pem.encode("utf-8")
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("private key must be Ed25519")
    return key


def _public_pem(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def key_id_for(public_pem: bytes) -> str:
    return hashlib.sha256(public_pem).hexdigest()[:32]


def _claims(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") or {}
    m0 = report.get("m0") or {}
    m1 = report.get("m1") or {}
    m2 = report.get("m2") or {}
    m4 = report.get("m4") or {}
    agents = (m0.get("checks") or {}).get("managed_agents") or {}
    chain = m1.get("chain_integrity") or {}
    staleness = m2.get("notification_staleness") or {}
    channel = m2.get("alert_channel") or {}
    guard = (m4.get("checks") or {}).get("guard_block_rate") or {}
    return {
        "all_passed": bool(summary.get("all_passed", False)),
        "checks": {f"m{i}": bool(summary.get(f"m{i}_passed", False)) for i in range(5)},
        "agents": {
            "survival_rate": agents.get("survival_rate"),
            "active_total": agents.get("active_total"),
            "dead": len(agents.get("dead") or []),
            "retired": len(agents.get("retired") or []),
        },
        "audit_chain": {
            "max_records_scanned": chain.get("max_records_scanned"),
            "truncated": bool(chain.get("truncated", False)),
        },
        "feedback": {
            "open_alerts": staleness.get("open_alerts"),
            "stale_24h": staleness.get("stale_24h"),
            "stale_72h": staleness.get("stale_72h"),
            "channel_status": channel.get("status"),
        },
        "cost": {
            "guarded_24h": guard.get("guarded_24h"),
            "coverage": guard.get("coverage"),
        },
        "signature_mode": report.get("signature_mode"),
    }


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_attestation(
    report: dict[str, Any],
    key: Ed25519PrivateKey,
    generated_at: str,
) -> dict[str, Any]:
    report_bytes = canonical(report)
    payload = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "source": {
            "component": "maref-meta-monitor",
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "report_timestamp": report.get("timestamp"),
        },
        "claims": _claims(report),
    }
    signature = key.sign(canonical(payload))
    public_pem = _public_pem(key)
    return {
        "payload": payload,
        "signature": {
            "alg": "ed25519",
            "key_id": key_id_for(public_pem),
            "value": base64.b64encode(signature).decode("ascii"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign a runtime health attestation")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Existing meta-monitor report (default: run the monitor once)",
    )
    parser.add_argument("--private-key", default=None, help="Ed25519 private key PEM")
    parser.add_argument(
        "--generated-at",
        default=None,
        help="ISO-8601 UTC timestamp override (for tests/backfill)",
    )
    args = parser.parse_args()

    try:
        key = _load_private_key(args.private_key)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.report is not None:
        try:
            report = json.loads(args.report.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read report {args.report}: {exc}", file=sys.stderr)
            return 2
    else:
        src = Path(__file__).resolve().parents[1] / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from maref.observability.meta_monitor import run_once

        report = run_once()

    if not isinstance(report, dict) or not isinstance(report.get("summary"), dict):
        print("ERROR: report has no summary object", file=sys.stderr)
        return 2

    generated_at = args.generated_at or _iso_now()
    attestation = build_attestation(report, key, generated_at)

    # Self-check before writing: never emit a signature we cannot verify.
    try:
        key.public_key().verify(
            base64.b64decode(attestation["signature"]["value"]),
            canonical(attestation["payload"]),
        )
    except Exception as exc:
        print(f"ERROR: self-verification failed: {exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(attestation, indent=2, ensure_ascii=False) + "\n")
    print(
        f"attestation written: {args.out} "
        f"(all_passed={attestation['payload']['claims']['all_passed']}, "
        f"generated_at={generated_at})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

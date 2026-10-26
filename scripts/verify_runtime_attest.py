#!/usr/bin/env python3
"""Verify a signed runtime attestation with a pinned public key.

Checks, in order: schema, pinned key id, Ed25519 signature, freshness
(default ≤24h, ≤5min clock skew), and optionally that the attested claims
report health (``--require-healthy``). Any failure is a failure — there is no
"unsigned counts as verified" path.

Usage:
    python3 scripts/verify_runtime_attest.py \\
        --attest reports/runtime_attest.json \\
        --public-key configs/runtime-attest-public.pub
    python3 scripts/verify_runtime_attest.py --attest ... --public-key ... --require-healthy

Exit codes: 0 = verified, 1 = invalid/expired/unhealthy, 2 = tooling/config.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMA = "maref.runtime_attestation/v1"
DEFAULT_PUBLIC_KEY = Path("configs/runtime-attest-public.pub")


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _parse_ts(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def verify(
    attestation: dict,
    public_key: Ed25519PublicKey,
    *,
    max_age_hours: float,
    require_healthy: bool,
    now: datetime | None = None,
) -> tuple[bool, list[str], dict]:
    problems: list[str] = []
    now = now or datetime.now(timezone.utc)

    payload = attestation.get("payload")
    signature = attestation.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, dict):
        return False, ["attestation must contain payload and signature objects"], {}

    if payload.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA}")

    if signature.get("alg") != "ed25519":
        problems.append("signature.alg must be ed25519")
    if not signature.get("value"):
        problems.append("signature.value is missing")

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    expected_key_id = hashlib.sha256(public_pem).hexdigest()[:32]
    if signature.get("key_id") != expected_key_id:
        problems.append("signature.key_id does not match the pinned public key")

    if signature.get("value") and signature.get("alg") == "ed25519":
        try:
            public_key.verify(
                base64.b64decode(signature["value"], validate=True),
                canonical(payload),
            )
        except (InvalidSignature, ValueError, KeyError) as exc:
            problems.append(f"signature invalid: {exc}")

    generated_at = payload.get("generated_at")
    age_seconds = None
    if not isinstance(generated_at, str):
        problems.append("payload.generated_at must be an ISO-8601 string")
    else:
        try:
            generated = _parse_ts(generated_at)
            age_seconds = (now - generated).total_seconds()
            if age_seconds < -300:
                problems.append(f"generated_at is in the future ({-age_seconds:.0f}s)")
            elif age_seconds > max_age_hours * 3600:
                problems.append(
                    f"attestation expired: age {age_seconds / 3600:.1f}h > {max_age_hours:.1f}h"
                )
        except ValueError:
            problems.append("payload.generated_at is not parseable")

    claims = payload.get("claims")
    if not isinstance(claims, dict):
        problems.append("payload.claims must be an object")
        claims = {}
    if require_healthy and claims.get("all_passed") is not True:
        problems.append("attested claims are not healthy (all_passed != true)")

    detail = {
        "schema": payload.get("schema"),
        "generated_at": generated_at,
        "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "key_id": signature.get("key_id"),
        "all_passed": claims.get("all_passed"),
        "checks": claims.get("checks"),
    }
    return not problems, problems, detail


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a runtime attestation")
    parser.add_argument("--attest", required=True, type=Path)
    parser.add_argument("--public-key", type=Path, default=DEFAULT_PUBLIC_KEY)
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument(
        "--require-healthy",
        action="store_true",
        help="also fail when claims.all_passed is not true",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.attest.is_file():
        print(f"ERROR: attestation not found: {args.attest}", file=sys.stderr)
        return 2
    if not args.public_key.is_file():
        print(f"ERROR: public key not found: {args.public_key}", file=sys.stderr)
        return 2

    try:
        attestation = json.loads(args.attest.read_text())
        public_key = serialization.load_pem_public_key(args.public_key.read_bytes())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not isinstance(public_key, Ed25519PublicKey):
        print("ERROR: public key must be Ed25519", file=sys.stderr)
        return 2

    ok, problems, detail = verify(
        attestation,
        public_key,
        max_age_hours=args.max_age_hours,
        require_healthy=args.require_healthy,
    )

    if args.json:
        print(
            json.dumps(
                {"verified": ok, "problems": problems, "detail": detail},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"attestation: {'VERIFIED' if ok else 'FAILED'}")
        print(f"  generated_at: {detail.get('generated_at')} (age {detail.get('age_seconds')}s)")
        print(f"  key_id: {detail.get('key_id')}")
        print(f"  all_passed: {detail.get('all_passed')}")
        for problem in problems:
            print(f"  - {problem}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

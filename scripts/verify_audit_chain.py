#!/usr/bin/env python3
"""Standalone audit chain verification.

Verifies chain linkage, record hashes, and optional Ed25519/HMAC signatures.
Supports both ``AuditLogger`` records and legacy state-machine records.

Usage:
    python3 scripts/verify_audit_chain.py --audit-file audit.jsonl
    python3 scripts/verify_audit_chain.py --audit-file audit.jsonl --json
    python3 scripts/verify_audit_chain.py --audit-file audit.jsonl \\
        --public-key signer.pem
    python3 scripts/verify_audit_chain.py --audit-file archived.jsonl \\
        --expect-failed

``--expect-failed`` is for quarantined chains: a verification failure exits 0,
while an unexpected pass exits 1. This keeps archived evidence checkable
without letting it masquerade as a healthy live chain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from maref.governance.audit_chain_verify import (  # noqa: E402
    resolve_hmac_key,
    verify_audit_chain,
)


def merkle_hash_pair(left: str, right: str) -> str:
    return hashlib.sha256((left + right).encode()).hexdigest()


def verify_merkle_proof(
    target_hash: str, proof: list[list[str | bool]], expected_root: str
) -> bool:
    current = target_hash
    for sibling_hash, direction in proof:
        if direction == "left" or direction is False:
            current = merkle_hash_pair(sibling_hash, current)
        else:
            current = merkle_hash_pair(current, sibling_hash)
    return current == expected_root


def verify_merkle_proof_file(proof_path: str) -> tuple[bool, str]:
    with open(proof_path) as f:
        data = json.load(f)

    target = data.get("target_hash", data.get("leaf_hash", ""))
    proof_path_list = data.get("proof_path", data.get("proof", []))
    root = data.get("root_hash", data.get("merkle_root", ""))

    if not target:
        return False, "Missing target_hash/leaf_hash in proof file"
    if not proof_path_list:
        return False, "Missing proof_path/proof in proof file"
    if not root:
        return False, "Missing root_hash/merkle_root in proof file"

    if verify_merkle_proof(target, proof_path_list, root):
        return True, f"Merkle proof valid: {target[:12]}... -> {root[:12]}..."
    return False, f"Merkle proof invalid: {target[:12]}... does not chain to {root[:12]}..."


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify MAREF audit chain integrity")
    parser.add_argument("--audit-file", required=True, help="Path to audit JSONL file")
    parser.add_argument(
        "--public-key",
        default=None,
        help="Path to Ed25519 public key PEM (for signature verification)",
    )
    parser.add_argument(
        "--hmac-key",
        default=None,
        help="HMAC key (defaults to MAREF_HMAC_SECRET_KEY or on-disk key file)",
    )
    parser.add_argument(
        "--merkle-proof",
        default=None,
        help="Path to Merkle proof JSON file (for offline proof verification)",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--expect-failed",
        action="store_true",
        help=(
            "The chain is quarantined/archived: exit 0 when verification fails, "
            "exit 1 when it unexpectedly passes"
        ),
    )
    args = parser.parse_args()

    audit_path = Path(args.audit_file)
    if not audit_path.exists():
        print(f"Error: audit file not found: {audit_path}", file=sys.stderr)
        return 1

    public_key_pem = None
    if args.public_key:
        public_key_pem = Path(args.public_key).read_text()

    hmac_key = resolve_hmac_key(args.hmac_key)
    report = verify_audit_chain(
        audit_path,
        hmac_key=hmac_key,
        ed25519_public_key_pem=public_key_pem,
    )

    expected_failed = bool(args.expect_failed)
    if args.json:
        payload = report.to_dict()
        payload["archived"] = expected_failed
        payload["expected_failed"] = expected_failed
        if expected_failed:
            payload["expectation_met"] = not report.integrity_intact
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        status = "OK" if report.integrity_intact else "FAILED"
        print(f"Chain integrity: {status} ({report.total} records)")
        if expected_failed:
            verdict = "as expected" if not report.integrity_intact else "UNEXPECTED PASS"
            print(f"  archived: true (expected FAILED; {verdict})")
        print(f"  formats: {report.formats}")
        print(f"  link breaks: {len(report.link_breaks)}")
        print(f"  hash invalid: {len(report.hash_invalid)}")
        print(f"  signature invalid: {len(report.signature_invalid)}")
        print(f"  signature unverifiable: {len(report.signature_unverifiable)}")
        print(f"  unsigned: {len(report.unsigned)}")
        if report.notes:
            for note in report.notes[:10]:
                print(f"  note: {note}")

    if expected_failed:
        exit_code = 0 if not report.integrity_intact else 1
    else:
        exit_code = 0 if report.integrity_intact else 1

    if args.merkle_proof:
        if not Path(args.merkle_proof).exists():
            print(f"Error: proof file not found: {args.merkle_proof}", file=sys.stderr)
            return 1
        ok, msg = verify_merkle_proof_file(args.merkle_proof)
        print(f"{'OK' if ok else 'FAILED'} Merkle proof: {msg}")
        if not ok:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

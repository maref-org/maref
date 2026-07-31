#!/usr/bin/env python3
"""Standalone audit chain verification script.

Verifies all four layers of MAREF audit chain integrity without requiring
the MAREF framework to be installed. Only needs Python 3.10+ standard
library + cryptography package for Ed25519 verification.

Usage:
    # Verify chain integrity only
    python3 scripts/verify_audit_chain.py --audit-file audit.jsonl

    # Verify chain + Ed25519 signatures
    python3 scripts/verify_audit_chain.py \\
        --audit-file audit.jsonl --public-key signer.pem

    # Verify chain + Merkle proof
    python3 scripts/verify_audit_chain.py \\
        --audit-file audit.jsonl --merkle-proof proof.json

    # For federated proof verification, use:
    #   maref federated verify proof.json [--pubkey signer.pem]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def verify_chain(filepath: str) -> tuple[bool, str]:
    with open(filepath) as f:
        entries = [json.loads(line) for line in f if line.strip()]

    if not entries:
        return False, "Empty audit file"

    previous = ""
    for entry in entries:
        if entry.get("previous_hash", "") != previous:
            return False, f"Chain broken at entry {entry.get('id', '?')}"
        payload = json.dumps(
            {
                "id": entry["id"],
                "timestamp": entry["timestamp"],
                "event_type": entry["event_type"],
                "actor": entry["actor"],
                "action": entry["action"],
                "details": entry["details"],
                "metadata": entry.get("metadata", {}),
                "previous_hash": entry.get("previous_hash", ""),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        expected = hashlib.sha256(
            entry.get("previous_hash", "").encode() + payload.encode()
        ).hexdigest()
        if entry.get("chain_hash", "") != expected:
            return False, f"Hash mismatch at entry {entry.get('id', '?')}"
        previous = entry["chain_hash"]

    return True, f"All {len(entries)} entries verified"


def verify_ed25519_signatures(filepath: str, public_key_pem_path: str) -> tuple[int, int]:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        print("Error: 'cryptography' package required for Ed25519 verification", file=sys.stderr)
        print("Install: pip install cryptography", file=sys.stderr)
        sys.exit(1)

    pubkey_pem = Path(public_key_pem_path).read_text()
    pubkey = serialization.load_pem_public_key(pubkey_pem.encode())

    with open(filepath) as f:
        entries = [json.loads(line) for line in f if line.strip()]

    valid = 0
    total = 0
    for entry in entries:
        sig = entry.get("ed25519_signature", "")
        if not sig:
            continue
        total += 1
        payload = json.dumps(
            {
                "id": entry["id"],
                "timestamp": entry["timestamp"],
                "event_type": entry["event_type"],
                "actor": entry["actor"],
                "action": entry["action"],
                "details": entry["details"],
                "metadata": entry.get("metadata", {}),
                "previous_hash": entry.get("previous_hash", ""),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode()
        try:
            pubkey.verify(bytes.fromhex(sig), payload)
            valid += 1
        except InvalidSignature:
            pass

    return valid, total


def merkle_hash_pair(left: str, right: str) -> str:
    return hashlib.sha256((left + right).encode()).hexdigest()


def verify_merkle_proof(target_hash: str, proof: list[list[str | bool]], expected_root: str) -> bool:
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

    ok = verify_merkle_proof(target, proof_path_list, root)
    if ok:
        return True, f"Merkle proof valid: {target[:12]}... → {root[:12]}..."
    return False, f"Merkle proof invalid: {target[:12]}... does not chain to {root[:12]}..."


def main():
    parser = argparse.ArgumentParser(
        description="Verify MAREF audit chain integrity"
    )
    parser.add_argument("--audit-file", required=True, help="Path to audit JSONL file")
    parser.add_argument(
        "--public-key",
        default=None,
        help="Path to Ed25519 public key PEM (for signature verification)",
    )
    parser.add_argument(
        "--merkle-proof",
        default=None,
        help="Path to Merkle proof JSON file (for offline proof verification)",
    )
    args = parser.parse_args()

    if not Path(args.audit_file).exists():
        print(f"Error: audit file not found: {args.audit_file}", file=sys.stderr)
        sys.exit(1)

    ok, msg = verify_chain(args.audit_file)
    print(f"{'✅' if ok else '❌'} Chain integrity: {msg}")
    if not ok:
        sys.exit(1)

    if args.public_key:
        valid, total = verify_ed25519_signatures(args.audit_file, args.public_key)
        if total > 0:
            print(f"{'✅' if valid == total else '⚠️'} Ed25519 signatures: {valid}/{total} valid")
        else:
            print("ℹ️  No Ed25519-signed entries found")

    if args.merkle_proof:
        if not Path(args.merkle_proof).exists():
            print(f"Error: proof file not found: {args.merkle_proof}", file=sys.stderr)
            sys.exit(1)
        ok, msg = verify_merkle_proof_file(args.merkle_proof)
        print(f"{'✅' if ok else '❌'} Merkle proof: {msg}")
        if not ok:
            sys.exit(1)

    print("\nVerification complete.")


if __name__ == "__main__":
    main()

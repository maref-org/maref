#!/usr/bin/env python3
"""Migrate v0.37.0 HMAC-signed audit logs to v0.38.0+ Ed25519 signatures.

Usage:
    python scripts/migrate_audit_hmac_to_ed25519.py \\
        --input audit_v037.jsonl --output audit_v038.jsonl \\
        --ed25519-key ./keys/maref_ed25519.pem

The script reads each HMAC-signed entry, verifies it (if the HMAC key is
available), then re-signs it with Ed25519 and appends it to the output file.

Entries without HMAC signatures are preserved as-is (unsigned).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from pathlib import Path


def load_ed25519_keypair(pem_path: str):
    """Load an Ed25519 key pair from a private key PEM file."""
    try:
        from maref.crypto.ed25519_keys import Ed25519KeyPair
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from maref.crypto.ed25519_keys import Ed25519KeyPair

    return Ed25519KeyPair.from_private_key_file(pem_path)


def migrate_entry(entry: dict, keypair, hmac_key: bytes | None = None) -> dict:
    """Re-sign an entry with Ed25519, verifying HMAC first if possible."""
    new_entry = dict(entry)

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
    ).encode("utf-8")

    old_hmac = entry.get("hmac_signature", "")
    if old_hmac and hmac_key:
        expected = hmac.new(hmac_key, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, old_hmac):
            print(f"  ⚠️  HMAC mismatch for entry {entry.get('id', '?')}", file=sys.stderr)

    sig = keypair.sign(payload)
    new_entry["ed25519_signature"] = sig.hex()
    new_entry["signer_fingerprint"] = keypair.fingerprint
    new_entry.pop("hmac_signature", None)

    return new_entry


def main():
    parser = argparse.ArgumentParser(
        description="Migrate HMAC-signed audit logs to Ed25519"
    )
    parser.add_argument("--input", required=True, help="Input audit JSONL file (v0.37.0)")
    parser.add_argument("--output", required=True, help="Output audit JSONL file (v0.38.0+)")
    parser.add_argument(
        "--ed25519-key", required=True, help="Path to Ed25519 private key PEM file"
    )
    parser.add_argument(
        "--hmac-key",
        default=None,
        help="HMAC key for verifying old signatures (optional)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify old HMAC signatures before migrating",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    keypair = load_ed25519_keypair(args.ed25519_key)

    hmac_key_bytes = None
    if args.hmac_key:
        hmac_key_bytes = args.hmac_key.encode("utf-8")

    total = 0
    migrated = 0
    errors = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path) as fin, open(output_path, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                entry = json.loads(line)
                if entry.get("hmac_signature"):
                    new_entry = migrate_entry(entry, keypair, hmac_key_bytes)
                    migrated += 1
                else:
                    new_entry = entry
                fout.write(json.dumps(new_entry, ensure_ascii=False) + "\n")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"  ❌ Error processing line {total}: {e}", file=sys.stderr)
                errors += 1

    print(f"\nDone: {total} entries processed, {migrated} migrated, {errors} errors")
    print(f"Output: {output_path}")
    print(f"Ed25519 fingerprint: {keypair.fingerprint}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Verify a hash-chained decision ledger without the runtime that wrote it.

Each line is ``{"prev_hash": ..., "body": {...}, "hash": ..., "signed": bool}``
and ``hash = sha256(canonical({"prev_hash": prev, "body": body}))``. The first
entry chains from 64 zeros. A tampered entry, a reordered line, or a broken
chain fails verification.

This verifier is deliberately independent of the runtime package: it only needs
the standard library, so the shipped artifacts stay checkable.

Usage:
    python3 prep/verify_ledger.py prep/runs/accessgate/attacks/ledger.jsonl
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

GENESIS = "0" * 64


def canonical(body: dict) -> bytes:
    return json.dumps(
        body, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def digest(prev_hash: str, body: dict) -> str:
    payload = canonical({"prev_hash": prev_hash, "body": body})
    return hashlib.sha256(payload).hexdigest()


def verify(path: Path) -> tuple[bool, int, str, str]:
    if not path.exists():
        return False, 0, "ledger not found", ""
    prev = GENESIS
    count = 0
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                prev_hash = entry["prev_hash"]
                body = entry["body"]
                stored = entry["hash"]
            except (json.JSONDecodeError, KeyError) as exc:
                return False, count, f"line {lineno}: malformed entry ({exc})", prev
            if prev_hash != prev:
                return False, count, f"line {lineno}: prev_hash mismatch", prev
            expected = digest(prev_hash, body)
            if stored != expected:
                return False, count, f"line {lineno}: hash mismatch", prev
            if entry.get("signed"):
                return False, count, f"line {lineno}: HMAC-signed ledger needs its key", prev
            prev = stored
            count += 1
    return True, count, "", prev


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: verify_ledger.py <ledger.jsonl>", file=sys.stderr)
        return 2
    ok, count, error, head = verify(Path(argv[0]))
    if ok:
        print(f"OK {count} entries, head {head[:16]}")
        return 0
    print(f"BROKEN after {count} entries: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

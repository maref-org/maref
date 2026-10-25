#!/usr/bin/env python3
"""Quarantine a legacy audit chain without deleting or rewriting bytes.

Moves an unmaintained audit file into an archive directory, writes a manifest
with the source/archive SHA-256 and a verification summary, appends an entry
to an append-only ledger, and records a signed ``audit_chain_quarantine``
event on the live governance chain.

The quarantined file is expected to fail full verification. Check it with::

    python3 scripts/verify_audit_chain.py --audit-file <archive> --expect-failed

Usage:
    python3 scripts/quarantine_audit_chain.py --dry-run \\
        --reason "legacy state-machine chain, no writers since 2026-10-23"
    python3 scripts/quarantine_audit_chain.py --apply --reason "..."

Exit codes: 0 = done/dry-run ok, 1 = verification or tooling failure,
2 = missing key/config, 3 = file still held open.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from maref.governance.audit_chain_verify import (  # noqa: E402
    resolve_hmac_key,
    verify_audit_chain,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _line_count(path: Path) -> int:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def _open_pids(path: Path) -> list[str]:
    if shutil.which("lsof") is None:
        return []
    out = subprocess.run(
        ["lsof", "-t", str(path)], capture_output=True, text=True, check=False
    ).stdout
    return [pid for pid in out.split() if pid.strip()]


def _summary(report) -> dict:
    return {
        "total": report.total,
        "formats": report.formats,
        "integrity_intact": report.integrity_intact,
        "link_break_count": len(report.link_breaks),
        "hash_invalid_count": len(report.hash_invalid),
        "signature_invalid_count": len(report.signature_invalid),
        "signature_unverifiable_count": len(set(report.signature_unverifiable)),
        "tampered_count": getattr(report, "tampered_count", None),
        "key_status": report.key_status,
        "first_previous_hash": report.first_previous_hash,
        "last_chain_hash": report.last_chain_hash,
        "notes": report.notes,
    }


def _record_live_event(manifest: dict, manifest_path: Path, hmac_key) -> str | None:
    from maref.governance.audit import AuditLogger

    try:
        logger = AuditLogger(
            log_path=_REPO_ROOT / ".governance" / "governance_audit.jsonl",
            hmac_key=hmac_key,
        )
        logger.log(
            event_type="audit_chain_quarantine",
            actor=os.environ.get("USER", "unknown"),
            action="quarantine",
            details=manifest["reason"],
            metadata={
                "archive_path": manifest["archive_path"],
                "archive_sha256": manifest["archive_sha256"],
                "source_sha256": manifest["source_sha256"],
                "line_count": manifest["line_count"],
                "link_break_count": manifest["verification"]["link_break_count"],
                "manifest": str(manifest_path),
                "manifest_sha256": _sha256_file(manifest_path),
            },
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator
        print(f"WARNING: live chain event not written: {exc}", file=sys.stderr)
        return None
    return "audit_chain_quarantine"


def main() -> int:
    parser = argparse.ArgumentParser(description="Quarantine a legacy audit chain")
    parser.add_argument(
        "--source",
        type=Path,
        default=_REPO_ROOT / ".governance" / "governance_audit_state_machine.jsonl",
    )
    parser.add_argument("--archive-dir", type=Path, default=None)
    parser.add_argument(
        "--suffix",
        default=f"pre-{time.strftime('%Y%m%d')}",
        help="Suffix inserted before the file extension",
    )
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true", help="Perform the move")
    parser.add_argument("--dry-run", action="store_true", help="Report only (default)")
    parser.add_argument("--force", action="store_true", help="Allow when the file is still open")
    parser.add_argument(
        "--no-record-event",
        action="store_true",
        help="Do not append a signed event to the live governance chain",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.is_file():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 1

    pids = _open_pids(source)
    if pids and not args.force:
        print(
            f"ERROR: source is open by PID(s) {', '.join(pids)}; stop writers or pass --force",
            file=sys.stderr,
        )
        return 3

    hmac_key = resolve_hmac_key(None)
    report = verify_audit_chain(source, hmac_key=hmac_key)
    summary = _summary(report)

    stamp = time.strftime("%Y%m%d")
    archive_dir = args.archive_dir or (
        _REPO_ROOT / ".governance" / "archive" / f"state-machine-quarantine-{stamp}"
    )
    archive_path = archive_dir / f"{source.stem}.{args.suffix}{source.suffix}"
    source_sha = _sha256_file(source)
    lines = _line_count(source)

    print(f"source      : {source}")
    print(f"records     : {report.total} (lines: {lines})")
    print(f"sha256      : {source_sha}")
    print(f"integrity   : {report.integrity_intact}")
    print(f"link breaks : {summary['link_break_count']}")
    print(f"hash bad    : {summary['hash_invalid_count']}")
    print(f"unverifiable: {summary['signature_unverifiable_count']}")
    print(f"key status  : {report.key_status}")
    print(f"archive     : {archive_path}")

    if args.dry_run or not args.apply:
        print("Dry-run: pass --apply to perform the quarantine.")
        return 0

    if archive_path.exists():
        print(f"ERROR: archive target already exists: {archive_path}", file=sys.stderr)
        return 1
    archive_dir.mkdir(parents=True, exist_ok=True)

    if not hmac_key:
        print(
            "ERROR: no HMAC key available; refusing to quarantine without "
            "recording a signed event.",
            file=sys.stderr,
        )
        return 2

    os.replace(source, archive_path)
    archive_sha = _sha256_file(archive_path)
    if archive_sha != source_sha:
        print(
            f"ERROR: archive SHA mismatch ({archive_sha} != {source_sha}); "
            f"file left at {archive_path}",
            file=sys.stderr,
        )
        return 1

    manifest = {
        "created_at": time.time(),
        "created_by": os.environ.get("USER", "unknown"),
        "reason": args.reason,
        "quarantined": True,
        "source_path": str(source),
        "source_sha256": source_sha,
        "archive_path": str(archive_path),
        "archive_sha256": archive_sha,
        "line_count": lines,
        "verification": summary,
    }
    manifest_path = archive_dir / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    ledger = _REPO_ROOT / ".governance" / "audit" / "archive" / "quarantine_events.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger_record = {
        "timestamp": time.time(),
        "actor": manifest["created_by"],
        "reason": args.reason,
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256_file(manifest_path),
        "source_sha256": source_sha,
        "archive_sha256": archive_sha,
        "line_count": lines,
    }
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ledger_record, ensure_ascii=False) + "\n")

    event = None
    if not args.no_record_event:
        event = _record_live_event(manifest, manifest_path, hmac_key)

    print(f"quarantined : {archive_path}")
    print(f"manifest    : {manifest_path}")
    print(f"ledger      : {ledger}")
    print(f"live event  : {event or 'not written'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

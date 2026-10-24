#!/usr/bin/env python3
"""Archive a forked governance audit log and start a new linear chain.

Historical audit logs contain forks caused by read-before-lock appends.
Those forks cannot be repaired without rewriting history, so this script:

1. verifies the existing log (link breaks, hash validity, key status);
2. archives the exact bytes (rename, never delete);
3. writes a signed manifest and a signed genesis ``chain_rebaseline`` record;
4. leaves the archive and manifest as the forensic record.

Default is dry-run. Use ``--apply`` to perform the migration.

Usage:
    python3 scripts/audit_chain_rebaseline.py
    python3 scripts/audit_chain_rebaseline.py --apply --reason "P0 fork repair"
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import json
import os
import shutil
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from maref.governance.audit_chain_verify import (  # noqa: E402
    resolve_hmac_keys,
    verify_audit_chain,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_files(path: Path) -> list[str]:
    """Return PIDs with the file open (best effort, macOS/Linux)."""
    if shutil.which("lsof") is None:
        return []
    import subprocess

    try:
        out = subprocess.run(
            ["lsof", "-t", str(path)], capture_output=True, text=True, check=False
        ).stdout
        return [pid for pid in out.split() if pid.strip()]
    except OSError:
        return []


def _canonical_payload(record: dict) -> str:
    payload = {
        "id": record["id"],
        "timestamp": record["timestamp"],
        "event_type": record["event_type"],
        "actor": record["actor"],
        "action": record["action"],
        "details": record["details"],
        "metadata": record.get("metadata", {}),
        "previous_hash": record.get("previous_hash", ""),
        "layer": "governance",
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _signed_genesis(reason: str, manifest: dict, key: bytes) -> dict:
    record = {
        "id": f"rebaseline_{int(time.time())}",
        "timestamp": time.time(),
        "event_type": "chain_rebaseline",
        "actor": os.environ.get("USER", "unknown"),
        "action": "archive_and_reset",
        "details": reason,
        "metadata": {
            "archived_file": manifest["archive_path"],
            "archive_sha256": manifest["archive_sha256"],
            "previous_source_sha256": manifest["source_sha256"],
            "link_breaks": manifest["verification"]["link_break_count"],
        },
        "previous_hash": "",
        "layer": "governance",
    }
    payload = _canonical_payload(record)
    record["hmac_signature"] = hmac.new(
        key, payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    record["signature_alg"] = "hmac-sha256"
    record["signer_backend"] = "local-hmac"
    record["chain_hash"] = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive and rebaseline audit chain")
    parser.add_argument(
        "--audit-file",
        default=str(_REPO_ROOT / ".governance" / "governance_audit.jsonl"),
    )
    parser.add_argument(
        "--archive-dir",
        default="",
        help="Defaults to <audit-file parent>/audit/archive",
    )
    parser.add_argument("--reason", default="audit chain fork remediation")
    parser.add_argument("--apply", action="store_true", help="Perform the migration")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow when the audit file is currently open by another process",
    )
    parser.add_argument("--hmac-key", default=None)
    args = parser.parse_args()

    audit_file = Path(args.audit_file)
    if not audit_file.exists():
        print(f"Error: audit file not found: {audit_file}", file=sys.stderr)
        return 1

    archive_dir = (
        Path(args.archive_dir) if args.archive_dir else audit_file.parent / "audit" / "archive"
    )
    report = verify_audit_chain(audit_file, hmac_key=args.hmac_key)
    keys = resolve_hmac_keys(args.hmac_key)

    print(f"audit file : {audit_file}")
    print(f"records    : {report.total}")
    print(f"formats    : {report.formats}")
    print(f"link breaks: {len(report.link_breaks)}")
    print(f"hash bad   : {len(report.hash_invalid)}")
    print(f"sig bad    : {len(report.signature_invalid)}")
    print(f"unverifiable: {len(set(report.signature_unverifiable))}")
    print(f"key status : {report.key_status}")
    print(f"archive dir: {archive_dir}")

    if not keys:
        print(
            "Error: no HMAC key available; refusing to write an unsigned genesis record.\n"
            "Set MAREF_HMAC_SECRET_KEY or pass --hmac-key.",
            file=sys.stderr,
        )
        return 2

    if len(report.link_breaks) == 0 and len(report.hash_invalid) == 0:
        print("Nothing to do: chain is already linear and hashes are valid.")
        return 0

    pids = _open_files(audit_file)
    if pids and not args.force:
        print(
            f"Error: audit file is open by PID(s) {', '.join(pids)}. "
            "Stop writers and retry, or pass --force.",
            file=sys.stderr,
        )
        return 3

    if not args.apply:
        print("Dry-run: pass --apply to archive and start a new chain.")
        return 0

    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"governance_audit_{stamp}.jsonl.gz"
    source_sha = _sha256_file(audit_file)
    with open(audit_file, encoding="utf-8", errors="replace") as fh:
        line_count = sum(1 for _ in fh)

    # Preserve exact content under compression before touching the live file.
    with open(audit_file, "rb") as src, gzip.GzipFile(
        filename=str(archive_path), mode="wb", mtime=0
    ) as dst:
        shutil.copyfileobj(src, dst)
    archive_sha = _sha256_file(archive_path)
    if _sha256_file(audit_file) != source_sha:
        print("Error: source changed during archive; aborting.", file=sys.stderr)
        archive_path.unlink(missing_ok=True)
        return 4

    manifest = {
        "created_at": time.time(),
        "created_by": os.environ.get("USER", "unknown"),
        "reason": args.reason,
        "source_path": str(audit_file),
        "source_sha256": source_sha,
        "archive_path": str(archive_path),
        "archive_sha256": archive_sha,
        "line_count": line_count,
        "verification": report.to_dict(),
    }
    manifest_path = archive_dir / f"rebaseline_manifest_{stamp}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    genesis = _signed_genesis(args.reason, manifest, keys[0])
    tmp = audit_file.with_suffix(".rebaseline.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(genesis, ensure_ascii=False, default=str) + "\n")
    os.replace(tmp, audit_file)

    # Separate, append-only migration ledger (not part of the chain).
    ledger = archive_dir / "rebaseline_events.jsonl"
    ledger_record = {
        "timestamp": time.time(),
        "actor": os.environ.get("USER", "unknown"),
        "reason": args.reason,
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256_file(manifest_path),
        "archive_sha256": archive_sha,
        "source_sha256": source_sha,
        "genesis_chain_hash": genesis["chain_hash"],
    }
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ledger_record, ensure_ascii=False) + "\n")

    print(f"Archived to: {archive_path}")
    print(f"Manifest   : {manifest_path}")
    print(f"New genesis: {genesis['chain_hash'][:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

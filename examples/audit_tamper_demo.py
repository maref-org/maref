#!/usr/bin/env python3
"""Create a signed audit log, verify it, tamper one entry, and verify again.

Run from the repository root:

    python examples/audit_tamper_demo.py

The script writes an intact log, a tampered copy, and the Ed25519 public key
to a temporary directory, then prints the exact CLI commands to verify both.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.governance.audit import AuditLogger


def _write_tampered_copy(source: Path, target: Path) -> None:
    shutil.copyfile(source, target)
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace("step 1", "step X", 1), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default="",
        help="Directory for demo artifacts (default: a new temp directory)",
    )
    args = parser.parse_args()

    out_dir = (
        Path(args.out_dir) if args.out_dir else Path(tempfile.mkdtemp(prefix="maref-audit-demo-"))
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    ok_path = out_dir / "audit-ok.jsonl"
    tampered_path = out_dir / "audit-tampered.jsonl"
    pub_path = out_dir / "signer.pub.pem"
    for path in (ok_path, tampered_path, pub_path):
        path.unlink(missing_ok=True)

    keypair = Ed25519KeyPair.generate()
    pub_path.write_text(keypair.public_key_pem, encoding="utf-8")

    logger = AuditLogger(log_path=ok_path, ed25519_keypair=keypair)
    for index in range(3):
        logger.log("demo", "agent-a", "tool_call", f"step {index}")

    before = logger.verify_integrity()
    _write_tampered_copy(ok_path, tampered_path)
    after_logger = AuditLogger(log_path=tampered_path, ed25519_keypair=keypair)
    after = after_logger.verify_integrity()

    print(f"intact log:    {ok_path}")
    print(f"tampered log:  {tampered_path}")
    print(f"public key:    {pub_path}")
    print(
        "before tamper: intact={} valid={}/{}".format(
            before["integrity_intact"],
            before["valid_signatures"],
            before["total_entries"],
        )
    )
    print(
        "after tamper:  intact={} valid={}/{} tampered={}".format(
            after["integrity_intact"],
            after["valid_signatures"],
            after["total_entries"],
            len(after["tampered_entries"]),
        )
    )
    print()
    print("Verify the intact log:")
    print(f"  maref audit verify -f {ok_path} -k {pub_path}")
    print("Verify the tampered log:")
    print(f"  maref audit verify -f {tampered_path} -k {pub_path}")

    expected = (
        before["integrity_intact"] is True
        and before["valid_signatures"] == before["total_entries"] == 3
        and after["integrity_intact"] is False
        and len(after["tampered_entries"]) == 1
    )
    return 0 if expected else 1


if __name__ == "__main__":
    sys.exit(main())

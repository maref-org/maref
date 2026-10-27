#!/usr/bin/env python3
"""Standalone audit-anchor verification.

Recomputes batch Merkle roots over the audit JSONL and compares them with
the externally stored anchor records. Detects deleted events, modified
payloads, and wholesale history rewrites (even when the audit hash chain
itself was recomputed).

Usage:
    python3 scripts/verify_audit_anchor.py --audit audit.jsonl --anchors anchors.jsonl
    python3 scripts/verify_audit_anchor.py --audit audit.jsonl --anchors anchors.jsonl --json

Exit code 0 means every anchored batch matches; 1 means verification failed.
Anchor files and TSA tokens are deployment-owned and must not be committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from maref.governance.audit_anchor import verify_anchors  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--audit", required=True, help="path to the audit JSONL file")
    parser.add_argument("--anchors", required=True, help="path to the anchors JSONL file")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    report = verify_anchors(args.audit, args.anchors)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        status = "OK" if report.ok else "FAILED"
        print(f"anchor verification {status}")
        print(f"  audit: {report.total_events} events, {report.uncovered_events} not anchored")
        print(f"  anchors: {report.anchor_count} batches, {report.anchored_events} events")
        for issue in report.issues:
            print(f"  - {issue}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

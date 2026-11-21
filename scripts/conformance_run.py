#!/usr/bin/env python3
"""Backwards-compatible entry point for the conformance suite.

The logic lives in :mod:`maref.conformance.cli` so that it ships inside the
wheel; this script stays for existing docs and CI invocations that expect
``python3 scripts/conformance_run.py ...``.

Examples::

    python3 scripts/conformance_run.py --demo good
    python3 scripts/conformance_run.py --trace trace.jsonl --out report.json --key "$KEY"
    python3 scripts/conformance_run.py --verify report.json --key "$KEY"
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from maref.conformance.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

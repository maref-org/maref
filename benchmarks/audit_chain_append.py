#!/usr/bin/env python3
"""MAREF Audit Chain Append Benchmark (O(n) → O(1) tail-read regression guard).

Measures AuditLogger.append cost on a pre-existing large chain file. The old
implementation called ``read_all(max_entries=None)`` on every append (O(n) per
write, O(n²) cumulative); the current implementation reads only the file tail
window (O(1) per write).

Reproduce:
  cd public/maref
  python benchmarks/audit_chain_append.py            # default: 2000 warmup + 500 timed appends
  python benchmarks/audit_chain_append.py --warmup 5000 --appends 1000

No external dependencies beyond the MAREF package itself.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from maref.governance.audit import AuditLogger


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit chain append benchmark")
    parser.add_argument("--warmup", type=int, default=2000, help="entries written before timing")
    parser.add_argument("--appends", type=int, default=500, help="timed append count")
    parser.add_argument("--rounds", type=int, default=3, help="measurement rounds (median taken)")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "audit.jsonl"
        logger = AuditLogger(log_path=path, hmac_key="bench")
        for i in range(args.warmup):
            logger.log(f"event_{i}", "actor", "action")

        size_kb = path.stat().st_size / 1024

        samples: list[float] = []
        for _ in range(args.rounds):
            # 每轮 fresh logger(文件尾读路径)；追加到同一文件使链持续增长，
            # 同时测更大链的 O(1) 稳定性。
            start = time.perf_counter()
            logger2 = AuditLogger(log_path=path, hmac_key="bench")
            for i in range(args.appends):
                logger2.log(f"new_{i}", "actor", "action")
            elapsed_ms = (time.perf_counter() - start) * 1000
            samples.append(elapsed_ms / args.appends * 1000)

        samples.sort()
        # 取中位数抗 CI 负载毛刺(单次毛刺可能虚高 10x+, 中位数稳健)。
        per_append_us = samples[len(samples) // 2]

        print(f"file size: {size_kb:.0f} KB")
        print(
            f"{args.appends} appends x {args.rounds} rounds: "
            f"{[f'{s:.1f}' for s in samples]} us/append, median={per_append_us:.1f} us"
        )

        # O(1) sanity gate: per-append cost must stay bounded (~sub-ms) regardless
        # of chain size. Old O(n) code on a 782KB / 2000-entry file took ~7.9ms
        # per append; O(1) tail read keeps it well under 1ms.
        if per_append_us > 1000:
            print(
                f"WARNING: append cost {per_append_us:.0f}us/append exceeds O(1) "
                f"budget — likely regression to full-file scan"
            )
            return 1
        print("OK: per-append cost within O(1) budget")
        return 0


if __name__ == "__main__":
    sys.exit(main())

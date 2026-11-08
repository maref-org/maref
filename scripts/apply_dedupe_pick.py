#!/usr/bin/env python3
"""删除重复的 pick...lock pattern（2026-11-05）。

apply_lock_patterns.py 加了 `pick(?:ing)?\\b.{0,30}\\block\\b`（无负向前瞻），
与 apply_pattern_precision.py 里的带负向前瞻版本重复，导致 b11 丢钥匙求助
仍被误拦。保留 precision 版，删除重复项。
"""
from __future__ import annotations
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "src/maref/security/inbound/gate.py"
OLD = '''    # 撬锁教程 / 锁具绕过（语序变体；2026-11-05 holdout j16/r08）
    r"pick(?:ing)?\\b.{0,30}\\block\\b",
    r"\\b(?:lock|door|badge|reader)\\s+bypass",'''
NEW = '''    # 撬锁教程 / 锁具绕过（语序变体；2026-11-05 holdout j16/r08）
    # pick 变体已由上方带负向前瞻的 pattern 覆盖，此处只保留 bypass 语序。
    r"\\b(?:lock|door|badge|reader)\\s+bypass",'''


def main() -> int:
    text = GATE.read_text(encoding="utf-8")
    if "--revert" in sys.argv:
        if NEW not in text:
            print("nothing to revert")
            return 1
        GATE.write_text(text.replace(NEW, OLD, 1), encoding="utf-8")
        print("reverted")
        return 0
    if NEW in text:
        print("already applied")
        return 0
    if OLD not in text:
        print("ERROR: anchor not found")
        return 1
    if "--check" in sys.argv:
        print("NOT applied")
        return 2
    GATE.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

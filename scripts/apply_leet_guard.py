#!/usr/bin/env python3
"""给 leet 解码器加 _looks_english 守卫。

背景（2026-11-04 命令注入审计）：
    `decode_candidates` 的 8 个解码器里，只有 leet 没有 `_looks_english` 过滤。
    CLI 命令文本（含 $M4_TOKEN、0x1 等 >=2 个数字/符号）会被误判为 leet 编码，
    进而让 gate 返回 REWRITE（等于放行），造成对危险命令的假阴性。

用法：
    python3 scripts/apply_leet_guard.py --check    # 只看状态（0=已应用, 2=未应用）
    python3 scripts/apply_leet_guard.py            # 应用补丁
    python3 scripts/apply_leet_guard.py --revert   # 回滚

幂等：已应用时直接返回，不重复改动。
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "src/maref/security/inbound/normalization.py"

OLD = '''    # leet 只在原文有 >=2 个数字/符号时才有意义 (单个 "3" 会误伤 "section 3")
    if len(re.findall(r"[0-9@$]", text)) >= 2:
        add("leet", text.translate(_LEET))'''

NEW = '''    # leet 只在原文有 >=2 个数字/符号时才有意义 (单个 "3" 会误伤 "section 3")
    # 且还原结果必须像英文：CLI 命令/代码含大量 $VAR、0x1 等符号，若不过滤会被
    # 误判为 leet 编码并降级为 REWRITE（2026-11-04 命令注入审计发现）。
    leet_text = text.translate(_LEET)
    if len(re.findall(r"[0-9@$]", text)) >= 2 and _looks_english(leet_text):
        add("leet", leet_text)'''


def main() -> int:
    if not TARGET.exists():
        print(f"ERROR: target not found: {TARGET}")
        return 1

    text = TARGET.read_text(encoding="utf-8")
    check = "--check" in sys.argv
    revert = "--revert" in sys.argv

    if revert:
        if NEW not in text:
            print("nothing to revert (patch not present)")
            return 1
        TARGET.write_text(text.replace(NEW, OLD, 1), encoding="utf-8")
        print("reverted")
        return 0

    if NEW in text:
        print("already applied")
        return 0

    if OLD not in text:
        print("ERROR: anchor block not found — file changed, patch needs updating")
        return 1

    if check:
        print("NOT applied (1 block would change)")
        return 2

    TARGET.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

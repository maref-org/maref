#!/usr/bin/env python3
"""口径 C：弱解码仅在"确实提升可读性"时 REWRITE，否则 ALLOW。

背景（2026-11-05 第 5 项口径讨论）：
    步骤 3 处理的是「弱方法（rot13/leet/键盘移位）解码出可读文本、但未命中任何
    deny pattern」的内容。原实现一律用 default_decision（默认 REWRITE），会把
    良性文本也改写；直接改成 ALLOW 又会让未被 deny 覆盖的编码内容原样进模型。

采用可读性增益判据（与 #533 的 leet 判据同一把尺子）：
    解码后常用词数 >= 原文 + 2  -> REWRITE（还原语义给下游）
    否则                        -> ALLOW（解码是噪音，不改写）

改动：
    1. 导入 _common_word_hits
    2. 步骤 3 按增益分流
    3. ReasonCode 新增 ALLOW_WEAK_DECODE；_infer_reason_code 增加两条映射

用法：
    python3 scripts/apply_weak_decode_criterion.py --check | --revert | (默认应用)
"""
from __future__ import annotations

import sys
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "src/maref/security/inbound/gate.py"

IMPORT_OLD = (
    "from maref.security.inbound.normalization import "
    "MAX_INPUT_CHARS, decode_candidates, looks_like_text"
)
IMPORT_NEW = (
    "from maref.security.inbound.normalization import (\n"
    "    MAX_INPUT_CHARS,\n"
    "    _common_word_hits,\n"
    "    decode_candidates,\n"
    "    looks_like_text,\n"
    ")"
)

STEP3_OLD = '''        # 3) 只有弱方法 (rot13/leet/键盘移位) 可读 → 默认处置
        weak = min(readable, key=lambda c: _METHOD_PRIORITY.get(c.method, 99))
        return self._verdict(
            self.default_decision,
            text,
            weak.text,
            (weak.method,),
            None,
            f"encoding detected via {weak.method}; no confident rewrite",
            started,
        )'''

STEP3_NEW = '''        # 3) 只有弱方法 (rot13/leet/键盘移位) 可读 →
        #    仅当解码确实提升可读性时还原给下游，否则视为噪音原样放行。
        #    （与 leet 的语义判据同一把尺子：常用词数至少 +2。）
        weak = min(readable, key=lambda c: _METHOD_PRIORITY.get(c.method, 99))
        src_words = _common_word_hits(text)
        dst_words = _common_word_hits(weak.text)
        if dst_words >= src_words + 2:
            return self._verdict(
                InboundDecision.REWRITE,
                text,
                weak.text,
                (weak.method,),
                None,
                f"weak decode improved readability via {weak.method}: "
                f"{src_words} -> {dst_words} words",
                started,
            )
        return self._verdict(
            InboundDecision.ALLOW,
            text,
            text,
            (),
            None,
            f"weak decode via {weak.method} did not improve readability "
            f"({src_words} -> {dst_words}); pass-through",
            started,
        )'''

ENUM_OLD = '''    REWRITE_WEAK = "REWRITE_WEAK"
    UNKNOWN = "UNKNOWN"'''
ENUM_NEW = '''    REWRITE_WEAK = "REWRITE_WEAK"
    ALLOW_WEAK_DECODE = "ALLOW_WEAK_DECODE"
    UNKNOWN = "UNKNOWN"'''

INFER_OLD = '''    if r.startswith("encoding detected via"):
        return ReasonCode.REWRITE_WEAK.value
    return ReasonCode.UNKNOWN.value'''
INFER_NEW = '''    if r.startswith("weak decode improved readability"):
        return ReasonCode.REWRITE_WEAK.value
    if r.startswith("weak decode via"):
        return ReasonCode.ALLOW_WEAK_DECODE.value
    if r.startswith("encoding detected via"):
        return ReasonCode.REWRITE_WEAK.value
    return ReasonCode.UNKNOWN.value'''

STRONG_OLD = """        "url",\n        "acrostic_rebuilt",\n    }\n)"""

STRONG_NEW = """        "url",
        "acrostic_rebuilt",
        "zero_width_stripped",
    }
)"""

PAIRS = [
    (IMPORT_OLD, IMPORT_NEW),
    (STEP3_OLD, STEP3_NEW),
    (ENUM_OLD, ENUM_NEW),
    (INFER_OLD, INFER_NEW),
    (STRONG_OLD, STRONG_NEW),
]


def main() -> int:
    if not GATE.exists():
        print(f"ERROR: target not found: {GATE}")
        return 1

    text = GATE.read_text(encoding="utf-8")
    check = "--check" in sys.argv
    revert = "--revert" in sys.argv

    if revert:
        changed = 0
        for old, new in PAIRS:
            if new in text:
                text = text.replace(new, old, 1)
                changed += 1
        GATE.write_text(text, encoding="utf-8")
        print(f"reverted {changed} block(s)")
        return 0

    pending = [i for i, (_, new) in enumerate(PAIRS) if new not in text]
    if not pending:
        print("already applied")
        return 0

    if check:
        print(f"NOT applied ({len(pending)} block(s) pending)")
        return 2

    for i, (old, new) in enumerate(PAIRS):
        if new in text:
            continue
        if old not in text:
            raise SystemExit(f"ERROR: anchor {i} not found — patch needs updating")
        text = text.replace(old, new, 1)

    GATE.write_text(text, encoding="utf-8")
    print(f"applied {len(pending)} block(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

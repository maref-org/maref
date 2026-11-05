#!/usr/bin/env python3
"""第 5 项（第一步）：给 InboundVerdict 加机器可读 reason_code。

背景（2026-11-05 命令注入审计）：
    reason 是英文自由文本，自动化断言只能做子串匹配；跨语言/改措辞即断。
    审计与告警路由需要稳定的枚举 code。

改动（集中在 _verdict 一处 + 一个推导函数，不改 10 个调用点）：
    1. 新增 ReasonCode 枚举
    2. InboundVerdict 新增 reason_code 字段（默认空，向后兼容）
    3. _verdict 统一用 _infer_reason_code(reason) 填充

用法：
    python3 scripts/apply_reason_codes.py --check | --revert | (默认应用)
"""
from __future__ import annotations

import sys
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "src/maref/security/inbound/gate.py"

ENUM_OLD = "class InboundDecision(str, Enum):"
ENUM_NEW = '''class ReasonCode(str, Enum):
    """裁决的机器可读理由码（稳定，不随文案变化）。"""

    ALLOW_EMPTY = "ALLOW_EMPTY"
    ALLOW_NO_ENCODING = "ALLOW_NO_ENCODING"
    ALLOW_NOT_READABLE = "ALLOW_NOT_READABLE"
    ALLOW_TOOL_CALL = "ALLOW_TOOL_CALL"
    DENY_PATTERN_RAW = "DENY_PATTERN_RAW"
    DENY_PATTERN_DECODED = "DENY_PATTERN_DECODED"
    DENY_DANGEROUS_COMMAND = "DENY_DANGEROUS_COMMAND"
    DENY_SENSITIVE_PATH = "DENY_SENSITIVE_PATH"
    REWRITE_STRONG = "REWRITE_STRONG"
    REWRITE_WEAK = "REWRITE_WEAK"
    UNKNOWN = "UNKNOWN"


class InboundDecision(str, Enum):'''

FIELD_OLD = '''    reason: str = ""
    elapsed_ms: float = 0.0
    input_digest: str = field(default="")'''
FIELD_NEW = '''    reason: str = ""
    reason_code: str = ""
    elapsed_ms: float = 0.0
    input_digest: str = field(default="")'''

INFER_ANCHOR = "def _digest(text: str) -> str:"
INFER_NEW = '''def _infer_reason_code(reason: str) -> str:
    """从 reason 文案推导稳定 code。文案措辞可改，code 不应变。"""
    r = reason.lower()
    if r.startswith("empty input"):
        return ReasonCode.ALLOW_EMPTY.value
    if r.startswith("no encoding detected"):
        return ReasonCode.ALLOW_NO_ENCODING.value
    if r.startswith("decoded candidates are not readable"):
        return ReasonCode.ALLOW_NOT_READABLE.value
    if r.startswith("tool_call: dangerous command"):
        return ReasonCode.DENY_PATTERN_RAW.value
    if r.startswith("tool_call: no dangerous command"):
        return ReasonCode.ALLOW_TOOL_CALL.value
    if r.startswith("dangerous command pattern"):
        return ReasonCode.DENY_DANGEROUS_COMMAND.value
    if r.startswith("sensitive path access"):
        return ReasonCode.DENY_SENSITIVE_PATH.value
    if r.startswith("deny pattern after"):
        return ReasonCode.DENY_PATTERN_DECODED.value
    if r.startswith("deny pattern on raw input"):
        return ReasonCode.DENY_PATTERN_RAW.value
    if r.startswith("rewritten via"):
        return ReasonCode.REWRITE_STRONG.value
    if r.startswith("encoding detected via"):
        return ReasonCode.REWRITE_WEAK.value
    return ReasonCode.UNKNOWN.value


def _digest(text: str) -> str:'''

VERDICT_OLD = '''            reason=reason,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),'''
VERDICT_NEW = '''            reason=reason,
            reason_code=_infer_reason_code(reason),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),'''

PAIRS = [
    (ENUM_OLD, ENUM_NEW),
    (FIELD_OLD, FIELD_NEW),
    (INFER_ANCHOR, INFER_NEW),
    (VERDICT_OLD, VERDICT_NEW),
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

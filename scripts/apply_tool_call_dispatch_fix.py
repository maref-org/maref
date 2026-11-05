#!/usr/bin/env python3
"""B1-fix：敏感路径不再无条件判危险。

问题（B1 应用后实测）：
    `_TOOL_DANGER` 直接含 `/etc/(shadow|passwd|sudoers)`，把正常安全讨论
    「How do I protect /etc/shadow?」「What is the purpose of /etc/passwd?」
    也判成 DENY。

修法：
    1. 从 `_TOOL_DANGER` 移除路径分支（保留管道/shell、rm -rf /、DROP TABLE、
       fork bomb —— 这些短语本身就是命令，不存在"正常讨论"歧义）
    2. 新增 `_SENSITIVE_PATH` + `_READ_VERB`
    3. 路径命中仅在「命令语法」或「读取动词」旁才 DENY

用法：
    python3 scripts/apply_tool_call_dispatch_fix.py --check | --revert | (默认应用)
"""
from __future__ import annotations

import sys
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "src/maref/security/inbound/gate.py"

DANGER_OLD = r'''_TOOL_DANGER = re.compile(
    r"\|\s*(?:sh|bash|zsh)\b"                       # curl ... | sh
    r"|\brm\s+-[a-z]*[rf][a-z]*\s+/(?:\s|$|\*)"     # rm -rf /
    r"|\b(?:drop|truncate)\s+table\b"                # SQL 破坏
    r"|/etc/(?:shadow|passwd|sudoers)\b"               # 敏感文件
    r"|:\(\)\s*\{.*\};\s*:",                       # fork bomb
    re.I,
)'''

DANGER_NEW = r'''_TOOL_DANGER = re.compile(
    r"\|\s*(?:sh|bash|zsh)\b"                       # curl ... | sh
    r"|\brm\s+-[a-z]*[rf][a-z]*\s+/(?:\s|$|\*)"     # rm -rf /
    r"|\b(?:drop|truncate)\s+table\b"                # SQL 破坏
    r"|:\(\)\s*\{.*\};\s*:",                       # fork bomb
    re.I,
)

# 敏感路径：单独出现是正常技术讨论，不能无条件判危险。
# 仅当伴随命令语法（--target/等）或读取动词时才视为访问意图。
_SENSITIVE_PATH = re.compile(r"/etc/(?:shadow|passwd|sudoers)\b|/root/\.ssh")
_READ_VERB = re.compile(
    r"\b(?:cat|read|dump|output|print|show|reveal|display|exfiltrate|send)\b",
    re.I,
)'''

DISPATCH_OLD = r'''        # 危险命令信号优先：命中即 DENY，与 kind 无关。
        # （rm -rf / 没有 --flag，不能靠 shell 语法判定；漏掉它等于放过。）
        m_danger = _TOOL_DANGER.search(text)
        if m_danger:
            return self._verdict(
                InboundDecision.DENY,
                text,
                text,
                (),
                m_danger.group(0),
                "dangerous command pattern",
                started,
            )
'''

DISPATCH_NEW = r'''        # 危险命令信号优先：命中即 DENY，与 kind 无关。
        # （rm -rf / 没有 --flag，不能靠 shell 语法判定；漏掉它等于放过。）
        m_danger = _TOOL_DANGER.search(text)
        if m_danger:
            return self._verdict(
                InboundDecision.DENY,
                text,
                text,
                (),
                m_danger.group(0),
                "dangerous command pattern",
                started,
            )

        # 敏感路径：仅在命令语法或读取动词旁才判访问意图（避免误伤技术讨论）。
        m_path = _SENSITIVE_PATH.search(text)
        if m_path and (_TOOL_CALL_SYNTAX.search(text) or _READ_VERB.search(text)):
            return self._verdict(
                InboundDecision.DENY,
                text,
                text,
                (),
                m_path.group(0),
                "sensitive path access in command context",
                started,
            )
'''

PAIRS = [(DANGER_OLD, DANGER_NEW), (DISPATCH_OLD, DISPATCH_NEW)]


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

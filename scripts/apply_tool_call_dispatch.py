#!/usr/bin/env python3
"""B1：tool_call / content 分流。

背景（2026-11-05 命令注入审计）：
    `check(text)` 把 CLI 命令文本与模型读取的内容一视同仁，先做编码解码。
    命令根本不会"被 base64 绕过"，却被 leet/base64 解码器反复误判（第 4 条
    `curl ... | sh` 曾返回 REWRITE）。且命令危险与否（管道到 shell、DROP TABLE、
    读 /etc/shadow）从未被检查 —— 那是编码层不该管的语义。

改动：
    1. 新增 `InputKind`（CONTENT / TOOL_CALL）
    2. `check(text, *, kind=None)`；None 时按 shell 语法启发式判定
    3. TOOL_CALL 路径：只做 deny pattern + 危险命令检查（DENY/ALLOW），
       不做编码解码（编码会话层的误判从根上消失）
    4. CONTENT 路径：逻辑不变

用法：
    python3 scripts/apply_tool_call_dispatch.py --check | --revert | (默认应用)
"""
from __future__ import annotations

import sys
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "src/maref/security/inbound/gate.py"

# --- 1. InputKind ---
KIND_OLD = "class InboundDecision(str, Enum):"
KIND_NEW = '''class InputKind(str, Enum):
    """输入来源：决定走哪条检查路径。

    CONTENT   — 模型读到的文本（用户消息、RAG 片段、网页），可能被编码混淆。
    TOOL_CALL — agent 工具调用（shell/SQL/HTTP 参数），不会被"编码绕过"，
                但可能有危险命令（管道到 shell、DROP TABLE、读敏感文件）。
    """

    CONTENT = "content"
    TOOL_CALL = "tool_call"


class InboundDecision(str, Enum):'''

# --- 2. 正则 ---
RE_OLD = '''# 这些方法产出的候选才视为"真实还原" (排除键盘移位等易误报项)'''
RE_NEW = '''# shell/CLI 语法特征：用于在未显式声明 kind 时判定为 TOOL_CALL。
# 只匹配强特征（flag/$VAR/管道到 shell/maref CLI），避免把普通文本里的 "--" 误判。
_TOOL_CALL_SYNTAX = re.compile(
    r"(?:^|\\s)--[A-Za-z][\\w-]*"
    r"|(?:^|\\s)\\$[A-Za-z_]\\w*"
    r"|\\|\\s*(?:sh|bash|zsh)\\b"
    r"|\\bmaref\\s+(?:invoke|audit)\\b"
)

# 命令上下文的危险信号（这些在编码层永远不会被识别为"危险"）。
_TOOL_DANGER = re.compile(
    r"\\|\\s*(?:sh|bash|zsh)\\b"                       # curl ... | sh
    r"|\\brm\\s+-[a-z]*[rf][a-z]*\\s+/(?:\\s|$|\\*)"     # rm -rf /
    r"|\\b(?:drop|truncate)\\s+table\\b"                # SQL 破坏
    r"|/etc/(?:shadow|passwd|sudoers)\\b"               # 敏感文件
    r"|:\\(\\)\\s*\\{.*\\};\\s*:",                       # fork bomb
    re.I,
)

# 这些方法产出的候选才视为"真实还原" (排除键盘移位等易误报项)'''

# --- 3. check 签名 + 分流 ---
CHECK_OLD = '''    def check(self, text: str) -> InboundVerdict:
        """对单条输入做裁决 (无副作用)。"""
        started = time.perf_counter()'''

CHECK_NEW = '''    def check(
        self, text: str, *, kind: InputKind | str | None = None
    ) -> InboundVerdict:
        """对单条输入做裁决 (无副作用)。

        kind: 输入类型。None 时按 shell 语法启发式判定（见 _TOOL_CALL_SYNTAX）。
              TOOL_CALL 走危险命令检查，不做编码解码。
        """
        started = time.perf_counter()'''

# --- 4. 分流体（插在 decode_candidates 之前）---
DISPATCH_OLD = "        candidates = decode_candidates(text, max_candidates=self.max_candidates)"
DISPATCH_NEW = '''        # 危险命令信号优先：命中即 DENY，与 kind 无关。
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

        if kind is None:
            kind = (
                InputKind.TOOL_CALL
                if _TOOL_CALL_SYNTAX.search(text)
                else InputKind.CONTENT
            )
        else:
            kind = InputKind(kind)

        if kind is InputKind.TOOL_CALL:
            # 命令上下文：不做编码解码（命令不会"被编码绕过"），只查 deny 词表。
            m_cmd = self._deny_re.search(text)
            return self._verdict(
                InboundDecision.DENY if m_cmd else InboundDecision.ALLOW,
                text,
                text,
                (),
                m_cmd.group(0) if m_cmd else None,
                "tool_call: dangerous command blocked"
                if m_cmd
                else "tool_call: no dangerous command",
                started,
            )

        candidates = decode_candidates(text, max_candidates=self.max_candidates)'''

PAIRS = [
    (KIND_OLD, KIND_NEW),
    (RE_OLD, RE_NEW),
    (CHECK_OLD, CHECK_NEW),
    (DISPATCH_OLD, DISPATCH_NEW),
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

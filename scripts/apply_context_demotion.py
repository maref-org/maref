#!/usr/bin/env python3
"""B3：deny pattern 命中一律 DENY；语境分类只记日志，不降级。

背景（2026-11-05 命令注入审计）：
    `_BENIGN_CONTEXT` 能把 deny 命中从 DENY 降为 HITL。软信号否决硬信号，
    使「Why does 'ignore previous instructions' work?」这类讨论、以及伪装成
    研究语境的真实注入，都退化为延迟放行。正确结构是：pattern 命中 -> DENY，
    语境分类只影响日志详级与告警路由。

    这是产品口径变更（原先刻意允许"讨论攻击"通过），非 bug fix。

改动：
    1. 模块 docstring：补齐 content/tool_call 两条路径的 fail 语义
    2. raw deny 分支：恒 DENY
    3. decoded deny 分支：恒 DENY
    4. 语境匹配仅追加日志后缀 "; benign context noted"

用法：
    python3 scripts/apply_context_demotion.py --check | --revert | (默认应用)
"""
from __future__ import annotations

import sys
from pathlib import Path

GATE = Path(__file__).resolve().parent.parent / "src/maref/security/inbound/gate.py"

DOC_OLD = """- 未命中一律 ALLOW (fail-open) — 因为它只是**加分项**, 不是唯一防线;
  真正的 fail-closed 由下游策略/模型/人工闸门承担"""

DOC_NEW = """- content 路径: 未命中一律 ALLOW (fail-open) — 它只是**加分项**, 不是唯一防线;
  真正的 fail-closed 由下游策略/模型/人工闸门承担
- tool_call 路径: 危险命令信号命中即 DENY (fail-closed)
- deny pattern 命中一律 DENY; 语境分类 (_BENIGN_CONTEXT) 只写日志, 不降级"""

RAW_OLD = '''        m_raw = self._deny_re.search(text)
        if m_raw:
            decision = (
                InboundDecision.HITL if _BENIGN_CONTEXT.search(text) else InboundDecision.DENY
            )
            return self._verdict(
                decision,
                text,
                text,
                ("raw",),
                m_raw.group(0),
                "deny pattern on raw input"
                + ("; benign context -> HITL" if decision is InboundDecision.HITL else ""),
                started,
            )'''

RAW_NEW = '''        m_raw = self._deny_re.search(text)
        if m_raw:
            # deny 命中恒 DENY；语境分类只进日志，不改变裁决。
            return self._verdict(
                InboundDecision.DENY,
                text,
                text,
                ("raw",),
                m_raw.group(0),
                "deny pattern on raw input"
                + ("; benign context noted" if _BENIGN_CONTEXT.search(text) else ""),
                started,
            )'''

DEC_OLD = """        for cand in decoded:
            m = self._deny_re.search(cand.text)
            if m:
                decision = (
                    InboundDecision.HITL
                    if _BENIGN_CONTEXT.search(cand.text)
                    else InboundDecision.DENY
                )
                reason = (
                    f"deny pattern after {cand.method} decode; benign context -> HITL"
                    if decision is InboundDecision.HITL
                    else f"deny pattern after {cand.method} decode"
                )
                return self._verdict(
                    decision, text, cand.text, (cand.method,), m.group(0), reason, started
                )"""

DEC_NEW = """        for cand in decoded:
            m = self._deny_re.search(cand.text)
            if m:
                # 同上：deny 命中恒 DENY，语境只记日志。
                reason = f"deny pattern after {cand.method} decode"
                if _BENIGN_CONTEXT.search(cand.text):
                    reason += "; benign context noted"
                return self._verdict(
                    InboundDecision.DENY,
                    text,
                    cand.text,
                    (cand.method,),
                    m.group(0),
                    reason,
                    started,
                )"""

PAIRS = [(DOC_OLD, DOC_NEW), (RAW_OLD, RAW_NEW), (DEC_OLD, DEC_NEW)]


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

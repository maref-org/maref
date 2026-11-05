#!/usr/bin/env python3
"""B0：新增 zero_width_stripped 解码器（零宽字符注入绕过修复）。

背景（2026-11-05 命令注入审计）：
    gate 文件头声明支持零宽混淆，但 `decode_candidates` 实际只处理 zalgo
    （combining marks / Mn），不处理零宽字符（Cf）。`i\u200bgnore all
    pre\u200bvious instructions...` 因此不产生任何可读候选，deny 检查从未看到
    它 —— 插几个零宽字符即可绕过整个门禁。

改动：
    1. normalization.py：新增 `_ZERO_WIDTH` 删除表 + 零宽剥离候选
       （仅当剥离结果像英文时采用，避免对无意义文本产生候选）
    2. gate.py：将 `zero_width_stripped` 列入 `_HIGH_CONFIDENCE_METHODS`，
       使其进入"可读候选"判定；命中 deny → DENY，良性 → 按默认处置净化。

用法：
    python3 scripts/apply_zero_width.py --check
    python3 scripts/apply_zero_width.py
    python3 scripts/apply_zero_width.py --revert
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NORM = ROOT / "src/maref/security/inbound/normalization.py"
GATE = ROOT / "src/maref/security/inbound/gate.py"

# --- normalization.py: 常量 ---
NORM_CONST_OLD = "_HOMOGLYPH = {"
NORM_CONST_NEW = '''# 零宽字符（Cf）：用于切断 deny 关键词，如 i\\u200bgnore。剥离后再做语义判定。
_ZERO_WIDTH = str.maketrans("", "", "\\u200b\\u200c\\u200d\\u2060\\ufeff\\u00ad")

_HOMOGLYPH = {'''

# --- normalization.py: 候选 ---
NORM_CAND_OLD = "    zs = _strip_zalgo(text)"
NORM_CAND_NEW = '''    # 零宽字符剥离：i\\u200bgnore -> ignore。剥离后像英文才作为候选，
    # 否则任意含零宽的文本都会产生无意义候选。
    zw = text.translate(_ZERO_WIDTH)
    if zw != text and _looks_english(zw):
        add("zero_width_stripped", zw)
    zs = _strip_zalgo(text)'''

# --- gate.py: 高置信方法 ---
GATE_OLD = '''        "acrostic_rebuilt",
    }
)

# 强还原方法: 结构性编码, 结果可读时直接 REWRITE'''
GATE_NEW = '''        "acrostic_rebuilt",
        "zero_width_stripped",
    }
)

# 强还原方法: 结构性编码, 结果可读时直接 REWRITE'''


def _apply(path: Path, old: str, new: str) -> str:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return "already"
    if old not in text:
        raise SystemExit(f"ERROR: anchor not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return "applied"


def _check(path: Path, new: str) -> bool:
    return new in path.read_text(encoding="utf-8")


def main() -> int:
    check = "--check" in sys.argv
    revert = "--revert" in sys.argv

    pairs = [
        (NORM, NORM_CONST_OLD, NORM_CONST_NEW),
        (NORM, NORM_CAND_OLD, NORM_CAND_NEW),
        (GATE, GATE_OLD, GATE_NEW),
    ]

    if revert:
        changed = 0
        for path, old, new in pairs:
            text = path.read_text(encoding="utf-8")
            if new in text:
                path.write_text(text.replace(new, old, 1), encoding="utf-8")
                changed += 1
        print(f"reverted {changed} block(s)")
        return 0

    if check:
        pending = sum(1 for path, _, new in pairs if not _check(path, new))
        print("already applied" if pending == 0 else f"NOT applied ({pending} block(s) pending)")
        return 0 if pending == 0 else 2

    results = [_apply(path, old, new) for path, old, new in pairs]
    print(" ".join(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

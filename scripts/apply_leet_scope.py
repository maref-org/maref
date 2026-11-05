#!/usr/bin/env python3
"""收窄 leet 触发条件：只认词内数字/符号，排除标识符与变量。

背景（2026-11-05 命令注入审计）：
    上一版用 `len(re.findall(r"[0-9@$]", text)) >= 2` 做裸计数。整条 CLI 命令
    只要含 `agent-demo-01`（0/1）或 `$M4_TOKEN`（4），就会被当成 leet 编码，
    令 gate 返回 REWRITE（等于放行），对危险命令形成假阴性。

修法：
    只统计"词内"数字/符号 —— 即前或后紧邻字母的 [0-9@$]。
      · `1gn0r3` 的 1/0/3  -> 命中（真实的词内替换）
      · `agent-demo-01`    -> 不命中（前是 -，后是字符串尾）
      · `$M4_TOKEN`        -> 不命中（4 前是 M 但后是 _，仅算 1 个）
      · `--flag`           -> 不命中
      · `1 2 3 4`          -> 不命中（前后是空格）

用法：
    python3 scripts/apply_leet_scope.py --check    # 0=已应用, 2=未应用
    python3 scripts/apply_leet_scope.py            # 应用
    python3 scripts/apply_leet_scope.py --revert   # 回滚
"""
from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "src/maref/security/inbound/normalization.py"

OLD = '''    # leet 只在原文有 >=2 个数字/符号时才有意义 (单个 "3" 会误伤 "section 3")
    # 且还原结果必须像英文：CLI 命令/代码含大量 $VAR、0x1 等符号，若不过滤会被
    # 误判为 leet 编码并降级为 REWRITE（2026-11-04 命令注入审计发现）。
    leet_text = text.translate(_LEET)
    if len(re.findall(r"[0-9@$]", text)) >= 2 and _looks_english(leet_text):
        add("leet", leet_text)'''

NEW = '''    # leet 只在"还原后确实变得更有英文语义"时才算编码（2026-11-05 命令注入
    # 审计）：裸计数会把含 agent-demo-01 / $M4_TOKEN / 0x1 的整条 CLI 命令误判
    # 为 leet 编码并返回 REWRITE（等于放行）。真 leet 文本（1gn0r3 4ll ...）
    # 解码后常用词显著增加；命令/标识符解码后语义不变，故用差值判据。
    leet_text = text.translate(_LEET)
    if (
        len(re.findall(r"[0-9@$]", text)) >= 2
        and _common_word_hits(leet_text) >= _common_word_hits(text) + 2
        and _looks_english(leet_text)
    ):
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

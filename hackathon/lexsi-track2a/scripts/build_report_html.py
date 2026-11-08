#!/usr/bin/env python3
"""把 report/REPORT.md 渲染为 report/REPORT.html（复用既有深色样式）。

用法: python scripts/build_report_html.py
"""
from __future__ import annotations

import markdown
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "report" / "REPORT.md"
OUT = ROOT / "report" / "REPORT.html"

HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>When Safety Is Semantic — Lexsi Track 2 report</title>
<style>
:root { --bg:#0f1115; --panel:#171a21; --ink:#e6e8ee; --muted:#9aa3b2; --line:#262b36; --accent:#d32e41; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif; }
main { max-width:860px; margin:0 auto; padding:56px 24px 90px; }
h1 { font-size:30px; line-height:1.28; margin:0 0 20px; letter-spacing:-.01em; }
h2 { font-size:20px; margin:42px 0 12px; padding-top:10px; border-top:1px solid var(--line); }
h3 { font-size:16px; margin:26px 0 8px; color:var(--muted); }
p { margin:0 0 13px; }
a { color:#7db2ff; text-decoration:none; } a:hover { text-decoration:underline; }
code { background:#12151c; border:1px solid var(--line); border-radius:5px; padding:1px 6px; font-size:13.5px; }
pre { background:#12151c; border:1px solid var(--line); border-radius:8px; padding:14px; overflow:auto; }
pre code { border:0; padding:0; }
table { width:100%; border-collapse:collapse; margin:14px 0; font-size:14.5px; }
th,td { text-align:left; padding:9px 11px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:600; border-bottom:1px solid #333a48; }
blockquote { margin:14px 0; padding:10px 14px; border-left:3px solid var(--accent); background:#161a22; color:#cfd5e0; }
hr { border:0; border-top:1px solid var(--line); margin:34px 0; }
ul,ol { padding-left:22px; } li { margin:5px 0; }
strong { color:#fff; }
footer { margin-top:48px; padding-top:18px; border-top:1px solid var(--line);
  color:var(--muted); font-size:13.5px; }
</style></head>
<body><main>
"""

FOOTER = """<footer>Source: <a href="https://github.com/maref-org/maref">maref-org/maref</a> ·
Dataset: <a href="https://huggingface.co/datasets/maref-org/lexsi-redteam-set">maref-org/lexsi-redteam-set</a></footer>
</main></body></html>
"""


def main() -> int:
    body = markdown.markdown(
        MD.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    OUT.write_text(HEAD + body + "\n" + FOOTER, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

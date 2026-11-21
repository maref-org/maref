"""AG-Conformance CLI — 随 wheel 一起发布的"尺子"入口。

历史（2026-11-21）：逻辑原本只存在于仓库的 ``scripts/conformance_run.py``，
``pip install maref`` 的用户既拿不到脚本，也拿不到 ``conformance/examples/``，
于是"10 分钟快速开始"实际只有 git clone 一条路。本模块把同一套逻辑移进包内，
``scripts/conformance_run.py`` 退化为薄壳，CLI 通过 ``maref conformance`` 暴露。

Exit codes: 0 = conformant / signature valid, 1 = non-conformant / invalid,
2 = usage or trace/report error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import (
    TraceError,
    build_trace,
    load_trace,
    render_markdown,
    run,
    sign_report,
    verify_report_dict,
)


def _write_trace(path: Path, trace: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False, sort_keys=True) for event in trace) + "\n",
        encoding="utf-8",
    )


def _verify(path: Path, key: str) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read report: {exc}", file=sys.stderr)
        return 2
    if not key:
        print("ERROR: --key (or MAREF_CONFORMANCE_KEY) is required for --verify", file=sys.stderr)
        return 2
    valid = verify_report_dict(payload, key)
    print(f"signature {'valid' if valid else 'INVALID'} for {path}")
    return 0 if valid else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="maref conformance", description="MAREF conformance v0.1")
    parser.add_argument("--trace", help="JSONL trace exported by the runtime under test")
    parser.add_argument("--demo", choices=["good", "bad"], help="run a built-in fixture")
    parser.add_argument("--export-trace", help="write the demo trace to this path")
    parser.add_argument("--out", help="write the JSON report to this path (default: stdout)")
    parser.add_argument("--md", help="write a Markdown report to this path")
    parser.add_argument("--key", default=os.environ.get("MAREF_CONFORMANCE_KEY", ""))
    parser.add_argument("--verify", help="verify a report JSON instead of running a trace")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.verify:
        return _verify(Path(args.verify), args.key)

    if bool(args.trace) == bool(args.demo):
        print("ERROR: provide exactly one of --trace or --demo", file=sys.stderr)
        return 2

    try:
        if args.demo:
            trace = build_trace(compliant=args.demo == "good")
            if args.export_trace:
                _write_trace(Path(args.export_trace), trace)
        else:
            trace = load_trace(Path(args.trace))
    except (OSError, TraceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    report = run(trace)
    if args.key:
        sign_report(report, args.key)

    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(render_markdown(report), encoding="utf-8")

    if not args.quiet:
        signed = "signed" if report.signature else "unsigned"
        print(
            f"VERDICT {report.verdict} | {report.passed} pass / {report.failed} fail "
            f"| score {report.score:.1%} | {signed}",
            file=sys.stderr,
        )
    return 0 if report.conformant else 1


if __name__ == "__main__":  # pragma: no cover - 便于 python -m maref.conformance.cli
    raise SystemExit(main())

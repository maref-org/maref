#!/usr/bin/env python3
"""Claim ledger: every public number must be reproducible by one command.

``claims.yaml`` is the single declaration surface.  Each entry names a
command, an extraction rule and an expectation.  ``--check`` executes the
commands and compares the observed values; ``--write`` regenerates the
human-readable table and machine-readable report.

Why this exists: the project's own 2026-11 audit found four different
versions advertised in README/``__init__``/``pyproject`` and a ``STATE.yaml``
that had been stale for three months.  Writing numbers by hand does not
scale past one person; executing them does.

Exit codes: 0 = all claims hold, 1 = drift, 2 = configuration/execution error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    print("ERROR: pyyaml is required (pip install pyyaml)", file=sys.stderr)
    raise SystemExit(2) from None

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CLAIMS = ROOT / "claims.yaml"
REPORT_PATH = ROOT / "claims.report.json"
DOCS_PATH = ROOT / "docs" / "claims.md"

PASS = "PASS"
FAIL = "FAIL"
ERROR = "ERROR"


@dataclass
class Claim:
    id: str
    statement: str
    command: list[str] | str
    extract: str | None = None
    expect: dict[str, Any] = field(default_factory=dict)
    timeout: int | None = None
    value: str | None = None
    status: str = PASS
    detail: str = ""

    @property
    def expectation(self) -> str:
        if "same_as" in self.expect:
            return f"same_as {self.expect['same_as']}"
        if "equals" in self.expect:
            return f"equals {self.expect['equals']}"
        if "min" in self.expect:
            return f">= {self.expect['min']}"
        if "regex" in self.expect:
            return f"regex {self.expect['regex']}"
        return "(none)"


def _load(path: Path) -> tuple[dict[str, Any], list[Claim]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("claims"), list):
        raise ValueError("claims.yaml must contain a top-level 'claims' list")
    claims: list[Claim] = []
    for raw in data["claims"]:
        if not isinstance(raw, dict) or "id" not in raw or "command" not in raw:
            raise ValueError(f"invalid claim entry: {raw!r}")
        claims.append(
            Claim(
                id=str(raw["id"]),
                statement=str(raw.get("statement", raw["id"])),
                command=raw["command"],
                extract=raw.get("extract"),
                expect=dict(raw.get("expect") or {}),
                timeout=int(raw["timeout"]) if raw.get("timeout") else None,
            )
        )
    return data, claims


def _argv(command: list[str] | str) -> list[str]:
    argv = shlex.split(command) if isinstance(command, str) else [str(part) for part in command]
    if argv and argv[0] in {"python", "python3"}:
        argv[0] = sys.executable
    return argv


def _run(claim: Claim, default_timeout: int) -> tuple[str | None, str]:
    try:
        proc = subprocess.run(
            _argv(claim.command),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=claim.timeout or default_timeout,
            check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"execution failed: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        return None, f"exit {proc.returncode}: {detail[-1] if detail else 'no output'}"
    text = proc.stdout.strip()
    if claim.extract:
        match = re.search(claim.extract, text, re.MULTILINE)
        if not match:
            return None, f"extract {claim.extract!r} did not match {text[:120]!r}"
        return (match.group(1) if match.groups() else match.group(0)).strip(), ""
    return (text.splitlines() or [""])[0].strip(), ""


def _check_expectation(claim: Claim, values: dict[str, str | None]) -> tuple[bool, str]:
    expect = claim.expect
    value = claim.value
    if "same_as" in expect:
        other = str(expect["same_as"])
        other_value = values.get(other)
        if other_value is None:
            return False, f"same_as target {other} has no value"
        return value == other_value, f"expected {other}={other_value!r}"
    if "equals" in expect:
        return value == str(expect["equals"]), f"expected {expect['equals']!r}"
    if "min" in expect:
        try:
            return float(value or "nan") >= float(expect["min"]), f"expected >= {expect['min']}"
        except (TypeError, ValueError):
            return False, f"expected numeric >= {expect['min']}"
    if "regex" in expect:
        return bool(re.search(str(expect["regex"]), value or "")), f"expected /{expect['regex']}/"
    known = {"same_as", "equals", "min", "regex"}
    unknown = sorted(set(expect) - known)
    return False, f"unknown expect keys: {unknown}"


def evaluate(claims: list[Claim], default_timeout: int) -> list[Claim]:
    values: dict[str, str | None] = {}
    for claim in claims:
        value, detail = _run(claim, default_timeout)
        claim.value = value
        values[claim.id] = value
        if value is None:
            claim.status = ERROR
            claim.detail = detail
        else:
            claim.status = PASS

    # Resolve same_as only after every raw value is known (order-independent).
    for claim in claims:
        if claim.status != PASS:
            continue
        ok, detail = _check_expectation(claim, values)
        if not ok:
            claim.status = FAIL
            claim.detail = detail
    return claims


def _summary(claims: list[Claim]) -> dict[str, int]:
    return {
        PASS: sum(1 for claim in claims if claim.status == PASS),
        FAIL: sum(1 for claim in claims if claim.status == FAIL),
        ERROR: sum(1 for claim in claims if claim.status == ERROR),
    }


def _print_table(claims: list[Claim]) -> None:
    width = max(len(claim.id) for claim in claims) + 2
    print(f"{'CLAIM':<{width}} {'VALUE':<28} {'STATUS':<6} EXPECTATION")
    for claim in claims:
        value = (claim.value or "-")[:26]
        print(f"{claim.id:<{width}} {value:<28} {claim.status:<6} {claim.expectation}")
        if claim.detail and claim.status != PASS:
            print(f"{'':<{width}} {'':<28}        {claim.detail}")
    summary = _summary(claims)
    print(
        f"\n{summary[PASS]} pass, {summary[FAIL]} fail, {summary[ERROR]} error "
        f"(total {len(claims)})"
    )


def _render_markdown(claims: list[Claim]) -> str:
    # 刻意不写生成时间：docs/claims.md 必须可由 `--write` 稳定复现，
    # 否则 `--write && git diff --exit-code` 这类漂移门禁永远无法成立。
    lines = [
        "<!-- generated by scripts/claims.py --write; do not edit by hand -->",
        "# 公开声称账本",
        "",
        "| 声称 | 值 | 期望 | 状态 |",
        "|---|---|---|---|",
    ]
    for claim in claims:
        value = (claim.value or "-").replace("|", "\\|")
        expectation = claim.expectation.replace("|", "\\|")
        lines.append(f"| `{claim.id}` | `{value}` | {expectation} | {claim.status} |")
    summary = _summary(claims)
    lines += [
        "",
        f"汇总：**{summary[PASS]} pass / {summary[FAIL]} fail / {summary[ERROR]} error**",
        "",
        "复算：`python scripts/claims.py --check`",
        "",
    ]
    return "\n".join(lines)


def _write_outputs(claims: list[Claim]) -> None:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary = _summary(claims)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "spec_version": 1,
                "generated_at": generated_at,
                "summary": summary,
                "claims": [
                    {
                        "id": claim.id,
                        "statement": claim.statement,
                        "value": claim.value,
                        "expectation": claim.expectation,
                        "status": claim.status,
                        "detail": claim.detail,
                    }
                    for claim in claims
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_PATH.write_text(_render_markdown(claims), encoding="utf-8")
    print(f"wrote {REPORT_PATH.relative_to(ROOT)} and {DOCS_PATH.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MAREF claim ledger")
    parser.add_argument("--file", default=str(DEFAULT_CLAIMS), help="path to claims.yaml")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify claims (default)")
    mode.add_argument("--write", action="store_true", help="regenerate docs/claims.md + report")
    mode.add_argument(
        "--check-docs",
        action="store_true",
        help="verify docs/claims.md matches the ledger (no writes; used by CI)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--only", action="append", default=[], help="run only these claim ids")
    args = parser.parse_args(argv)

    try:
        config, claims = _load(Path(args.file))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: cannot load claims file: {exc}", file=sys.stderr)
        return 2

    if args.only:
        wanted = set(args.only)
        # Pull in same_as targets so a filtered run still resolves cross-checks.
        by_id = {claim.id: claim for claim in claims}
        pending = list(wanted)
        while pending:
            current = pending.pop()
            claim = by_id.get(current)
            if claim and "same_as" in claim.expect:
                target = str(claim.expect["same_as"])
                if target not in wanted:
                    wanted.add(target)
                    pending.append(target)
        claims = [claim for claim in claims if claim.id in wanted]
        if not claims:
            print(f"ERROR: no claims matched {sorted(wanted)}", file=sys.stderr)
            return 2

    claims = evaluate(claims, int(config.get("timeout_seconds", 180)))

    if args.check_docs:
        expected = _render_markdown(claims)
        actual = DOCS_PATH.read_text(encoding="utf-8") if DOCS_PATH.exists() else ""
        if actual != expected:
            print(
                "ERROR: docs/claims.md is out of sync with claims.yaml "
                "(run: python scripts/claims.py --write)",
                file=sys.stderr,
            )
            return 1
        print("docs/claims.md in sync with claims.yaml")
        return 0

    if args.json:
        print(
            json.dumps(
                {
                    "summary": _summary(claims),
                    "claims": [
                        {
                            "id": claim.id,
                            "value": claim.value,
                            "status": claim.status,
                            "expectation": claim.expectation,
                            "detail": claim.detail,
                        }
                        for claim in claims
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_table(claims)

    if args.write:
        _write_outputs(claims)

    return 0 if all(claim.status == PASS for claim in claims) else 1


if __name__ == "__main__":
    raise SystemExit(main())

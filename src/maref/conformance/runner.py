"""Runner, report signing and verification for the conformance suite."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from .controls import evaluate_controls
from .types import Report, canonical_bytes, sha256_hex, utc_now


class TraceError(ValueError):
    """Raised when the input is not a valid conformance trace."""


def load_trace(source: str | Path | list[str]) -> list[dict[str, Any]]:
    """Load a JSONL trace from a path or an iterable of lines."""
    if isinstance(source, (str, Path)):
        text = Path(source).read_text(encoding="utf-8")
        lines = text.splitlines()
    else:
        lines = list(source)

    events: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TraceError(f"line {number}: invalid JSON: {exc}") from exc
        if not isinstance(event, dict):
            raise TraceError(f"line {number}: event must be a JSON object")
        events.append(event)

    if not events:
        raise TraceError("trace is empty")
    if events[0].get("type") != "manifest":
        raise TraceError("first event must be the manifest")
    if sum(1 for event in events if event.get("type") == "manifest") != 1:
        raise TraceError("trace must contain exactly one manifest")
    return events


def run(trace: list[dict[str, Any]], run_id: str | None = None) -> Report:
    """Evaluate all controls and build an unsigned report."""
    if not trace or trace[0].get("type") != "manifest":
        raise TraceError("trace must start with a manifest")
    manifest = trace[0]
    controls = evaluate_controls(trace, manifest)
    return Report(
        run_id=run_id or str(manifest.get("run_id") or sha256_hex(trace)[7:19]),
        controls=controls,
        generated_at=utc_now(),
        trace_sha256=sha256_hex(trace),
    )


def _signing_payload(report: Report) -> bytes:
    return canonical_bytes(report.to_dict(include_signature=False))


def sign_report(report: Report, key: str) -> Report:
    """Attach an HMAC-SHA256 signature over the canonical report payload."""
    if not key:
        raise ValueError("signing key must be non-empty")
    digest = hmac.new(key.encode("utf-8"), _signing_payload(report), hashlib.sha256).hexdigest()
    report.signature = {
        "alg": "hmac-sha256",
        "key_id": hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
        "value": digest,
    }
    return report


def verify_report(report: Report, key: str) -> bool:
    """Return True iff the report signature matches the supplied key."""
    return verify_report_dict(report.to_dict(), key)


def verify_report_dict(payload: dict[str, Any], key: str) -> bool:
    """Verify a report loaded from JSON (third-party verifier entry point)."""
    signature = payload.get("signature") or {}
    if signature.get("alg") != "hmac-sha256" or not signature.get("value"):
        return False
    body = {name: value for name, value in payload.items() if name != "signature"}
    expected = hmac.new(key.encode("utf-8"), canonical_bytes(body), hashlib.sha256).hexdigest()
    return hmac.compare_digest(str(signature["value"]), expected)


def render_markdown(report: Report) -> str:
    """Human-readable verdict, suitable for attaching to a ticket."""
    lines = [
        f"# Conformance report — {report.run_id}",
        "",
        f"- Spec: `{report.spec_version}`",
        f"- Generated: `{report.generated_at}`",
        f"- Trace: `{report.trace_sha256}`",
        f"- Verdict: **{report.verdict}** ({report.passed} pass / {report.failed} fail)",
        f"- Score: **{report.score:.1%}**",
        "",
        "| Control | Title | Status | Findings |",
        "|---|---|---|---|",
    ]
    for control in report.controls:
        detail = "; ".join(
            f"seq {finding.seq}: {finding.message}" if finding.seq else finding.message
            for finding in control.findings[:3]
        )
        lines.append(f"| `{control.id}` | {control.title} | {control.status.value} | {detail} |")
    if report.signature:
        lines += [
            "",
            f"Signature: `{report.signature['alg']}` key `{report.signature['key_id']}` "
            f"value `{report.signature['value']}`",
        ]
    else:
        lines += ["", "Signature: none (unsigned report)"]
    lines.append("")
    return "\n".join(lines)

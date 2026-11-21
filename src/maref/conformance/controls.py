"""The ten v0.1 conformance controls.

Each control is a pure function of the exported trace.  It never imports the
runtime under test: the only input is the JSONL evidence.  That is what makes
the result portable and third-party verifiable.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .types import ControlResult, Finding, Status, event_digest

HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DATA_CLASSES = {"public", "internal", "confidential", "restricted"}
DECISIONS = {"allow", "deny", "escalate"}
HIGH_RISK = {"high", "critical"}


@dataclass(frozen=True)
class Control:
    id: str
    title: str
    check: Callable[[list[dict[str, Any]], dict[str, Any]], list[Finding]]
    applies_to_tool_calls: bool = False


def _events(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in trace if event.get("type") != "manifest"]


def _tool_calls(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in _events(trace) if event.get("action") == "tool_call"]


def _result(control: Control, findings: list[Finding], applicable: bool) -> ControlResult:
    if not applicable:
        return ControlResult(control.id, control.title, Status.NA)
    return ControlResult(
        control.id,
        control.title,
        Status.FAIL if findings else Status.PASS,
        findings,
    )


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(HASH_RE.match(value))


def check_identity(trace: list[dict[str, Any]], manifest: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for event in _events(trace):
        seq = event.get("seq")
        identity = event.get("identity") or {}
        if not event.get("actor"):
            findings.append(Finding("missing actor", seq))
        if not identity.get("type"):
            findings.append(Finding("missing identity.type", seq))
        if not (identity.get("signature") or identity.get("key_id")):
            findings.append(Finding("missing identity signature/key_id", seq))
    return findings


def check_policy_bound(trace: list[dict[str, Any]], manifest: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for event in _tool_calls(trace):
        policy = event.get("policy") or {}
        if not policy.get("id"):
            findings.append(Finding("tool call has no policy.id", event.get("seq")))
        if not _is_hash(policy.get("hash")):
            findings.append(Finding("tool call has no valid policy.hash", event.get("seq")))
    return findings


def check_decision(trace: list[dict[str, Any]], manifest: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for event in _tool_calls(trace):
        decision = event.get("decision")
        if decision not in DECISIONS:
            findings.append(Finding(f"invalid decision {decision!r}", event.get("seq")))
        if decision in {"deny", "escalate"} and not event.get("reason"):
            findings.append(Finding(f"{decision} without reason", event.get("seq")))
    return findings


def check_least_privilege(trace: list[dict[str, Any]], manifest: dict[str, Any]) -> list[Finding]:
    allowed = set(manifest.get("allowed_tools") or [])
    findings: list[Finding] = []
    for event in _tool_calls(trace):
        if event.get("decision") == "allow" and event.get("tool") not in allowed:
            findings.append(
                Finding(f"allowed tool outside manifest: {event.get('tool')!r}", event.get("seq"))
            )
    return findings


def check_chain_link(trace: list[dict[str, Any]], manifest: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    previous = manifest.get("genesis_hash", "genesis")
    for event in _events(trace):
        if event.get("prev_hash") != previous:
            findings.append(
                Finding(f"prev_hash mismatch (expected {previous!r})", event.get("seq"))
            )
        if not _is_hash(event.get("hash")):
            findings.append(Finding("missing or malformed hash", event.get("seq")))
        previous = event.get("hash")
    return findings


def check_hash_integrity(trace: list[dict[str, Any]], manifest: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for event in _events(trace):
        if event.get("hash") != event_digest(event):
            findings.append(Finding("event digest does not match payload", event.get("seq")))
    return findings


def check_high_risk_approval(
    trace: list[dict[str, Any]], manifest: dict[str, Any]
) -> list[Finding]:
    findings: list[Finding] = []
    for event in _tool_calls(trace):
        if event.get("risk_level") not in HIGH_RISK:
            continue
        approval = event.get("approval") or {}
        if not approval.get("approver") or not approval.get("ts"):
            findings.append(Finding("high-risk action has no approval", event.get("seq")))
            continue
        if str(approval["ts"]) > str(event.get("ts")):
            findings.append(Finding("approval timestamp is after the action", event.get("seq")))
    return findings


def check_supply_chain(trace: list[dict[str, Any]], manifest: dict[str, Any]) -> list[Finding]:
    manifest_hash = manifest.get("tool_manifest_hash")
    findings: list[Finding] = []
    if not _is_hash(manifest_hash):
        findings.append(Finding("manifest.tool_manifest_hash is missing or malformed"))
    for event in _tool_calls(trace):
        if event.get("tool_manifest_hash") != manifest_hash:
            findings.append(
                Finding("tool call is not bound to the manifest hash", event.get("seq"))
            )
    return findings


def check_data_class(trace: list[dict[str, Any]], manifest: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for event in _tool_calls(trace):
        data_class = event.get("data_class")
        if data_class is not None and data_class not in DATA_CLASSES:
            findings.append(Finding(f"invalid data_class {data_class!r}", event.get("seq")))
        if event.get("external") and data_class not in DATA_CLASSES:
            findings.append(Finding("external call without a valid data_class", event.get("seq")))
    return findings


def _parse_ts(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def check_completeness(trace: list[dict[str, Any]], manifest: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    expected = 1
    for event in _events(trace):
        if event.get("seq") != expected:
            findings.append(Finding(f"sequence gap (expected {expected})", event.get("seq")))
        if not _parse_ts(event.get("ts")):
            findings.append(Finding("missing or invalid timestamp", event.get("seq")))
        expected += 1
    return findings


CONTROLS: tuple[Control, ...] = (
    Control("AG-01", "Agent identity present and signed", check_identity),
    Control("AG-02", "Every tool call is bound to a policy", check_policy_bound),
    Control("AG-03", "Explicit allow/deny/escalate decision", check_decision),
    Control("AG-04", "Least privilege against the tool manifest", check_least_privilege),
    Control("AG-05", "Hash chain linkage", check_chain_link),
    Control("AG-06", "Payload hash integrity", check_hash_integrity),
    Control("AG-07", "Human approval for high-risk actions", check_high_risk_approval),
    Control("AG-08", "Tool supply-chain binding", check_supply_chain),
    Control("AG-09", "Data classification for external calls", check_data_class),
    Control("AG-10", "Trace completeness (sequence + timestamps)", check_completeness),
)


def evaluate_controls(
    trace: list[dict[str, Any]],
    manifest: dict[str, Any],
    controls: Iterable[Control] = CONTROLS,
) -> list[ControlResult]:
    events = _events(trace)
    tool_calls = _tool_calls(trace)
    results: list[ControlResult] = []
    for control in controls:
        if not events:
            results.append(_result(control, [], applicable=False))
            continue
        if control.id in {"AG-02", "AG-03", "AG-04", "AG-07", "AG-08", "AG-09"} and not tool_calls:
            results.append(_result(control, [], applicable=False))
            continue
        results.append(_result(control, control.check(trace, manifest), applicable=True))
    return results

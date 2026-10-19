from __future__ import annotations

from pathlib import Path

import pytest

from sidecar.compliance import unified


@pytest.fixture()
def policy_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "phoenix_policy.yaml"
    path.write_text(
        """
version: 2
epoch: "2026-10-19"
rules:
  - name: deny-write
    match:
      tools: [write_file]
    decision: deny
    reason: write denied
  - name: deny-high
    match:
      risk: [high, critical]
    decision: deny
    reason: high denied
  - name: approve-multi
    match:
      multi_party: true
    decision: require_approval
    reason: need approval
  - name: deny-outside-prod
    match:
      tools: [danger_tool]
      scope_not_prefix: ["/prod/"]
    decision: deny
    reason: only outside prod
  - name: allow-read
    match:
      tools: [read_file]
      risk: [low, medium]
    decision: allow
    reason: read allowed
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MAREF_PHOENIX_POLICY", str(path))
    unified._POLICY_CACHE.clear()
    return path


def test_high_risk_missing_policy_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("MAREF_PHOENIX_POLICY", str(tmp_path / "missing.yaml"))
    unified._POLICY_CACHE.clear()
    decision = unified.check_if_governed("unknown_tool", risk="high")
    assert decision is not None
    assert decision.decision == "deny"


def test_low_risk_missing_policy_is_ungoverned(tmp_path, monkeypatch):
    monkeypatch.setenv("MAREF_PHOENIX_POLICY", str(tmp_path / "missing.yaml"))
    unified._POLICY_CACHE.clear()
    assert unified.check_if_governed("unknown_tool", risk="low") is None


def test_destructive_tool_denied(policy_file):
    decision = unified.check_if_governed("write_file", risk="low")
    assert decision is not None
    assert decision.decision == "deny"
    assert "write denied" in decision.reason
    assert decision.policy_version == "2"
    assert decision.policy_epoch == "2026-10-19"


def test_readonly_allowed(policy_file):
    decision = unified.check_if_governed("read_file", risk="low")
    assert decision is not None
    assert decision.decision == "allow"


def test_high_risk_beats_allow_rule(policy_file):
    decision = unified.check_if_governed("read_file", risk="high")
    assert decision is not None
    assert decision.decision == "deny"
    assert "high denied" in decision.reason


def test_multi_party_requires_approval(policy_file):
    decision = unified.check_if_governed("read_file", risk="low", multi_party=True)
    assert decision is not None
    assert decision.decision == "require_approval"


def test_invalid_yaml_fails_closed_for_high_risk(tmp_path, monkeypatch):
    path = tmp_path / "bad.yaml"
    path.write_text("rules: [unclosed", encoding="utf-8")
    monkeypatch.setenv("MAREF_PHOENIX_POLICY", str(path))
    unified._POLICY_CACHE.clear()
    decision = unified.check_if_governed("unknown_tool", risk="high")
    assert decision is not None
    assert decision.decision == "deny"


def test_unknown_low_risk_is_ungoverned(policy_file):
    assert unified.check_if_governed("unknown_tool", risk="low") is None


def test_scope_not_prefix_excludes_matching_scope(policy_file):
    assert unified.check_if_governed(
        "danger_tool", scope="/dev/agent", risk="low"
    ).decision == "deny"
    assert unified.check_if_governed("danger_tool", scope="/prod/agent", risk="low") is None

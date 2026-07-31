"""Tests for DestructiveOperationGate — default-on destructive operation gate."""

from __future__ import annotations

from typing import Any

import pytest

from maref.governance.destructive_gate import (
    DESTRUCTIVE_PATTERNS,
    DESTRUCTIVE_TOOL_NAMES,
    DestructiveOperationGate,
    GateDecision,
    GateVerdict,
)


@pytest.fixture
def signer() -> Any:
    from maref.crypto.ed25519_keys import Ed25519KeyPair
    return Ed25519KeyPair.generate()


class TestDestructiveOperationGate:
    def test_default_enabled(self) -> None:
        gate = DestructiveOperationGate()
        assert gate.enabled is True

    def test_evaluate_rm_blocked(self) -> None:
        gate = DestructiveOperationGate()
        d = gate.evaluate("delete_file", "shell", {"command": "rm -rf /"}, agent_id="agent-1")
        assert d.verdict == GateVerdict.BLOCK

    def test_evaluate_sql_drop_blocked(self) -> None:
        gate = DestructiveOperationGate()
        d = gate.evaluate("execute_sql", "run_query", {"query": "DROP TABLE users"}, agent_id="agent-1")
        assert d.verdict in (GateVerdict.BLOCK, GateVerdict.HITL_REQUIRED)

    def test_safe_operation_allowed(self) -> None:
        gate = DestructiveOperationGate()
        d = gate.evaluate("read_file", "read", {"path": "/tmp/test.txt"}, agent_id="agent-1")
        assert d.verdict == GateVerdict.ALLOW

    def test_gate_disabled_allows_all(self) -> None:
        gate = DestructiveOperationGate(enabled=False)
        d = gate.evaluate("delete_file", "shell", {"command": "rm -rf /"}, agent_id="agent-1")
        assert d.verdict == GateVerdict.ALLOW

    def test_shell_tool_high_risk(self) -> None:
        gate = DestructiveOperationGate()
        d = gate.evaluate("run", "shell", {"cmd": "ls"}, agent_id="agent-1")
        assert d.verdict == GateVerdict.BLOCK

    def test_hitl_threshold_triggers_hitl(self) -> None:
        gate = DestructiveOperationGate(hitl_threshold=0.3, block_above=0.9)
        d = gate.evaluate("write_file", "write", {"path": "/etc/config.yaml"}, agent_id="agent-1")
        assert d.verdict == GateVerdict.HITL_REQUIRED

    def test_confirm_hitl_allows(self) -> None:
        gate = DestructiveOperationGate(hitl_threshold=0.3, block_above=0.9)
        d = gate.evaluate("write_file", "write", {"path": "/etc/config.yaml"}, agent_id="agent-1")
        assert d.verdict == GateVerdict.HITL_REQUIRED
        gate.confirm_hitl(d, approved=True, approver_id="admin")
        assert d.verdict == GateVerdict.ALLOW
        assert d.hitl_approved is True

    def test_confirm_hitl_denies(self) -> None:
        gate = DestructiveOperationGate(hitl_threshold=0.3, block_above=0.9)
        d = gate.evaluate("write_file", "write", {"path": "/etc/config.yaml"}, agent_id="agent-1")
        gate.confirm_hitl(d, approved=False, approver_id="admin")
        assert d.verdict == GateVerdict.BLOCK
        assert d.hitl_approved is False

    def test_confirm_non_hitl_unchanged(self) -> None:
        gate = DestructiveOperationGate()
        d = gate.evaluate("read_file", "read", {"path": "/tmp/test.txt"}, agent_id="agent-1")
        gate.confirm_hitl(d, approved=True, approver_id="admin")
        assert d.verdict == GateVerdict.ALLOW  # unchanged

    def test_recent_decisions_empty_initially(self) -> None:
        gate = DestructiveOperationGate()
        assert gate.recent_decisions() == []

    def test_recent_decisions_returns_last_n(self) -> None:
        gate = DestructiveOperationGate()
        for i in range(5):
            gate.evaluate(f"op{i}", "tool", agent_id="agent-1")
        assert len(gate.recent_decisions(count=3)) == 3

    def test_recent_decisions_filtered(self) -> None:
        gate = DestructiveOperationGate()
        gate.evaluate("read_file", "read", {"path": "/tmp/x.txt"}, agent_id="agent-1")
        gate.evaluate("delete_file", "shell", {"command": "rm -rf /"}, agent_id="agent-1")
        blocked = gate.recent_decisions(verdict=GateVerdict.BLOCK)
        assert len(blocked) >= 1
        assert all(d.verdict == GateVerdict.BLOCK for d in blocked)

    def test_summary_structure(self) -> None:
        gate = DestructiveOperationGate()
        gate.evaluate("delete_file", "shell", {"command": "rm -rf /"}, agent_id="agent-1")
        gate.evaluate("read_file", "read", {"path": "/tmp/x.txt"}, agent_id="agent-1")
        s = gate.summary()
        assert s["enabled"] is True
        assert s["blocked"] >= 1
        assert s["allowed"] >= 1
        assert s["total_decisions"] == 2

    def test_severity_scoring_shell(self) -> None:
        gate = DestructiveOperationGate()
        d = gate.evaluate("execute", "bash", {"script": "echo hello"}, agent_id="agent-1")
        assert d.severity >= 0.9

    def test_severity_scoring_read(self) -> None:
        gate = DestructiveOperationGate()
        d = gate.evaluate("read_file", "read", {"path": "/tmp/test.txt"}, agent_id="agent-1")
        assert d.severity < 0.5


class TestGateDecisionEvidence:
    def test_evidence_message_deterministic(self) -> None:
        d1 = GateDecision(
            decision_id="gate-test",
            operation="test", tool_name="tool", verdict=GateVerdict.ALLOW,
            timestamp=1000.0,
        )
        d2 = GateDecision(
            decision_id="gate-test",
            operation="test", tool_name="tool", verdict=GateVerdict.ALLOW,
            timestamp=1000.0,
        )
        assert d1.evidence_message() == d2.evidence_message()

    def test_signed_when_signer_provided(self, signer: Any) -> None:
        gate = DestructiveOperationGate(signer=signer)
        d = gate.evaluate("delete_file", "shell", {"cmd": "rm -rf /"}, agent_id="agent-1")
        assert d.signature not in ("", "sign_error", "unsigned")

    def test_signature_verifiable(self, signer: Any) -> None:
        gate = DestructiveOperationGate(signer=signer)
        d = gate.evaluate("delete_file", "shell", {"cmd": "rm -rf /"}, agent_id="agent-1")
        assert d.verify_evidence(signer.public_key_pem) is True

    def test_signature_wrong_key_fails(self, signer: Any) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair
        gate = DestructiveOperationGate(signer=signer)
        d = gate.evaluate("delete_file", "shell", {"cmd": "rm -rf /"}, agent_id="agent-1")
        wrong_kp = Ed25519KeyPair.generate()
        assert d.verify_evidence(wrong_kp.public_key_pem) is False

    def test_unsigned_verify_returns_false(self) -> None:
        d = GateDecision(operation="test", tool_name="tool", verdict=GateVerdict.ALLOW)
        assert d.verify_evidence("") is False

    def test_to_dict_includes_signature(self, signer: Any) -> None:
        gate = DestructiveOperationGate(signer=signer)
        d = gate.evaluate("delete_file", "shell", agent_id="agent-1")
        dd = d.to_dict()
        assert "signature" in dd
        assert "signer_fingerprint" in dd
        assert dd["verdict"] == "BLOCK"

    def test_confirm_hitl_resigns(self, signer: Any) -> None:
        gate = DestructiveOperationGate(hitl_threshold=0.3, block_above=0.9, signer=signer)
        d = gate.evaluate("write_file", "write", {"path": "/etc/config.yaml"}, agent_id="agent-1")
        orig_sig = d.signature
        gate.confirm_hitl(d, approved=True, approver_id="admin")
        assert d.signature != orig_sig
        assert d.verify_evidence(signer.public_key_pem) is True


class TestDestructivePatterns:
    def test_known_patterns_loaded(self) -> None:
        assert len(DESTRUCTIVE_PATTERNS) > 0
        assert len(DESTRUCTIVE_TOOL_NAMES) > 0

    def test_rm_in_patterns(self) -> None:
        assert any("rm " in p for p in DESTRUCTIVE_PATTERNS)

    def test_drop_in_patterns(self) -> None:
        assert any("drop" in p.lower() for p in DESTRUCTIVE_PATTERNS)

    def test_delete_in_patterns(self) -> None:
        assert any("delete" in p.lower() for p in DESTRUCTIVE_PATTERNS)

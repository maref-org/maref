"""SemanticIntegrityGuard 单元测试 — A2A 语义完整性 (P2-11)."""

from __future__ import annotations

import pytest

from maref.integration.a2a_semantic_guard import (
    SemanticDecision,
    SemanticIntegrityGuard,
)


class TestSemanticCheck:
    def test_consistent_payload_allowed(self) -> None:
        guard = SemanticIntegrityGuard()
        decision = guard.check("read", "read the config file")
        assert decision.allowed is True

    def test_contradicting_payload_denied(self) -> None:
        guard = SemanticIntegrityGuard()
        decision = guard.check("read", "please DELETE FROM users")
        assert decision.allowed is False
        assert "delete" in decision.findings

    def test_exec_intent_detected(self) -> None:
        guard = SemanticIntegrityGuard()
        decision = guard.check("read", "then exec(rm -rf /)")
        assert decision.allowed is False
        assert "exec(" in decision.findings

    def test_unknown_action_has_no_policy(self) -> None:
        guard = SemanticIntegrityGuard()
        assert guard.check("custom.action", "anything").allowed is True

    def test_custom_markers(self) -> None:
        guard = SemanticIntegrityGuard(forbidden_markers={"read": ["transfer"]})
        assert guard.check("read", "transfer funds").allowed is False

    def test_decision_serializable(self) -> None:
        payload = SemanticDecision(False, "bad", ["x"]).to_dict()
        assert payload == {"allowed": False, "reason": "bad", "findings": ["x"]}


class TestCovertChannels:
    def test_unicode_stego_detected(self) -> None:
        guard = SemanticIntegrityGuard()
        findings = guard.detect_unicode_covert_channel("hello\u200bworld\u200c")
        assert findings
        assert all(finding.startswith("U+") for finding in findings)

    def test_clean_text_no_unicode_findings(self) -> None:
        assert SemanticIntegrityGuard().detect_unicode_covert_channel("plain text") == []

    def test_regular_intervals_flagged(self) -> None:
        guard = SemanticIntegrityGuard()
        assert guard.detect_timing_covert_channel([1.0, 1.0, 1.0, 1.0]) is True

    def test_irregular_intervals_not_flagged(self) -> None:
        guard = SemanticIntegrityGuard()
        assert guard.detect_timing_covert_channel([1.0, 5.0, 2.0, 9.0]) is False

    def test_too_few_intervals(self) -> None:
        assert SemanticIntegrityGuard().detect_timing_covert_channel([1.0, 1.0]) is False

    def test_invalid_threshold(self) -> None:
        with pytest.raises(ValueError):
            SemanticIntegrityGuard(timing_cv_threshold=-1.0)


class TestInspect:
    def test_inspect_combines_signals(self) -> None:
        guard = SemanticIntegrityGuard()
        result = guard.inspect("read", "read file", intervals=[1.0, 1.0, 1.0])
        assert result["semantic"]["allowed"] is True
        assert result["timing_covert"] is True
        assert result["allowed"] is False  # covert channel blocks

    def test_inspect_clean(self) -> None:
        guard = SemanticIntegrityGuard()
        result = guard.inspect("read", "read file")
        assert result["allowed"] is True
        assert result["unicode_covert"] == []
        assert result["timing_covert"] is False

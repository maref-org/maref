"""Tests for Protocol E: grounding triangulation (v0.51 W5-S2 / E2).

Protocol E verifies an assertion against its retrieved evidence and the
evidence's declared source using the GroundingVerifier, without requiring a
gateway adapter.
"""

from __future__ import annotations

from maref.integration.percv.verification_bridge import VerificationBridge


def _bridge() -> VerificationBridge:
    return VerificationBridge()  # Protocol E 不依赖 gateway


def test_protocol_e_supported_assertion() -> None:
    bridge = _bridge()
    result = bridge.run_protocol_e(
        assertion="customer count increased by 12%",
        evidence=["Customer count rose 12% in Q2"],
        source="q2_analytics_report",
    )
    assert result.protocol == "E"
    assert result.passed
    assert result.confidence >= 0.7
    assert result.details["source"] == "q2_analytics_report"


def test_protocol_e_contradicted_assertion() -> None:
    bridge = _bridge()
    result = bridge.run_protocol_e(
        assertion="revenue doubled last quarter",
        evidence=["Revenue was flat last quarter"],
        source="quarterly_report",
    )
    assert result.protocol == "E"
    assert not result.passed
    assert result.confidence < 0.5


def test_protocol_e_unverifiable_no_evidence() -> None:
    bridge = _bridge()
    result = bridge.run_protocol_e(
        assertion="unverifiable claim",
        evidence=[],
        source="",
    )
    assert not result.passed
    assert result.confidence == 0.0
    assert "no evidence" in (result.error or "").lower()


def test_protocol_e_records_history() -> None:
    bridge = _bridge()
    bridge.run_protocol_e(
        assertion="alpha is live",
        evidence=["The alpha channel is now live"],
        source="release_notes",
    )
    assert len(bridge.history) == 1
    assert bridge.history[0].protocol == "E"


def test_protocol_e_source_captured_in_details() -> None:
    bridge = _bridge()
    result = bridge.run_protocol_e(
        assertion="alpha is live",
        evidence=["The alpha channel is now live"],
        source="release_notes",
    )
    assert result.details["evidence_count"] == 1
    assert result.details["support_level"] == "supported"

from __future__ import annotations

from maref.immunity.intent_drift_detector import IntentDriftDetector
from maref.recursive.safety_gate_v2 import SafetyGateV2

HAPPY_CODE = """
def login(username, password):
    if username is None or password is None:
        return {"error": "empty"}
    if len(password) < 8:
        return {"error": "too short"}
    try:
        result = authenticate(username, password)
        return result
    except AuthenticationError:
        return {"error": "auth_failed"}
"""


class TestIntentDriftSentinel:
    def test_intent_drift_blocks_on_hash_change(self) -> None:
        gate = SafetyGateV2()
        detector = IntentDriftDetector()
        detector.attach_safety_gate(gate)

        criteria = detector._extractor.extract_ac("实现用户登录功能")
        initial_audit_count = len(gate.safety_audit_trail())

        result = detector.evaluate_code(
            code=HAPPY_CODE,
            criteria=criteria,
            expected_hash="deadbeef" * 8,
        )

        assert result.intent_valid is False
        assert result.blocked is True

        audit_trail = gate.safety_audit_trail()
        assert len(audit_trail) == initial_audit_count + 1
        block_entry = audit_trail[-1]
        assert block_entry["direction"] == "block"
        assert "intent_drift" in block_entry["value"]

    def test_intent_drift_no_block_when_valid(self) -> None:
        gate = SafetyGateV2()
        detector = IntentDriftDetector()
        detector.attach_safety_gate(gate)

        criteria = detector._extractor.extract_ac("实现用户登录功能")
        ih = detector._extractor.compute_intent_hash(criteria)
        initial_audit_count = len(gate.safety_audit_trail())

        result = detector.evaluate_code(
            code=HAPPY_CODE,
            criteria=criteria,
            expected_hash=ih.hash_value,
        )

        assert result.intent_valid is True
        assert result.blocked is False

        assert len(gate.safety_audit_trail()) == initial_audit_count

    def test_intent_drift_without_gate_still_blocks(self) -> None:
        detector = IntentDriftDetector()
        criteria = detector._extractor.extract_ac("实现用户登录功能")

        result = detector.evaluate_code(
            code=HAPPY_CODE,
            criteria=criteria,
            expected_hash="deadbeef" * 8,
        )

        assert result.blocked is True
        assert result.intent_valid is False

    def test_block_returns_true(self) -> None:
        gate = SafetyGateV2()
        assert gate.block("test_reason") is True
        assert len(gate.safety_audit_trail()) == 1

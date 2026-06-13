from __future__ import annotations

import pytest

from maref.immunity.ai_stench_detector import AIStenchDetector, StenchWarning


COMMENT_REPETITION_CODE = """
def get_user_by_id(user_id):
    \"\"\"Get user by id\"\"\"
    return query(User).filter(User.id == user_id).first()

def process_data(input_data):
    \"\"\"Process data\"\"\"
    return input_data.strip()
"""

ERROR_STENCIL_CODE = """
def handle_errors():
    try:
        step_one()
    except ValueError as e:
        logger.error(f"Error in step one: {e}")
        raise
    try:
        step_two()
    except KeyError as e:
        logger.error(f"Error in step two: {e}")
        raise
    try:
        step_three()
    except TypeError as e:
        logger.error(f"Error in step three: {e}")
        raise
"""

MISSING_BOUNDARY_CODE = """
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
"""

GOOD_CODE = """
def get_user(user_id):
    \"\"\"Retrieve user record with team membership eager-loaded.
       Raises NotFound if user doesn't exist.\"\"\"
    if user_id is None:
        raise ValueError("user_id required")
    try:
        return db.query(User).filter(User.id == user_id).one()
    except NotFound:
        raise

def calculate_discount(items):
    \"\"\"Apply tiered discount based on order total.
       Returns 0 for empty orders.\"\"\"
    if not items:
        return 0.0
    if any(item.price < 0 for item in items):
        raise ValueError("Negative price")
    total = sum(item.price for item in items)
    if total < 0:
        raise OverflowError("Overflow")
    return total * 0.9 if total > 100 else total
"""


class TestAIStenchDetector:
    """M3.1: AI Stench Detector."""

    def test_comment_repetition_detected(self):
        detector = AIStenchDetector()
        warnings = detector.scan(COMMENT_REPETITION_CODE)
        cr = [w for w in warnings if w.type == "comment_repetition"]
        assert len(cr) >= 2

    def test_comment_repetition_severity_warning(self):
        detector = AIStenchDetector()
        warnings = detector.scan(COMMENT_REPETITION_CODE)
        cr = [w for w in warnings if w.type == "comment_repetition"]
        assert all(w.severity == "WARNING" for w in cr)

    def test_error_handler_stencil_detected(self):
        detector = AIStenchDetector()
        warnings = detector.scan(ERROR_STENCIL_CODE)
        es = [w for w in warnings if w.type == "error_handler_stencil"]
        assert len(es) >= 1

    def test_error_handler_stencil_severity_warning(self):
        detector = AIStenchDetector()
        warnings = detector.scan(ERROR_STENCIL_CODE)
        es = [w for w in warnings if w.type == "error_handler_stencil"]
        assert all(w.severity == "WARNING" for w in es)

    def test_missing_boundary_detected(self):
        detector = AIStenchDetector()
        warnings = detector.scan(MISSING_BOUNDARY_CODE)
        mb = [w for w in warnings if w.type == "missing_boundary_check"]
        assert len(mb) >= 1

    def test_missing_boundary_is_hard_block(self):
        detector = AIStenchDetector()
        warnings = detector.scan(MISSING_BOUNDARY_CODE)
        mb = [w for w in warnings if w.type == "missing_boundary_check"]
        assert all(w.severity == "HARD_BLOCK" for w in mb)

    def test_good_code_no_false_positives(self):
        detector = AIStenchDetector()
        warnings = detector.scan(GOOD_CODE)
        assert len(warnings) == 0

    def test_syntax_error_returns_empty(self):
        detector = AIStenchDetector()
        warnings = detector.scan("def broken( ")
        assert len(warnings) == 0

    def test_empty_code_returns_empty(self):
        detector = AIStenchDetector()
        warnings = detector.scan("")
        assert len(warnings) == 0

    def test_stench_warning_has_suggestion(self):
        detector = AIStenchDetector()
        warnings = detector.scan(COMMENT_REPETITION_CODE)
        for w in warnings:
            assert w.suggestion

    def test_missing_boundary_mentions_function_name(self):
        detector = AIStenchDetector()
        warnings = detector.scan(MISSING_BOUNDARY_CODE)
        mb = [w for w in warnings if w.type == "missing_boundary_check"]
        assert any("multiply" in w.function_name for w in mb)

    def test_safety_gate_integration(self):
        from maref.recursive.safety_gate_v2 import SafetyGateV2

        gate = SafetyGateV2()
        detector = AIStenchDetector()
        gate.attach_stench_detector(detector)

        result = gate.detect_ai_stench(COMMENT_REPETITION_CODE)
        assert result.threat_detected is False

        result2 = gate.detect_ai_stench(MISSING_BOUNDARY_CODE)
        assert result2.threat_detected is True
        assert result2.blocked is True

    def test_safety_gate_no_detector_returns_clean(self):
        from maref.recursive.safety_gate_v2 import SafetyGateV2

        gate = SafetyGateV2()
        result = gate.detect_ai_stench("any code")
        assert result.threat_detected is False

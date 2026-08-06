"""Tests for TLA+ StenoDetectionComplete theorem (THEOREM 6).

Verifies that TLATheoremVerifier.verify_steno_detection_complete() correctly
judges clean vs. steganography-laden output, and that verify_all() includes
the new theorem in its result dictionary.

Covers:
- Clean ASCII text passes (no stego markers)
- Claude stego marker (U+02B9) fails with default INIT state
- Stego text passes when state machine is in HALT
- Zero-width chars (U+200B) detected
- verify_all() includes StenoDetectionComplete entry
- verify_all() with stego output marks StenoDetectionComplete as failed
"""

from __future__ import annotations

from maref.governance.state_machine import GovernanceStateMachine
from maref.integration.test_platform import (
    EvaluationReport,
    MASAgentCard,
    TestMode,
    TLATheoremVerifier,
)


class TestStenoDetectionTheorem:
    def test_clean_text_passes(self) -> None:
        """清洁 ASCII 文本 → passed=True, counterexample=None."""
        result = TLATheoremVerifier.verify_steno_detection_complete("Hello, normal message.")
        assert result.passed is True
        assert result.theorem_name == "StenoDetectionComplete"
        assert result.counterexample is None

    def test_stego_text_with_claude_marker_fails(self) -> None:
        """含 U+02B9 + 默认 INIT state → passed=False, counterexample 非空."""
        result = TLATheoremVerifier.verify_steno_detection_complete("hello\u02b9world")
        assert result.passed is False
        assert result.counterexample is not None
        assert result.counterexample["expected_state"] == "HALT"
        assert result.counterexample["actual_state"] == "INIT"

    def test_stego_text_with_halt_state_passes(self) -> None:
        """含 stego + state_machine 在 HALT → passed=True."""
        fsm = GovernanceStateMachine()
        fsm.force_halt(reason="test")
        result = TLATheoremVerifier.verify_steno_detection_complete(
            "hello\u02b9world", state_machine=fsm
        )
        assert result.passed is True
        assert result.counterexample is None

    def test_zero_width_chars_detected(self) -> None:
        """含 U+200B → passed=False."""
        result = TLATheoremVerifier.verify_steno_detection_complete("a\u200bb")
        assert result.passed is False
        assert result.counterexample is not None

    def test_verify_all_includes_steno_theorem(self) -> None:
        """verify_all 返回的字典包含 StenoDetectionComplete 条目，清洁文本通过."""
        card = MASAgentCard(
            agent_id="a1",
            agent_name="A",
            data_residency="US",
            model_backend_location="US",
            cross_border=False,
        )
        report = EvaluationReport(
            report_id="r1",
            agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=85.0,
        )
        results = TLATheoremVerifier.verify_all(card, report, output_text="clean text")
        assert "StenoDetectionComplete" in results
        assert results["StenoDetectionComplete"].passed is True

    def test_verify_all_with_stego_output(self) -> None:
        """verify_all 含 stego 输出时 StenoDetectionComplete 失败."""
        card = MASAgentCard(
            agent_id="a1",
            agent_name="A",
            data_residency="US",
            model_backend_location="US",
            cross_border=False,
        )
        report = EvaluationReport(
            report_id="r1",
            agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=85.0,
        )
        results = TLATheoremVerifier.verify_all(card, report, output_text="evil\u02b9")
        assert results["StenoDetectionComplete"].passed is False


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])

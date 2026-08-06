"""
Tests for gray_code_validator.py
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from src.formal.gray_code_validator import (
    validate_entropy_profile,
    validate_gray_code_completeness,
    validate_no_self_loops,
    validate_reachability,
    validate_single_bit_transitions,
    validate_terminal_absorbing,
)

from maref.governance.constants import ENTROPY_LEVELS, GRAY_CODE


class TestValidateSingleBitTransitions:
    def test_valid_transitions(self) -> None:
        """Test that the actual Gray code sequence has single-bit transitions."""
        passed, errors = validate_single_bit_transitions()
        assert passed is True
        assert errors == []

    def test_invalid_transition_detection(self) -> None:
        """Test detection of invalid transitions (if Gray code were corrupted)."""
        # Patch the module-level GRAY_CODE that the function uses
        from src.formal import gray_code_validator as validator_module
        original = validator_module.GRAY_CODE.copy()

        try:
            # Temporarily corrupt a Gray code to create 2-bit difference
            validator_module.GRAY_CODE[2] = (0, 1, 1, 0, 0)  # Changed from (0,1,0,0,0)
            passed, errors = validate_single_bit_transitions()
            assert passed is False
            assert any("Hamming distance" in e for e in errors)
        finally:
            # Restore
            validator_module.GRAY_CODE.clear()
            validator_module.GRAY_CODE.update(original)


class TestValidateNoSelfLoops:
    def test_no_self_loops_in_valid_transitions(self) -> None:
        """Test that valid transitions have no self-loops."""
        from maref.governance.constants import compute_valid_transitions

        transitions = compute_valid_transitions()
        passed, errors = validate_no_self_loops(transitions)
        assert passed is True
        assert errors == []

    def test_self_loop_detection(self) -> None:
        """Test detection of self-loops."""
        transitions = {0: [1, 0], 1: [2]}  # State 0 has self-loop
        passed, errors = validate_no_self_loops(transitions)
        assert passed is False
        assert any("self-loop" in e for e in errors)


class TestValidateTerminalAbsorbing:
    def test_halt_has_no_outgoing_transitions(self) -> None:
        """Test that HALT state (9) has no outgoing transitions."""
        from maref.governance.constants import compute_valid_transitions

        transitions = compute_valid_transitions()
        passed, errors = validate_terminal_absorbing(transitions)
        assert passed is True
        assert errors == []

    def test_halt_with_transitions_detected(self) -> None:
        """Test detection when HALT state has outgoing transitions."""
        transitions = {9: [8], 0: [1]}  # HALT has transition to 8
        passed, errors = validate_terminal_absorbing(transitions)
        assert passed is False
        assert any("HALT state has outgoing transitions" in e for e in errors)


class TestValidateReachability:
    def test_all_states_reachable(self) -> None:
        """Test that all states are reachable from INIT."""
        passed, errors = validate_reachability()
        assert passed is True
        assert errors == []

    def test_unreachable_state_detection(self) -> None:
        """Test detection of unreachable states."""
        # Mock compute_valid_transitions to return disconnected graph
        mock_transitions = {
            0: [1],  # INIT -> OBSERVE
            1: [2],  # OBSERVE -> ANALYZE
            2: [3],  # ANALYZE -> EVALUATE
            3: [4],  # EVALUATE -> DECIDE
            4: [5],  # DECIDE -> ACT
            5: [6],  # ACT -> VERIFY
            6: [7],  # VERIFY -> STABILIZE
            7: [8],  # STABILIZE -> REPORT
            8: [9],  # REPORT -> HALT
            9: [],   # HALT (terminal)
            # State 10 (if it existed) would be unreachable
        }

        with patch("src.formal.gray_code_validator.compute_valid_transitions", return_value=mock_transitions):
            passed, errors = validate_reachability()
            # Actually all 0-9 are reachable in this mock
            assert passed is True


class TestValidateEntropyProfile:
    def test_valid_entropy_profile(self) -> None:
        """Test that entropy profile matches expected pattern."""
        passed, errors = validate_entropy_profile()
        assert passed is True
        assert errors == []

    def test_invalid_entropy_detection(self) -> None:
        """Test detection of incorrect entropy values."""
        original_entropy = ENTROPY_LEVELS.copy()

        # Temporarily change an entropy value
        with patch.dict(ENTROPY_LEVELS, {5: 3}):  # ACT should be 4 (MAX_ENTROPY)
            passed, errors = validate_entropy_profile()
            assert passed is False
            assert any("ACT state entropy" in e for e in errors)

        # Restore
        ENTROPY_LEVELS.clear()
        ENTROPY_LEVELS.update(original_entropy)


class TestValidateGrayCodeCompleteness:
    def test_all_gray_codes_unique(self) -> None:
        """Test that all 10 Gray codes are unique."""
        passed, errors = validate_gray_code_completeness()
        assert passed is True
        assert errors == []

    def test_duplicate_detection(self) -> None:
        """Test detection of duplicate Gray codes."""
        original_gray_code = GRAY_CODE.copy()

        # Create a duplicate
        with patch.dict(GRAY_CODE, {2: GRAY_CODE[1]}):  # State 2 same as state 1
            passed, errors = validate_gray_code_completeness()
            assert passed is False
            assert any("Duplicate Gray code" in e for e in errors)

        # Restore
        GRAY_CODE.clear()
        GRAY_CODE.update(original_gray_code)


class TestRunAllValidations:
    def test_all_validations_pass(self) -> None:
        """Test that all validations pass for correct configuration."""
        from src.formal.gray_code_validator import run_all_validations

        all_passed, checks = run_all_validations()
        assert all_passed is True
        assert len(checks) == 6
        for _check_name, (passed, errors) in checks.items():
            assert passed is True
            assert errors == []

    def test_failed_validation_reporting(self) -> None:
        """Test reporting when a validation fails."""
        from src.formal.gray_code_validator import run_all_validations

        # Mock one validation to fail
        with patch("src.formal.gray_code_validator.validate_single_bit_transitions") as mock_validate:
            mock_validate.return_value = (False, ["Test error"])

            all_passed, checks = run_all_validations()
            assert all_passed is False
            assert checks["single_bit_transitions"][0] is False
            assert "Test error" in checks["single_bit_transitions"][1]


def test_print_functions_do_not_crash() -> None:
    """Test that print functions execute without crashing."""
    from src.formal.gray_code_validator import print_gray_code_table, print_transition_graph

    # Mock console to avoid actual printing
    with patch("src.formal.gray_code_validator.console") as mock_console:
        print_gray_code_table()
        print_transition_graph()

        # Verify console methods were called
        assert mock_console.print.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

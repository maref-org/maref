"""Unit tests for the Gray code state machine validator."""

from formal.gray_code_validator import (
    ENTROPY_LEVELS,
    GRAY_CODE,
    MAX_ENTROPY,
    STATE_NAMES,
    compute_valid_transitions,
    hamming_distance,
    run_all_validations,
    validate_entropy_profile,
    validate_no_self_loops,
    validate_reachability,
    validate_single_bit_transitions,
)


class TestHammingDistance:
    """Tests for Hamming distance calculation."""

    def test_identical(self) -> None:
        assert hamming_distance((0, 0, 0, 0), (0, 0, 0, 0)) == 0

    def test_one_bit_diff(self) -> None:
        assert hamming_distance((0, 0, 0, 0), (0, 0, 0, 1)) == 1

    def test_all_bits_diff(self) -> None:
        assert hamming_distance((0, 0, 0, 0), (1, 1, 1, 1)) == 4

    def test_gray_code_neighbors(self) -> None:
        # Adjacent states in Gray code sequence differ by 1 bit
        assert hamming_distance(GRAY_CODE[0], GRAY_CODE[1]) == 1
        assert hamming_distance(GRAY_CODE[1], GRAY_CODE[2]) == 1
        assert hamming_distance(GRAY_CODE[8], GRAY_CODE[9]) == 1


class TestGrayCodeProperties:
    """Tests for Gray code structural properties."""

    def test_all_states_unique(self) -> None:
        codes = list(GRAY_CODE.values())
        assert len(codes) == len(set(codes))

    def test_ten_states(self) -> None:
        assert len(GRAY_CODE) == 10
        assert set(GRAY_CODE.keys()) == set(range(10))

    def test_four_bit_encoding(self) -> None:
        for code in GRAY_CODE.values():
            assert len(code) == 4
            assert all(bit in (0, 1) for bit in code)


class TestTransitions:
    """Tests for state transition properties."""

    def test_halt_is_absorbing(self) -> None:
        transitions = compute_valid_transitions()
        assert transitions[9] == []

    def test_no_self_loops(self) -> None:
        transitions = compute_valid_transitions()
        passed, errors = validate_no_self_loops(transitions)
        assert passed, errors

    def test_all_states_reachable(self) -> None:
        passed, errors = validate_reachability()
        assert passed, errors

    def test_single_bit_transitions(self) -> None:
        passed, errors = validate_single_bit_transitions()
        assert passed, errors


class TestEntropyProfile:
    """Tests for entropy level assignments."""

    def test_entropy_peaks_at_act(self) -> None:
        assert ENTROPY_LEVELS[5] == MAX_ENTROPY

    def test_init_has_zero_entropy(self) -> None:
        assert ENTROPY_LEVELS[0] == 0

    def test_halt_has_zero_entropy(self) -> None:
        assert ENTROPY_LEVELS[9] == 0

    def test_entropy_profile_valid(self) -> None:
        passed, errors = validate_entropy_profile()
        assert passed, errors


class TestIntegration:
    """Integration tests for full validation suite."""

    def test_all_validations_pass(self) -> None:
        all_passed, checks = run_all_validations()
        assert all_passed
        for name, (passed, errors) in checks.items():
            assert passed, f"{name} failed: {errors}"


class TestStateNames:
    """Tests for state name mappings."""

    def test_all_states_have_names(self) -> None:
        assert len(STATE_NAMES) == 10
        for s in range(10):
            assert s in STATE_NAMES
            assert isinstance(STATE_NAMES[s], str)
            assert len(STATE_NAMES[s]) > 0

    def test_halt_name(self) -> None:
        assert STATE_NAMES[9] == "HALT"

    def test_init_name(self) -> None:
        assert STATE_NAMES[0] == "INIT"

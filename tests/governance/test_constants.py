"""
Governance Constants 测试

覆盖审计问题 P18：Gray code 编码正确性、Hamming distance、有效转换、HALT 状态无出边。
"""

from __future__ import annotations

import pytest

from maref.governance.constants import (
    GRAY_CODE,
    STATE_NAMES,
    ENTROPY_LEVELS,
    MAX_ENTROPY,
    hamming_distance,
    compute_valid_transitions,
)


class TestGrayCode:
    def test_gray_code_length(self) -> None:
        assert len(GRAY_CODE) == 10

    def test_gray_code_bit_length(self) -> None:
        for state, bits in GRAY_CODE.items():
            assert len(bits) == 4
            assert all(b in (0, 1) for b in bits)

    def test_gray_code_consecutive_differs_by_one_bit(self) -> None:
        """Gray code 特性：相邻状态只有一位不同。"""
        for i in range(len(GRAY_CODE) - 1):
            dist = hamming_distance(GRAY_CODE[i], GRAY_CODE[i + 1])
            assert dist == 1, f"States {i} and {i+1} differ by {dist} bits"

    def test_state_names_coverage(self) -> None:
        assert len(STATE_NAMES) == 10
        assert STATE_NAMES[0] == "INIT"
        assert STATE_NAMES[9] == "HALT"

    def test_entropy_levels(self) -> None:
        assert ENTROPY_LEVELS[0] == 0  # INIT
        assert ENTROPY_LEVELS[5] == 4  # ACT (max)
        assert ENTROPY_LEVELS[9] == 0  # HALT

    def test_max_entropy(self) -> None:
        assert MAX_ENTROPY == 4
        assert all(v <= MAX_ENTROPY for v in ENTROPY_LEVELS.values())


class TestHammingDistance:
    def test_same_tuple(self) -> None:
        assert hamming_distance((0, 0, 0, 0), (0, 0, 0, 0)) == 0

    def test_one_bit_diff(self) -> None:
        assert hamming_distance((0, 0, 0, 0), (0, 0, 0, 1)) == 1

    def test_all_bits_diff(self) -> None:
        assert hamming_distance((0, 0, 0, 0), (1, 1, 1, 1)) == 4

    def test_different_lengths(self) -> None:
        assert hamming_distance((0, 0), (0, 0, 0)) == 0  # zip stops at shortest


class TestValidTransitions:
    def test_halt_no_outgoing(self) -> None:
        transitions = compute_valid_transitions()
        assert transitions[9] == []

    def test_init_has_outgoing(self) -> None:
        transitions = compute_valid_transitions()
        assert len(transitions[0]) > 0

    def test_all_transitions_single_bit(self) -> None:
        transitions = compute_valid_transitions()
        for state, targets in transitions.items():
            for target in targets:
                dist = hamming_distance(GRAY_CODE[state], GRAY_CODE[target])
                assert dist == 1, f"Transition {state}->{target} has Hamming distance {dist}"

    def test_transitions_are_symmetric_except_halt(self) -> None:
        transitions = compute_valid_transitions()
        for state, targets in transitions.items():
            if state == 9:  # HALT has no outgoing edges
                continue
            for target in targets:
                if target != 9:  # HALT is absorbing
                    assert state in transitions[target], f"Transition {state}->{target} not symmetric"

    def test_no_self_loops(self) -> None:
        transitions = compute_valid_transitions()
        for state, targets in transitions.items():
            assert state not in targets

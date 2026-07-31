from __future__ import annotations

from maref_lite._constants import (
    ENTROPY_LEVELS,
    GRAY_CODE,
    MAX_ENTROPY,
    STATE_NAMES,
    VALID_TRANSITIONS,
    compute_valid_transitions,
    hamming_distance,
)
from maref_lite._constants import __all__ as constants_all


def _states() -> set[str]:
    return set(STATE_NAMES)


class TestLiteModelSelfConsistency:
    """Lite 8 态模型（INIT..HALT）常量自洽性验证。

    maref_lite 是独立的 8 态精简 FSM（非完整版 10 态模型的重导出），
    因此不要求与 maref.governance.constants 数值相等，只验证内部一致。
    """

    def test_entropy_levels_cover_all_states(self):
        assert set(ENTROPY_LEVELS.keys()) == _states()

    def test_max_entropy_matches_entropy_levels(self):
        assert MAX_ENTROPY == max(ENTROPY_LEVELS.values())
        assert MAX_ENTROPY > 0

    def test_entropy_forms_mountain_curve(self):
        order = [ENTROPY_LEVELS[s] for s in STATE_NAMES]
        assert order[0] == 0  # INIT
        assert order[-1] == 0  # HALT
        peak = max(order)
        assert peak == MAX_ENTROPY

    def test_gray_code_covers_all_states(self):
        assert set(GRAY_CODE.keys()) == _states()
        assert len(set(GRAY_CODE.values())) == len(GRAY_CODE)  # 编码互异

    def test_gray_code_single_bit_adjacency(self):
        order = STATE_NAMES
        for i in range(len(order) - 1):
            assert hamming_distance(GRAY_CODE[order[i]], GRAY_CODE[order[i + 1]]) == 1

    def test_valid_transitions_cover_all_states(self):
        assert set(VALID_TRANSITIONS.keys()) == _states()
        for targets in VALID_TRANSITIONS.values():
            for t in targets:
                assert t in _states()

    def test_halt_is_terminal(self):
        assert VALID_TRANSITIONS["HALT"] == []

    def test_compute_valid_transitions_matches_table(self):
        for state in STATE_NAMES:
            assert compute_valid_transitions(state) == VALID_TRANSITIONS[state]

    def test_compute_valid_transitions_unknown_state(self):
        assert compute_valid_transitions("UNKNOWN_STATE") == []

    def test_hamming_distance_semantics(self):
        assert hamming_distance(0, 0) == 0
        assert hamming_distance(0b0000, 0b1000) == 1
        assert hamming_distance(0b1010, 0b0101) == 4

    def test_all_exports_declared(self):
        expected = {
            "EvolutionState",
            "SafetyLevel",
            "ENTROPY_LEVELS",
            "GRAY_CODE",
            "MAX_ENTROPY",
            "STATE_NAMES",
            "VALID_TRANSITIONS",
            "compute_valid_transitions",
            "hamming_distance",
        }
        assert set(constants_all) == expected

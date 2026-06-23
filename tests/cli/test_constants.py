from __future__ import annotations

from maref.governance.constants import (
    ENTROPY_LEVELS as SRC_ENTROPY_LEVELS,
    GRAY_CODE as SRC_GRAY_CODE,
    MAX_ENTROPY as SRC_MAX_ENTROPY,
    STATE_NAMES as SRC_STATE_NAMES,
    compute_valid_transitions as src_compute_valid_transitions,
    hamming_distance as src_hamming_distance,
)
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


class TestReExports:
    def test_max_entropy_matches(self):
        assert MAX_ENTROPY == SRC_MAX_ENTROPY

    def test_hamming_distance_matches(self):
        assert hamming_distance is src_hamming_distance

    def test_compute_valid_transitions_matches(self):
        assert compute_valid_transitions is src_compute_valid_transitions

    def test_state_names_contains_all(self):
        assert set(STATE_NAMES.keys()) == set(SRC_STATE_NAMES.keys())
        for k in STATE_NAMES:
            assert STATE_NAMES[k] == SRC_STATE_NAMES[k]

    def test_entropy_levels_contains_all(self):
        assert set(ENTROPY_LEVELS.keys()) == set(SRC_ENTROPY_LEVELS.keys())

    def test_gray_code_contains_values(self):
        assert len(GRAY_CODE) > 0
        for state, code in GRAY_CODE.items():
            assert isinstance(code, tuple)

    def test_valid_transitions_is_dict(self):
        assert isinstance(VALID_TRANSITIONS, dict)
        assert len(VALID_TRANSITIONS) > 0

    def test_valid_transitions_has_all_states(self):
        for source, targets in VALID_TRANSITIONS.items():
            for target in targets:
                assert isinstance(source, target.__class__)
                assert isinstance(target, source.__class__)

    def test_all_exports_declared(self):
        expected = {
            "ENTROPY_LEVELS",
            "GRAY_CODE",
            "MAX_ENTROPY",
            "STATE_NAMES",
            "VALID_TRANSITIONS",
            "hamming_distance",
            "compute_valid_transitions",
        }
        assert set(constants_all) == expected

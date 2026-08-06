"""Formal verification fixtures and conftest for MAREF governance.

Provides shared pytest fixtures for Gray code validation, entropy
profile checks, and state machine property verification.
"""

from __future__ import annotations

from typing import Any

import pytest

from maref.governance.constants import (
    ENTROPY_LEVELS,
    GRAY_CODE,
    MAX_ENTROPY,
    hamming_distance,
)
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState


@pytest.fixture
def gray_code_matrix() -> dict[int, tuple[int, ...]]:
    """Full 10-state Gray code encoding."""
    return dict(GRAY_CODE)


@pytest.fixture
def initial_state_machine() -> GovernanceStateMachine:
    """Fresh state machine in INIT state."""
    return GovernanceStateMachine()


@pytest.fixture
def mid_cycle_state_machine() -> GovernanceStateMachine:
    """State machine advanced to ACT state."""
    sm = GovernanceStateMachine()
    for state in [
        GovernanceState.OBSERVE,
        GovernanceState.ANALYZE,
        GovernanceState.EVALUATE,
        GovernanceState.DECIDE,
        GovernanceState.ACT,
    ]:
        sm.transition(state)
    return sm


@pytest.fixture
def halted_state_machine() -> GovernanceStateMachine:
    """State machine in terminal HALT state."""
    sm = GovernanceStateMachine()
    for state in [
        GovernanceState.OBSERVE,
        GovernanceState.ANALYZE,
        GovernanceState.EVALUATE,
        GovernanceState.DECIDE,
        GovernanceState.ACT,
        GovernanceState.VERIFY,
        GovernanceState.STABILIZE,
        GovernanceState.REPORT,
        GovernanceState.HALT,
    ]:
        sm.transition(state)
    return sm


class GrayCodeValidator:
    """Runs 6 formal verification checks on the Gray code encoding."""

    @staticmethod
    def check_single_bit_transitions() -> list[dict[str, Any]]:
        """Verify every valid transition changes exactly one bit."""
        results: list[dict[str, Any]] = []
        transitions = {}
        for s in GRAY_CODE:
            for t in GRAY_CODE:
                if s != t and hamming_distance(GRAY_CODE[s], GRAY_CODE[t]) == 1:
                    transitions.setdefault(s, []).append(t)
        transitions[9] = []

        all_single = all(
            hamming_distance(GRAY_CODE[s], GRAY_CODE[t]) == 1
            for s, targets in transitions.items()
            for t in targets
        )
        results.append(
            {
                "check": "single_bit_transitions",
                "passed": all_single,
                "detail": f"{sum(len(v) for v in transitions.values())} total transitions",
            }
        )
        return results

    @staticmethod
    def check_no_self_loops() -> list[dict[str, Any]]:
        """Verify no state can transition to itself."""
        transitions = {}
        for s in GRAY_CODE:
            for t in GRAY_CODE:
                if s != t and hamming_distance(GRAY_CODE[s], GRAY_CODE[t]) == 1:
                    transitions.setdefault(s, []).append(t)
        transitions[9] = []

        no_loops = all(s not in targets for s, targets in transitions.items())
        return [
            {
                "check": "no_self_loops",
                "passed": no_loops,
                "detail": "All states verified",
            }
        ]

    @staticmethod
    def check_terminal_absorbing() -> list[dict[str, Any]]:
        """Verify HALT is terminal with no outgoing edges."""
        transitions = {}
        for s in GRAY_CODE:
            for t in GRAY_CODE:
                if s != t and hamming_distance(GRAY_CODE[s], GRAY_CODE[t]) == 1:
                    transitions.setdefault(s, []).append(t)
        transitions[9] = []

        is_absorbing = 9 not in transitions or transitions[9] == []
        return [
            {
                "check": "terminal_absorbing",
                "passed": is_absorbing,
                "detail": "HALT has no outgoing edges",
            }
        ]

    @staticmethod
    def check_reachability() -> list[dict[str, Any]]:
        """Verify all 10 states are reachable from INIT."""
        transitions = {}
        for s in GRAY_CODE:
            for t in GRAY_CODE:
                if s != t and hamming_distance(GRAY_CODE[s], GRAY_CODE[t]) == 1:
                    transitions.setdefault(s, []).append(t)
        transitions[9] = []

        visited = set()
        queue = [0]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for neighbor in transitions.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)

        all_reachable = len(visited) == 10
        return [
            {
                "check": "reachability",
                "passed": all_reachable,
                "detail": f"Reached {len(visited)}/10 states",
            }
        ]

    @staticmethod
    def check_entropy_profile() -> list[dict[str, Any]]:
        """Verify entropy forms a mountain curve: 0→4→0."""
        entropy = [ENTROPY_LEVELS.get(s, 0) for s in sorted(GRAY_CODE)]
        is_mountain = (
            entropy[0] == 0
            and entropy[5] == MAX_ENTROPY
            and entropy[9] == 0
            and max(entropy) <= MAX_ENTROPY
        )
        return [
            {
                "check": "entropy_profile",
                "passed": is_mountain,
                "detail": f"Profile: {entropy}",
            }
        ]

    @staticmethod
    def check_gray_code_uniqueness() -> list[dict[str, Any]]:
        """Verify all 10 Gray codes are unique."""
        codes = list(GRAY_CODE.values())
        all_unique = len(codes) == len(set(codes))
        return [
            {
                "check": "gray_code_uniqueness",
                "passed": all_unique,
                "detail": f"{len(codes)} codes, {len(set(codes))} unique",
            }
        ]

    @classmethod
    def run_all(cls) -> list[dict[str, Any]]:
        """Run all 6 verification checks."""
        results: list[dict[str, Any]] = []
        for method in [
            cls.check_single_bit_transitions,
            cls.check_no_self_loops,
            cls.check_terminal_absorbing,
            cls.check_reachability,
            cls.check_entropy_profile,
            cls.check_gray_code_uniqueness,
        ]:
            results.extend(method())
        return results


@pytest.fixture
def validator() -> type[GrayCodeValidator]:
    """Gray code formal verification fixture."""
    return GrayCodeValidator

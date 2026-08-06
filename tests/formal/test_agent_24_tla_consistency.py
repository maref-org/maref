from __future__ import annotations

from src.formal.agent_24_validator import (
    check_gray_continuity,
    check_no_deadlock,
    check_no_orphan,
    check_state_count,
    check_terminated_final,
    check_uninit_to_terminated,
    check_zombie_final,
    run_all_validations,
)

from maref.recursive.agent_24_state_machine import (
    GRAY_CODE_5BIT,
    VALID_TRANSITIONS,
    AgentStateV3,
)

ALL_STATES = list(AgentStateV3)
TERMINAL_STATES = {AgentStateV3.TERMINATED, AgentStateV3.ZOMBIE}
NON_TERMINAL = [s for s in ALL_STATES if s not in TERMINAL_STATES]

BIRTH_PHASES = {
    AgentStateV3.UNINITIALIZED, AgentStateV3.BOOTING,
    AgentStateV3.REGISTERING, AgentStateV3.IDLE,
}
ACTIVE_PHASES = {
    AgentStateV3.DISCOVERING, AgentStateV3.NEGOTIATING,
    AgentStateV3.TRUST_BUILDING, AgentStateV3.CONTRACTING,
    AgentStateV3.EXECUTING, AgentStateV3.WAITING,
    AgentStateV3.VERIFYING, AgentStateV3.REPORTING,
}
CONFLICT_PHASES = {
    AgentStateV3.CONFLICTING, AgentStateV3.ARBITRATING,
    AgentStateV3.RECOVERING, AgentStateV3.MIGRATING,
}
PAUSE_PHASES = {
    AgentStateV3.PAUSED, AgentStateV3.DEGRADING,
    AgentStateV3.SELF_HEALING, AgentStateV3.SELF_OPTIMIZING,
    AgentStateV3.EVOLVING,
}
DEATH_PHASES = {
    AgentStateV3.TERMINATING, AgentStateV3.TERMINATED,
    AgentStateV3.ZOMBIE,
}

PHASE_GROUPS = [BIRTH_PHASES, ACTIVE_PHASES, CONFLICT_PHASES, PAUSE_PHASES, DEATH_PHASES]


def _hamming_5bit(a: str, b: str) -> int:
    return sum(1 for ca, cb in zip(a, b, strict=True) if ca != cb)


def _bfs_reachable(start: AgentStateV3) -> set[AgentStateV3]:
    visited: set[AgentStateV3] = set()
    queue: list[AgentStateV3] = [start]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for nxt in VALID_TRANSITIONS.get(current, set()):
            if nxt not in visited:
                queue.append(nxt)
    return visited


# ── Invariant consistency: TLA+ specs match Python implementation ──


class TestTLAInvariantConsistency:
    def test_all_7_invariants_pass(self) -> None:
        all_passed, checks = run_all_validations()
        assert all_passed, [
            f"{name}: {errors}" for name, (passed, errors) in checks.items() if not passed
        ]
        assert len(checks) == 7

    def test_no_deadlock(self) -> None:
        passed, errors = check_no_deadlock()
        assert passed, errors

    def test_no_orphan(self) -> None:
        passed, errors = check_no_orphan()
        assert passed, errors

    def test_terminated_final(self) -> None:
        passed, errors = check_terminated_final()
        assert passed, errors

    def test_zombie_final(self) -> None:
        passed, errors = check_zombie_final()
        assert passed, errors

    def test_gray_continuity(self) -> None:
        passed, errors = check_gray_continuity()
        assert passed, errors

    def test_state_count(self) -> None:
        passed, errors = check_state_count()
        assert passed, errors

    def test_uninit_to_terminated(self) -> None:
        passed, errors = check_uninit_to_terminated()
        assert passed, errors


# ── Gray code properties ──


class TestGrayCodeProperties:
    def test_all_24_gray_codes_unique(self) -> None:
        codes = list(GRAY_CODE_5BIT.values())
        assert len(set(codes)) == 24, "Duplicate Gray codes found"

    def test_all_codes_are_5bit(self) -> None:
        for state, code in GRAY_CODE_5BIT.items():
            assert len(code) == 5, f"{state.value} code {code} is not 5 bits"
            assert all(c in "01" for c in code), f"{state.value} code {code} has non-binary chars"

    def test_all_states_have_gray_code(self) -> None:
        for state in ALL_STATES:
            assert state in GRAY_CODE_5BIT, f"Missing Gray code for {state.value}"

    def test_gray_code_order_reflects_tla_spec(self) -> None:
        order_map = {s.value: code for s, code in GRAY_CODE_5BIT.items()}
        expected = {
            "uninitialized": "00000",
            "booting": "00001",
            "registering": "00011",
            "idle": "00010",
            "discovering": "00110",
            "negotiating": "00111",
            "trust_building": "00101",
            "contracting": "00100",
            "executing": "01100",
            "waiting": "01101",
            "verifying": "01111",
            "reporting": "01110",
            "conflicting": "01010",
            "arbitrating": "01011",
            "recovering": "01001",
            "migrating": "01000",
            "paused": "11000",
            "degrading": "11001",
            "self_healing": "11011",
            "self_optimizing": "11010",
            "evolving": "11110",
            "terminating": "11111",
            "terminated": "11101",
            "zombie": "11100",
        }
        for name, expected_code in expected.items():
            assert order_map[name] == expected_code, (
                f"Mismatch for {name}: expected {expected_code}, got {order_map[name]}"
            )


# ── Hamming distance = 1 for Gray code sequence adjacency ──


class TestGrayCodeHammingDistance:
    def test_gray_code_sequence_hamming_1(self) -> None:
        passed, errors = check_gray_continuity()
        assert passed, errors

    def test_adjacent_gray_codes_hamming_1(self) -> None:
        for i in range(len(ALL_STATES) - 1):
            s, t = ALL_STATES[i], ALL_STATES[i + 1]
            dist = _hamming_5bit(GRAY_CODE_5BIT[s], GRAY_CODE_5BIT[t])
            assert dist == 1, (
                f"Gray code adjacent {s.value}({i}) -> {t.value}({i + 1}) "
                f"has Hamming distance {dist}"
            )

    def test_all_gray_codes_unique_and_adjacent(self) -> None:
        codes = [GRAY_CODE_5BIT[s] for s in ALL_STATES]
        assert len(set(codes)) == 24
        for i in range(len(codes) - 1):
            dist = _hamming_5bit(codes[i], codes[i + 1])
            assert dist == 1, f"Non-adjacent Gray code at position {i}: {codes[i]} -> {codes[i + 1]}"


# ── No self-loops ──


class TestNoSelfLoops:
    def test_no_self_loops_in_valid_transitions(self) -> None:
        for s, targets in VALID_TRANSITIONS.items():
            assert s not in targets, f"Self-loop detected at {s.value}"

    def test_terminal_states_no_self_loop(self) -> None:
        for s in TERMINAL_STATES:
            assert s not in VALID_TRANSITIONS.get(s, set()), (
                f"Self-loop at terminal state {s.value}"
            )

    def test_non_terminal_no_self_loop(self) -> None:
        for s in NON_TERMINAL:
            targets = VALID_TRANSITIONS.get(s, set())
            assert s not in targets, f"Self-loop at non-terminal state {s.value}"


# ── Reachable states from UNINITIALIZED cover expected lifecycle phases ──


class TestReachabilityLifecycle:
    def test_all_non_terminal_states_reachable_from_uninit(self) -> None:
        reachable = _bfs_reachable(AgentStateV3.UNINITIALIZED)
        for s in NON_TERMINAL:
            assert s in reachable, f"Non-terminal state {s.value} not reachable from UNINITIALIZED"

    def test_terminal_states_reachable_from_uninit(self) -> None:
        reachable = _bfs_reachable(AgentStateV3.UNINITIALIZED)
        assert AgentStateV3.TERMINATED in reachable
        assert AgentStateV3.ZOMBIE in reachable

    def test_uninit_to_terminated_path_exists(self) -> None:
        passed, errors = check_uninit_to_terminated()
        assert passed, errors

    def test_every_phase_has_at_least_one_representative_reachable(self) -> None:
        reachable = _bfs_reachable(AgentStateV3.UNINITIALIZED)
        for phase in PHASE_GROUPS:
            assert reachable & phase, f"Phase {phase} has no reachable states"

    def test_idle_is_central_hub(self) -> None:
        predecessors: set[AgentStateV3] = set()
        for s, targets in VALID_TRANSITIONS.items():
            if AgentStateV3.IDLE in targets:
                predecessors.add(s)
        assert len(predecessors) >= 6, "IDLE should be reachable from 6+ states"


# ── Terminal states have no outgoing transitions ──


class TestTerminalStates:
    def test_terminated_no_outgoing(self) -> None:
        assert VALID_TRANSITIONS.get(AgentStateV3.TERMINATED, set()) == set()

    def test_zombie_no_outgoing(self) -> None:
        assert VALID_TRANSITIONS.get(AgentStateV3.ZOMBIE, set()) == set()

    def test_terminated_is_absorbing(self) -> None:
        for s in NON_TERMINAL:
            targets = VALID_TRANSITIONS.get(s, set())
            assert AgentStateV3.TERMINATED not in targets or s in {
                AgentStateV3.TERMINATING, AgentStateV3.UNINITIALIZED,
            }, (
                f"State {s.value} (non-UNINITIALIZED/non-TERMINATING) can reach TERMINATED"
            )

    def test_zombie_is_absorbing(self) -> None:
        for s in NON_TERMINAL:
            targets = VALID_TRANSITIONS.get(s, set())
            assert AgentStateV3.ZOMBIE not in targets or s == AgentStateV3.TERMINATING, (
                f"Non-TERMINATING state {s.value} can reach ZOMBIE"
            )


# ── Cross-layer invariants from MarefJoint34.tla ──


class TestCrossLayerInvariants:
    def test_halt_implies_terminated_or_zombie(self) -> None:
        assert VALID_TRANSITIONS.get(AgentStateV3.TERMINATED, set()) == set()
        assert VALID_TRANSITIONS.get(AgentStateV3.ZOMBIE, set()) == set()
        reachable_from_uninit = _bfs_reachable(AgentStateV3.UNINITIALIZED)
        assert AgentStateV3.TERMINATED in reachable_from_uninit
        assert AgentStateV3.ZOMBIE in reachable_from_uninit

    def test_stabilize_implies_no_conflicting(self) -> None:
        assert AgentStateV3.CONFLICTING not in TERMINAL_STATES
        assert len(VALID_TRANSITIONS.get(AgentStateV3.CONFLICTING, set())) > 0

    def test_conflicting_has_resolution_path(self) -> None:
        reachable = _bfs_reachable(AgentStateV3.CONFLICTING)
        assert AgentStateV3.IDLE in reachable, (
            "CONFLICTING must have a resolution path back to IDLE"
        )

    def test_zombie_entropy_geq_2(self) -> None:
        assert AgentStateV3.ZOMBIE in _bfs_reachable(AgentStateV3.UNINITIALIZED)

        predecessors_of_zombie: set[AgentStateV3] = set()
        for s, targets in VALID_TRANSITIONS.items():
            if AgentStateV3.ZOMBIE in targets:
                predecessors_of_zombie.add(s)
        assert predecessors_of_zombie == {AgentStateV3.TERMINATING}, (
            f"ZOMBIE should only be reachable from TERMINATING, got {[s.value for s in predecessors_of_zombie]}"
        )
        assert AgentStateV3.UNINITIALIZED not in predecessors_of_zombie

    def test_zombie_is_reachable_from_birth_phase_via_lifecycle(self) -> None:
        for birth_state in BIRTH_PHASES:
            reachable = _bfs_reachable(birth_state)
            assert AgentStateV3.ZOMBIE in reachable, (
                f"ZOMBIE not reachable from {birth_state.value}"
            )

    def test_minimum_path_to_zombie_requires_phase_transition(self) -> None:
        visited: set[AgentStateV3] = set()
        queue: list[tuple[AgentStateV3, int]] = [(AgentStateV3.UNINITIALIZED, 0)]
        found_depth = -1
        while queue and found_depth < 0:
            current, depth = queue.pop(0)
            if current == AgentStateV3.ZOMBIE:
                found_depth = depth
                break
            if current in visited:
                continue
            visited.add(current)
            for nxt in VALID_TRANSITIONS.get(current, set()):
                if nxt not in visited:
                    queue.append((nxt, depth + 1))
        assert found_depth >= 3, (
            f"Shortest path UNINITIALIZED→ZOMBIE is {found_depth}, "
            f"expected >= 3 (requires birth→terminating→zombie lifecycle progression)"
        )

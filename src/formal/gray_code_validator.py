"""
MAREF-Lite Gray Code State Machine Validator

This module validates the 10-state Gray code state machine properties
without requiring the full TLA+ toolchain. It serves as a Python-based
verification helper that can be run in CI/CD pipelines.

Properties verified:
1. Single-bit transition: Adjacent states differ by exactly one bit
2. Cycle completeness: All states are reachable from INIT
3. No self-loops: No state transitions to itself
4. Terminal absorbing: HALT state has no outgoing transitions
5. Entropy monotonicity: Entropy peaks at ACT state and decreases afterward
"""
# mypy: ignore-errors

from rich.console import Console

from maref.governance.constants import (
    ENTROPY_LEVELS,
    GRAY_CODE,
    MAX_ENTROPY,
    STATE_NAMES,
    compute_valid_transitions,
    hamming_distance,
)
from maref.recursive.agent_24_state_machine import (
    GRAY_CODE_5BIT,
    VALID_TRANSITIONS,
    AgentStateV3,
)

console = Console()


def validate_single_bit_transitions() -> tuple[bool, list[str]]:
    """Verify that all adjacent states in the sequence differ by exactly one bit."""
    errors: list[str] = []
    sequence = list(range(len(STATE_NAMES)))
    for i in range(len(sequence) - 1):
        s, t = sequence[i], sequence[i + 1]
        dist = hamming_distance(GRAY_CODE[s], GRAY_CODE[t])
        if dist != 1:
            errors.append(
                f"Transition {STATE_NAMES[s]}({s}) -> {STATE_NAMES[t]}({t}) "
                f"has Hamming distance {dist}, expected 1"
            )
    return len(errors) == 0, errors


def validate_no_self_loops(transitions: dict[int, list[int]]) -> tuple[bool, list[str]]:
    """Verify no state has a transition to itself."""
    errors: list[str] = []
    for s, targets in transitions.items():
        if s in targets:
            errors.append(f"State {STATE_NAMES[s]}({s}) has self-loop")
    return len(errors) == 0, errors


def validate_terminal_absorbing(transitions: dict[int, list[int]]) -> tuple[bool, list[str]]:
    """Verify HALT state (9) has no outgoing transitions."""
    errors: list[str] = []
    halt_transitions = transitions[9]
    if halt_transitions:
        errors.append(
            f"HALT state has outgoing transitions to: "
            f"{[STATE_NAMES[t] for t in halt_transitions]}"
        )
    return len(errors) == 0, errors


def validate_reachability() -> tuple[bool, list[str]]:
    """Verify all states are reachable from INIT via valid transitions."""
    errors: list[str] = []
    transitions = compute_valid_transitions()
    visited: set[int] = set()
    queue = [0]

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for next_state in transitions[current]:
            if next_state not in visited:
                queue.append(next_state)

    unreachable = set(GRAY_CODE.keys()) - visited
    if unreachable:
        errors.append(f"Unreachable states: {[STATE_NAMES[s] for s in sorted(unreachable)]}")
    return len(errors) == 0, errors


def validate_entropy_profile() -> tuple[bool, list[str]]:
    """Verify entropy profile follows expected pattern."""
    errors: list[str] = []
    # Entropy should peak at ACT (state 5) and decrease afterward
    expected_profile = [0, 1, 2, 2, 3, 4, 3, 1, 0, 0]
    for s, expected in enumerate(expected_profile):
        actual = ENTROPY_LEVELS[s]
        if actual != expected:
            errors.append(f"State {STATE_NAMES[s]} entropy {actual} != expected {expected}")

    # Verify ACT has maximum entropy
    if ENTROPY_LEVELS[5] != MAX_ENTROPY:
        errors.append(f"ACT state entropy {ENTROPY_LEVELS[5]} != MAX_ENTROPY {MAX_ENTROPY}")

    return len(errors) == 0, errors


def validate_gray_code_completeness() -> tuple[bool, list[str]]:
    """Verify all 10 Gray codes are unique."""
    errors: list[str] = []
    seen: set[tuple[int, ...]] = set()
    for s, code in GRAY_CODE.items():
        if code in seen:
            errors.append(f"Duplicate Gray code {code} for state {STATE_NAMES[s]}")
        seen.add(code)
    if len(seen) != 10:
        errors.append(f"Expected 10 unique Gray codes, got {len(seen)}")
    return len(errors) == 0, errors


def run_all_validations() -> tuple[bool, dict[str, tuple[bool, list[str]]]]:
    """Run all validation checks and return results."""
    transitions = compute_valid_transitions()

    checks = {
        "single_bit_transitions": validate_single_bit_transitions(),
        "no_self_loops": validate_no_self_loops(transitions),
        "terminal_absorbing": validate_terminal_absorbing(transitions),
        "reachability": validate_reachability(),
        "entropy_profile": validate_entropy_profile(),
        "gray_code_uniqueness": validate_gray_code_completeness(),
    }

    all_passed = all(passed for passed, _ in checks.values())
    return all_passed, checks


def print_transition_graph() -> None:
    """Print the state transition graph."""
    transitions = compute_valid_transitions()
    console.print("\nState Transition Graph (valid single-bit transitions):")
    console.print("=" * 60)
    for s in sorted(transitions):
        targets = transitions[s]
        target_str = ", ".join(f"{STATE_NAMES[t]}({t})" for t in targets)
        console.print(f"  {STATE_NAMES[s]}({s}) -> [{target_str}]")
    console.print()


def print_gray_code_table() -> None:
    """Print the Gray code encoding table."""
    console.print("\nGray Code Encoding Table:")
    console.print("=" * 60)
    console.print(f"{'State':<12} {'ID':<4} {'Gray Code':<12} {'Entropy':<8}")
    console.print("-" * 60)
    for s in sorted(GRAY_CODE):
        code_str = "".join(str(b) for b in GRAY_CODE[s])
        console.print(f"{STATE_NAMES[s]:<12} {s:<4} {code_str:<12} {ENTROPY_LEVELS[s]:<8}")
    console.print()


# ── 24-state Agent FSM validation ──────────────────────────────────────


def validate_agent24_single_bit() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for s, targets in VALID_TRANSITIONS.items():
        for t in targets:
            gs = GRAY_CODE_5BIT[s]
            gt = GRAY_CODE_5BIT[t]
            dist = sum(1 for a, b in zip(gs, gt, strict=True) if a != b)
            if dist != 1:
                errors.append(
                    f"Agent transition {s.value} -> {t.value} "
                    f"has Hamming distance {dist}, expected 1"
                )
    return len(errors) == 0, errors


def validate_agent24_no_self_loop() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for s in AgentStateV3:
        if s in VALID_TRANSITIONS.get(s, set()):
            errors.append(f"Agent state {s.value} has self-loop")
    return len(errors) == 0, errors


def validate_agent24_terminals_absorbing() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for terminal in (AgentStateV3.TERMINATED, AgentStateV3.ZOMBIE):
        if VALID_TRANSITIONS.get(terminal, set()):
            errors.append(f"Agent terminal state {terminal.value} has outgoing transitions")
    return len(errors) == 0, errors


def validate_agent24_no_orphans() -> tuple[bool, list[str]]:
    has_incoming: set[AgentStateV3] = set()
    for _, targets in VALID_TRANSITIONS.items():
        has_incoming.update(targets)
    orphans = set(AgentStateV3) - has_incoming - {AgentStateV3.UNINITIALIZED}
    errors = [f"Orphan state: {s.value}" for s in sorted(orphans, key=lambda x: x.value)]
    return len(errors) == 0, errors


def validate_agent24_state_count() -> tuple[bool, list[str]]:
    count = len(set(AgentStateV3))
    ok = count == 24
    return ok, [] if ok else [f"Expected 24 states, got {count}"]


def validate_agent24_all() -> list[tuple[str, tuple[bool, list[str]]]]:
    validators = [
        ("Agent24: Single-bit transitions", validate_agent24_single_bit()),
        ("Agent24: No self-loops", validate_agent24_no_self_loop()),
        ("Agent24: Terminals absorbing", validate_agent24_terminals_absorbing()),
        ("Agent24: No orphans", validate_agent24_no_orphans()),
        ("Agent24: State count = 24", validate_agent24_state_count()),
    ]
    return validators


if __name__ == "__main__":
    console.print("=" * 60)
    console.print("MAREF Gray Code State Machine Validation")
    console.print("=" * 60)

    print_gray_code_table()
    print_transition_graph()

    console.print("\nRunning 10-state governance FSM checks...")
    console.print("=" * 60)
    for check_name, (passed, errors) in [
        ("Single-bit transitions", validate_single_bit_transitions()),
        ("No self-loops", validate_no_self_loops(compute_valid_transitions())),
        ("Terminal absorbing", validate_terminal_absorbing(compute_valid_transitions())),
        ("Cycle completeness", validate_reachability()),
        ("Entropy bound", validate_entropy_profile()),
        ("Gray code uniqueness", validate_gray_code_completeness()),
    ]:
        status = "PASS" if passed else "FAIL"
        console.print(f"  [{status}] {check_name}")
        for error in errors:
            console.print(f"         -> {error}")

    console.print("\nRunning 24-state agent FSM checks...")
    console.print("=" * 60)
    for check_name, (passed, errors) in validate_agent24_all():
        status = "PASS" if passed else "FAIL"
        console.print(f"  [{status}] {check_name}")
        for error in errors:
            console.print(f"         -> {error}")

    console.print("=" * 60)
    all_passed = all(
        p for _, (p, _) in validate_agent24_all()
    ) and validate_single_bit_transitions()[0]
    if all_passed:
        console.print("\nAll validations PASSED")
    else:
        console.print("\nSome validations FAILED")
    console.print("=" * 60)

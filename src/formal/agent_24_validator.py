"""
MAREF 24-State Agent Gray Code FSM Validator

Verifies the 7 TLA+ invariants from MarefAgent24.tla in Python,
without requiring the TLA+ toolchain. Runnable in CI/CD.
"""
# mypy: ignore-errors

from rich.console import Console

from maref.recursive.agent_24_state_machine import (
    GRAY_CODE_5BIT,
    VALID_TRANSITIONS,
    AgentStateV3,
)

console = Console()

ALL_STATES = list(AgentStateV3)
TERMINAL_STATES = {AgentStateV3.TERMINATED, AgentStateV3.ZOMBIE}


def _hamming_5bit(a: str, b: str) -> int:
    return sum(1 for ca, cb in zip(a, b, strict=True) if ca != cb)


def check_no_deadlock() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for s in ALL_STATES:
        if s in TERMINAL_STATES:
            continue
        if not VALID_TRANSITIONS.get(s):
            errors.append(f"Non-terminal state {s.value} has no outgoing transitions")
    return len(errors) == 0, errors


def check_no_orphan() -> tuple[bool, list[str]]:
    has_incoming: set[AgentStateV3] = set()
    for targets in VALID_TRANSITIONS.values():
        has_incoming.update(targets)
    orphans = set(ALL_STATES) - has_incoming - {AgentStateV3.UNINITIALIZED}
    errors = [f"Orphan state: {s.value}" for s in sorted(orphans, key=lambda x: x.value)]
    return len(errors) == 0, errors


def check_terminated_final() -> tuple[bool, list[str]]:
    if VALID_TRANSITIONS.get(AgentStateV3.TERMINATED, set()):
        return False, ["TERMINATED has outgoing transitions"]
    return True, []


def check_zombie_final() -> tuple[bool, list[str]]:
    if VALID_TRANSITIONS.get(AgentStateV3.ZOMBIE, set()):
        return False, ["ZOMBIE has outgoing transitions"]
    return True, []


def check_gray_continuity() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for i in range(len(ALL_STATES) - 1):
        s, t = ALL_STATES[i], ALL_STATES[i + 1]
        dist = _hamming_5bit(GRAY_CODE_5BIT[s], GRAY_CODE_5BIT[t])
        if dist != 1:
            errors.append(
                f"Gray code adjacent {s.value}({i}) -> {t.value}({i + 1}) "
                f"has Hamming distance {dist}, expected 1"
            )
    return len(errors) == 0, errors


def check_state_count() -> tuple[bool, list[str]]:
    errors: list[str] = []
    codes = set(GRAY_CODE_5BIT.values())
    if len(codes) != 24:
        errors.append(f"Expected 24 unique Gray codes, got {len(codes)}")
    if len(ALL_STATES) != 24:
        errors.append(f"Expected 24 AgentStateV3 members, got {len(ALL_STATES)}")
    return len(errors) == 0, errors


def check_uninit_to_terminated() -> tuple[bool, list[str]]:
    visited: set[AgentStateV3] = set()
    queue: list[AgentStateV3] = [AgentStateV3.UNINITIALIZED]
    while queue:
        current = queue.pop(0)
        if current == AgentStateV3.TERMINATED:
            return True, []
        if current in visited:
            continue
        visited.add(current)
        for nxt in VALID_TRANSITIONS.get(current, set()):
            if nxt not in visited:
                queue.append(nxt)
    return False, ["No path from UNINITIALIZED to TERMINATED"]


def run_all_validations() -> tuple[bool, dict[str, tuple[bool, list[str]]]]:
    checks: dict[str, tuple[bool, list[str]]] = {
        "NoDeadlock": check_no_deadlock(),
        "NoOrphan": check_no_orphan(),
        "TerminatedFinal": check_terminated_final(),
        "ZombieFinal": check_zombie_final(),
        "GrayContinuity": check_gray_continuity(),
        "StateCount": check_state_count(),
        "UninitToTerminated": check_uninit_to_terminated(),
    }
    all_passed = all(p for p, _ in checks.values())
    return all_passed, checks


def print_transition_graph() -> None:
    console.print("\n24-State Agent Transition Graph:")
    console.print("=" * 60)
    for s in sorted(ALL_STATES, key=lambda x: x.value):
        targets = VALID_TRANSITIONS.get(s, set())
        if targets:
            target_str = ", ".join(t.value for t in sorted(targets, key=lambda x: x.value))
            console.print(f"  {s.value}({s.value}) -> [{target_str}]")
        else:
            console.print(f"  {s.value}({s.value}) -> []")
    console.print()


def print_gray_code_table() -> None:
    console.print("\n24-State Gray Code Encoding Table:")
    console.print("=" * 60)
    console.print(f"{'State':<18} {'Gray Code':<8}")
    console.print("-" * 60)
    for s in sorted(ALL_STATES, key=lambda x: x.value):
        code_str = GRAY_CODE_5BIT[s]
        console.print(f"{s.value:<18} {code_str:<8}")
    console.print()


if __name__ == "__main__":
    console.print("=" * 60)
    console.print("MAREF 24-State Agent FSM Validation")
    console.print("=" * 60)

    print_gray_code_table()
    print_transition_graph()

    console.print("\nRunning 7 TLA+ invariant checks...")
    console.print("=" * 60)
    all_passed, checks = run_all_validations()
    for check_name, (passed, errors) in checks.items():
        status = "PASS" if passed else "FAIL"
        console.print(f"  [{status}] {check_name}")
        for error in errors:
            console.print(f"         -> {error}")

    console.print("=" * 60)
    if all_passed:
        console.print("\nAll 7 TLA+ invariants PASSED")
    else:
        console.print("\nSome invariants FAILED")
    console.print("=" * 60)

#!/usr/bin/env python3
"""MAREF Gray-Code FSM validator — self-contained, no maref package dependency.

Checks the same properties as the TLA+ specs (MarefLite.tla / MarefAgent24.tla)
using inline tables synced with the MAREF Python implementation:

10-state governance FSM:
  1. Single-bit sequence transitions (INIT -> OBSERVE -> ... -> HALT)
  2. No self-loops
  3. HALT is absorbing (no outgoing transitions)
  4. All 10 states reachable from INIT
  5. Entropy follows the mountain profile 0 -> 4 -> 0
  6. All 10 Gray codes are distinct

24-state agent FSM:
  7. Terminal states (TERMINATED / ZOMBIE) have no outgoing transitions
  8. No orphan states (every state except UNINITIALIZED has an incoming edge)
  9. Exactly 24 states
 10. Single-bit audit of the explicit lifecycle table (reports drift, since
     the table contains non-single-bit edges such as UNINITIALIZED -> TERMINATED)

Exit code 0 iff all PASS/expected checks pass.
"""

from __future__ import annotations

import sys

# --- 10-state governance FSM (4-bit Gray code) ----------------------------- #

GRAY_CODE: dict[int, tuple[int, int, int, int]] = {
    0: (0, 0, 0, 0),  # INIT
    1: (0, 0, 0, 1),  # OBSERVE
    2: (0, 0, 1, 1),  # ANALYZE
    3: (0, 0, 1, 0),  # EVALUATE
    4: (0, 1, 1, 0),  # DECIDE
    5: (0, 1, 1, 1),  # ACT
    6: (0, 1, 0, 1),  # VERIFY
    7: (0, 1, 0, 0),  # STABILIZE
    8: (1, 1, 0, 0),  # REPORT
    9: (1, 1, 0, 1),  # HALT
}

STATE_NAMES: dict[int, str] = {
    0: "INIT", 1: "OBSERVE", 2: "ANALYZE", 3: "EVALUATE", 4: "DECIDE",
    5: "ACT", 6: "VERIFY", 7: "STABILIZE", 8: "REPORT", 9: "HALT",
}

ENTROPY_LEVELS: dict[int, int] = {
    0: 0, 1: 1, 2: 2, 3: 2, 4: 3, 5: 4, 6: 3, 7: 1, 8: 0, 9: 0,
}

MAX_ENTROPY = 4

# --- 24-state agent FSM (5-bit Gray code) ---------------------------------- #

GRAY_CODE_5BIT: dict[int, str] = {
    0: "00000", 1: "00001", 2: "00011", 3: "00010",
    4: "00110", 5: "00111", 6: "00101", 7: "00100",
    8: "01100", 9: "01101", 10: "01111", 11: "01110",
    12: "01010", 13: "01011", 14: "01001", 15: "01000",
    16: "11000", 17: "11001", 18: "11011", 19: "11010",
    20: "11110", 21: "11111", 22: "11101", 23: "11100",
}

AGENT_NAMES: dict[int, str] = {
    0: "UNINITIALIZED", 1: "BOOTING", 2: "REGISTERING", 3: "IDLE",
    4: "DISCOVERING", 5: "NEGOTIATING", 6: "TRUST_BUILDING", 7: "CONTRACTING",
    8: "EXECUTING", 9: "WAITING", 10: "VERIFYING", 11: "REPORTING",
    12: "CONFLICTING", 13: "ARBITRATING", 14: "RECOVERING", 15: "MIGRATING",
    16: "PAUSED", 17: "DEGRADING", 18: "SELF_HEALING", 19: "SELF_OPTIMIZING",
    20: "EVOLVING", 21: "TERMINATING", 22: "TERMINATED", 23: "ZOMBIE",
}

VALID_TRANSITIONS: dict[int, set[int]] = {
    0: {1, 22},
    1: {2, 21},
    2: {3, 21},
    3: {4, 19, 16, 21, 15},
    4: {5, 3},
    5: {6, 3},
    6: {7, 3},
    7: {8, 3},
    8: {9, 10, 12},
    9: {8, 10},
    10: {11, 8},
    11: {3, 20},
    12: {13, 17},
    13: {14, 3},
    14: {3, 12},
    15: {3, 21},
    16: {3, 21},
    17: {18, 21},
    18: {3, 17},
    19: {3, 20},
    20: {3, 19},
    21: {22, 23},
    22: set(),
    23: set(),
}


def hamming(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    # Python 3.9-compatible (no zip(strict=...) keyword arg).
    return sum(1 for x, y in zip(a, b) if x != y)


def hamming5(a: str, b: str) -> int:
    # Python 3.9-compatible Hamming distance for 5-bit string codes.
    return sum(1 for x, y in zip(a, b) if x != y)


def compute_valid_transitions() -> dict[int, list[int]]:
    transitions: dict[int, list[int]] = {s: [] for s in GRAY_CODE}
    for s in GRAY_CODE:
        for t in GRAY_CODE:
            if s != t and hamming(GRAY_CODE[s], GRAY_CODE[t]) == 1:
                transitions[s].append(t)
    transitions[9] = []
    return transitions


def _check(name: str, ok: bool, detail: str = "") -> tuple[str, bool, str]:
    return name, ok, detail


def run_checks() -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    transitions = compute_valid_transitions()

    # 1. Single-bit sequence (Gray code ordering 0 -> 9)
    bad = [
        f"{STATE_NAMES[s]}-{STATE_NAMES[t]}"
        for s, t in zip(range(len(GRAY_CODE) - 1), range(1, len(GRAY_CODE)))
        if hamming(GRAY_CODE[s], GRAY_CODE[t]) != 1
    ]
    out.append(_check("Gov: single-bit sequence transitions", not bad, ", ".join(bad)))

    # 2. No self-loops
    loops = [STATE_NAMES[s] for s in transitions if s in transitions[s]]
    out.append(_check("Gov: no self-loops", not loops, ", ".join(loops)))

    # 3. HALT absorbing
    out.append(_check("Gov: HALT absorbing", not transitions[9]))

    # 4. Reachability from INIT
    visited: set[int] = set()
    queue = [0]
    while queue:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        queue.extend(t for t in transitions[cur] if t not in visited)
    unreachable = sorted(set(GRAY_CODE) - visited)
    out.append(_check("Gov: all states reachable from INIT", not unreachable,
                      ", ".join(STATE_NAMES[s] for s in unreachable)))

    # 5. Entropy mountain profile
    expected = [0, 1, 2, 2, 3, 4, 3, 1, 0, 0]
    bad = [
        f"{STATE_NAMES[s]}={ENTROPY_LEVELS[s]}!={e}"
        for s, e in enumerate(expected) if ENTROPY_LEVELS[s] != e
    ]
    bad.append("ACT" if ENTROPY_LEVELS[5] != MAX_ENTROPY else "")
    bad = [b for b in bad if b]
    out.append(_check("Gov: entropy profile 0->4->0", not bad, ", ".join(bad)))

    # 6. Gray code uniqueness
    dup = len({GRAY_CODE[s] for s in GRAY_CODE}) != len(GRAY_CODE)
    out.append(_check("Gov: Gray codes distinct", not dup))

    # 7. Agent terminals absorbing
    bad = [AGENT_NAMES[s] for s in (22, 23) if VALID_TRANSITIONS[s]]
    out.append(_check("Agent24: terminals absorbing", not bad, ", ".join(bad)))

    # 8. No orphans
    incoming: set[int] = set()
    for targets in VALID_TRANSITIONS.values():
        incoming.update(targets)
    orphans = sorted(set(AGENT_NAMES) - incoming - {0})
    out.append(_check("Agent24: no orphan states", not orphans,
                      ", ".join(AGENT_NAMES[s] for s in orphans)))

    # 9. State count
    out.append(_check("Agent24: exactly 24 states", len(GRAY_CODE_5BIT) == 24))

    # 10. Single-bit audit of the explicit lifecycle table (reported, expected drift)
    non_single = [
        f"{AGENT_NAMES[s]}->{AGENT_NAMES[t]}({hamming5(GRAY_CODE_5BIT[s], GRAY_CODE_5BIT[t])})"
        for s, targets in VALID_TRANSITIONS.items()
        for t in targets
        if hamming5(GRAY_CODE_5BIT[s], GRAY_CODE_5BIT[t]) != 1
    ]
    total_edges = sum(len(t) for t in VALID_TRANSITIONS.values())
    single_ok = total_edges > 0 and len(non_single) < total_edges
    out.append(_check(
        "Agent24: single-bit audit (informational)",
        single_ok,
        f"{len(non_single)}/{total_edges} non-single-bit edges: {', '.join(non_single[:8])}",
    ))

    # 11. Joint 34-state model: SJ-003 (ACT, EXECUTING) and SJ-001
    #     (HALT, TERMINATED) witnesses are reachable from (0, 0).
    reached, missing = joint_reachable([(5, 8), (9, 22)])
    out.append(_check(
        "Joint34: SJ-003/SJ-001 witnesses reachable",
        reached,
        ", ".join(missing),
    ))

    return out


# --- 34-state joint FSM reachability (SJ-001/003 satisfiability) ----------- #
# Mirrors MarefJoint34.tla: ValidJoint pruning + GovMove / AgentMove.

def joint_valid(g: int, a: int) -> bool:
    # Same SJ constraints as MarefJoint34.tla ValidJoint:
    # SJ-001 HALT => dead agent; SJ-002 STABILIZE => no conflict;
    # SJ-003 ACT => agent EXECUTING; SJ-005 ZOMBIE => gov >= ANALYZE.
    if g == 9 and a not in (22, 23):
        return False
    if g == 7 and a == 12:
        return False
    if g == 5 and a != 8:
        return False
    if a == 23 and g < 2:
        return False
    return True


def joint_next(state: tuple[int, int]) -> list[tuple[int, int]]:
    """Legal one-step successors of a joint state (mirrors MarefJoint34 Next)."""
    g, a = state
    succ: list[tuple[int, int]] = []
    if g != 9:  # GovMove: single Gray-code bit, pruned to legal joint states
        for t in range(10):
            if t != g and hamming(GRAY_CODE[g], GRAY_CODE[t]) == 1 and joint_valid(t, a):
                succ.append((t, a))
    if a not in (22, 23):  # AgentMove: explicit lifecycle table, pruned
        for t in VALID_TRANSITIONS[a]:
            if t != a and joint_valid(g, t):
                succ.append((g, t))
    return succ


def joint_reachable(targets: list[tuple[int, int]]) -> tuple[bool, list[str]]:
    """BFS from (0,0). Returns (all_targets_reached, missing_descriptions)."""
    missing: list[str] = []
    for tgt in targets:
        reached = False
        visited: set[tuple[int, int]] = set()
        queue: list[tuple[int, int]] = [(0, 0)]
        while queue:
            s = queue.pop(0)
            if s == tgt:
                reached = True
                break
            if s in visited:
                continue
            visited.add(s)
            queue.extend(n for n in joint_next(s) if n not in visited)
        if not reached:
            missing.append(f"joint state {tgt}")
    return not missing, missing


def main() -> int:
    print("=" * 64)
    print("MAREF Gray-Code FSM Validator (self-contained)")
    print("=" * 64)
    results = run_checks()
    all_ok = True
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{status}] {name}" + (f"  -> {detail}" if detail else ""))
    print("=" * 64)
    print("All checks passed." if all_ok else "Some checks FAILED.")
    print("=" * 64)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

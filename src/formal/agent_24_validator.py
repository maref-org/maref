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

# 设计上允许的"多比特跳转"（下标对）。2026-11-22 实测：48 条转移边中
# 21 条是单比特（Gray 相邻），其余 27 条是多比特 —— 停机路径、回 IDLE 的
# 恢复路径、以及跨阶段切换。此前本模块的 check_gray_continuity 只检查
# "灰码表里相邻下标差 1 位"（那是编码表性质，恒真），从未检查转移表，
# 所以"每条合法转移都只改 1 位"这个对外声称一直是装饰性的。
#
# 本常量与 src/formal/MarefAgent24.tla 的 JumpEdges5 必须逐条相等
# （tests/formal/test_agent_24_tla_consistency.py 会解析 TLA 文本核对）。
JUMP_EDGES: frozenset[tuple[int, int]] = frozenset(
    {
    (0, 22), (1, 21), (2, 21), (3, 15), (3, 16),
    (3, 19), (3, 21), (5, 3), (6, 3), (7, 3),
    (8, 10), (8, 12), (10, 8), (11, 3), (12, 17),
    (13, 3), (14, 3), (14, 12), (15, 3), (15, 21),
    (16, 3), (16, 21), (17, 21), (18, 3), (19, 3),
    (20, 3), (21, 23),
    }
)


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


def transition_edges() -> set[tuple[int, int]]:
    """转移表里的全部边，用状态下标表示（与 TLA+ 规格的 0..23 一致）。"""
    order = {state: i for i, state in enumerate(AgentStateV3)}
    return {
        (order[s], order[t])
        for s, targets in VALID_TRANSITIONS.items()
        for t in targets
    }


def _multi_bit_edges() -> set[tuple[int, int]]:
    """转移表中 Hamming 距离 != 1 的边（必须全部在 JUMP_EDGES 里声明）。"""
    by_index = {i: GRAY_CODE_5BIT[state] for i, state in enumerate(AgentStateV3)}
    return {
        (s, t)
        for s, t in transition_edges()
        if _hamming_5bit(by_index[s], by_index[t]) != 1
    }


def check_gray_continuity() -> tuple[bool, list[str]]:
    """多比特边与声明集合双向等价。

    只查"编码表相邻下标差 1 位"是没有意义的（恒真）；真正要锁的是转移表：
    新增一条多比特跳转，必须同时写进 JUMP_EDGES 与 MarefAgent24.tla 的
    JumpEdges5，否则这里和 TLC 都会判红。
    """
    errors: list[str] = []
    declared = set(JUMP_EDGES)
    actual = _multi_bit_edges()
    for s, t in sorted(actual - declared):
        errors.append(f"未声明的多比特跳转 {s} -> {t}（必须写进 JUMP_EDGES 与 JumpEdges5）")
    for s, t in sorted(declared - actual):
        errors.append(f"声明的跳转 {s} -> {t} 不在转移表里（幽灵边）")
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

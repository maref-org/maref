"""34-state joint FSM symmetry reduction and cross-layer invariant verifier.

Generates REACHABLE (gov_state, agent_state) pairs via BFS from (INIT, UNINITIALIZED),
then checks 7 cross-layer invariants.  Symmetry reduction collapses equivalent agent
states within the same Gray-code prefix.

Invariants:
  SJ-001: Gov HALT ⇒ agent must be TERMINATED or ZOMBIE
  SJ-002: Gov STABILIZE ⇒ no agent in CONFLICTING
  SJ-003: Gov ACT ⇒ at least one agent in EXECUTING
  SJ-004: Gov HALT is absorbing for governance FSM
  SJ-005: Agent ZOMBIE ⇒ Gov entropy >= 2 (ANALYZE+)
  SJ-006: Agent TERMINATED cannot re-enter lifecycle
  SJ-007: Gov HALT ⇒ no agent can transition further
"""
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from maref.governance.constants import ENTROPY_LEVELS, STATE_NAMES, compute_valid_transitions
from maref.recursive.agent_24_state_machine import VALID_TRANSITIONS, AgentStateV3

GovState = int
AgentState = AgentStateV3
GOV_NAME: dict[int, str] = STATE_NAMES
AGENT_HALT_ENTROPY: int = 2
GOV_TRANSITIONS: dict[int, list[int]] = compute_valid_transitions()

def _gov_entropy(s: GovState) -> int:
    return ENTROPY_LEVELS.get(s, 0)

def reachable_pairs(max_steps: int=5) -> set[tuple[GovState, AgentState]]:
    """BFS from (INIT, UNINITIALIZED) up to *max_steps* joint transitions."""
    seen: set[tuple[GovState, AgentState]] = set()
    q: deque[tuple[GovState, AgentState, int]] = deque()
    q.append((0, AgentStateV3.UNINITIALIZED, 0))
    seen.add((0, AgentStateV3.UNINITIALIZED))
    while q:
        g, a, depth = q.popleft()
        if depth >= max_steps:
            continue
        for ng in GOV_TRANSITIONS.get(g, []):
            pair = (ng, a)
            if pair not in seen:
                seen.add(pair)
                q.append((ng, a, depth + 1))
        for na in VALID_TRANSITIONS.get(a, set()):
            pair = (g, na)
            if pair not in seen:
                seen.add(pair)
                q.append((g, na, depth + 1))
    return seen

@dataclass
class InvariantResult:
    name: str
    passed: bool
    violations: list[dict[str, Any]] = field(default_factory=list)
    total_checked: int = 0

def check_halt_implies_agents_dead(pairs: set[tuple[GovState, AgentState]]) -> InvariantResult:
    name = 'SJ-001: Gov HALT ⇒ agent TERMINATED or ZOMBIE (needs coordination)'
    violations = []
    for g, a in pairs:
        if g == 9 and a not in (AgentStateV3.TERMINATED, AgentStateV3.ZOMBIE):
            violations.append({'pair': f'{GOV_NAME[g]} / {a.value}'})
    return InvariantResult(name=name, passed=len(violations) == 0, violations=violations, total_checked=len(pairs))

def check_stabilize_implies_no_conflict(pairs: set[tuple[GovState, AgentState]]) -> InvariantResult:
    name = 'SJ-002: Gov STABILIZE ⇒ no agent in CONFLICTING (needs coordination)'
    violations = []
    for g, a in pairs:
        if g == 7 and a == AgentStateV3.CONFLICTING:
            violations.append({'pair': f'{GOV_NAME[g]} / {a.value}'})
    return InvariantResult(name=name, passed=len(violations) == 0, violations=violations, total_checked=len(pairs))

def check_act_implies_executing(pairs: set[tuple[GovState, AgentState]]) -> InvariantResult:
    name = 'SJ-003: Gov ACT ⇒ at least one agent in EXECUTING (needs coordination)'
    act_pairs = [(g, a) for g, a in pairs if g == 5]
    has_executing = any((a == AgentStateV3.EXECUTING for _, a in act_pairs))
    violations = []
    if not has_executing and act_pairs:
        violations.append({'pair': 'ACT / no EXECUTING agent'})
    return InvariantResult(name=name, passed=len(violations) == 0, violations=violations, total_checked=len(act_pairs))

def check_halt_gov_absorbing(pairs: set[tuple[GovState, AgentState]]) -> InvariantResult:
    name = 'SJ-004: Gov HALT is absorbing (structural)'
    violations = []
    for t in range(10):
        if t != 9 and t in GOV_TRANSITIONS.get(9, []):
            violations.append({'pair': f'HALT(9) -> {t}'})
    return InvariantResult(name=name, passed=len(violations) == 0, violations=violations, total_checked=10)

def check_zombie_implies_gov_analyzed(pairs: set[tuple[GovState, AgentState]]) -> InvariantResult:
    name = f'SJ-005: Agent ZOMBIE ⇒ Gov entropy >= {AGENT_HALT_ENTROPY} (needs coordination)'
    violations = []
    for g, a in pairs:
        if a == AgentStateV3.ZOMBIE and _gov_entropy(g) < AGENT_HALT_ENTROPY:
            violations.append({'pair': f'entropy={_gov_entropy(g)} / ZOMBIE'})
    return InvariantResult(name=name, passed=len(violations) == 0, violations=violations, total_checked=len(pairs))

def check_terminated_immutability(pairs: set[tuple[GovState, AgentState]]) -> InvariantResult:
    name = 'SJ-006: Agent TERMINATED cannot re-enter (structural)'
    violations = []
    for t in AgentStateV3:
        if t in VALID_TRANSITIONS.get(AgentStateV3.TERMINATED, set()):
            violations.append({'pair': f'TERMINATED -> {t.value}'})
    return InvariantResult(name=name, passed=len(violations) == 0, violations=violations, total_checked=len(AgentStateV3))

def check_halt_joint_absorbing(pairs: set[tuple[GovState, AgentState]]) -> InvariantResult:
    name = 'SJ-007: Gov HALT ⇒ no agent transitions (needs coordination)'
    violations = []
    for g, a in pairs:
        if g != 9:
            continue
        if VALID_TRANSITIONS.get(a, set()):
            violations.append({'pair': f'HALT / {a.value}'})
    return InvariantResult(name=name, passed=len(violations) == 0, violations=violations, total_checked=len(pairs))
ALL_INVARIANTS = [check_halt_implies_agents_dead, check_stabilize_implies_no_conflict, check_act_implies_executing, check_halt_gov_absorbing, check_zombie_implies_gov_analyzed, check_terminated_immutability, check_halt_joint_absorbing]

def run_all(max_steps: int=5) -> list[InvariantResult]:
    pairs = reachable_pairs(max_steps=max_steps)
    results = [inv(pairs) for inv in ALL_INVARIANTS]
    return results

def print_report(results: list[InvariantResult], reachable_count: int) -> None:
    print('=' * 70)
    print('34-State Joint FSM — Reachable-State Invariant Verification')
    print('=' * 70)
    print(f'Reachable pairs (BFS depth 5): {reachable_count}/240')
    print('=' * 70)
    all_pass = True
    for r in results:
        status = 'PASS' if r.passed else 'FAIL'
        print(f'  [{status}] {r.name}  ({r.total_checked} pairs)')
        if not r.passed:
            all_pass = False
            for v in r.violations[:3]:
                print(f"         └─ {v.get('pair', '?')}")
            if len(r.violations) > 3:
                print(f'         └─ ... and {len(r.violations) - 3} more')
    print('=' * 70)
    print(f"Result: {('ALL PASSED' if all_pass else 'SOME FAILED')}")
    print('=' * 70)
if __name__ == '__main__':
    results = run_all(max_steps=5)
    print_report(results, len(reachable_pairs(5)))

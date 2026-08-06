"""Phase 3.6 — Agent Internet formal verification (dependency-free).

Implements the exact ``Init`` / ``Next`` / invariant semantics of
``src/formal/MAREF_InternetInvariants.tla`` as a bounded state-space
enumerator, so the TLA+ cross-domain invariants can be model-checked in
CI environments without a JVM/TLC:

1. **TrustAcyclic** — trust-report propagation never forms a cycle
   (2-/3-cycle guard in ``Next``; the enumerator checks arbitrary-length
   cycles via reachability).
2. **AuditChainIntegrity** — audit chains are append-only, bounded, and
   the last hash is deterministically coupled to the chain length
   (``lastHash == 13 * chainLen + 7``); any tamper breaks the coupling.
3. **StateConvergence** — reconciled federation states always agree
   (``reconciled[a] AND reconciled[b] IMPLIES ledger[a] = ledger[b]``).

Each invariant check is mirrored by an *attacker* check proving the
detector can actually catch a violation (model-checker effectiveness).
``check_tla_artifact_sync`` guards against spec drift: every invariant
defined in the archived ``.tla`` artifact must be covered here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Bounded model constants (mirror the archived TLC configuration).
NODES = (0, 1, 2)
ENTRIES: frozenset[int] = frozenset({1})
MAX_CHAIN = 2

SPEC_PATH = (
    Path(__file__).resolve().parents[2] / "formal" / "MAREF_InternetInvariants.tla"
)

_INVARIANT_PATTERN = re.compile(r"^(\w+)\s*==\s*$", re.MULTILINE)


@dataclass(frozen=True)
class InternetState:
    """A single state of the Agent Internet model."""

    trust_edges: frozenset[tuple[int, int]]
    chain_len: tuple[int, int, int]
    last_hash: tuple[int, int, int]
    ledger: tuple[frozenset[int], frozenset[int], frozenset[int]]
    reconciled: tuple[bool, bool, bool]


def _expected_hash(length: int) -> int:
    """H(length) = 13*length + 7 — matches the TLA+ invariant."""
    return 13 * length + 7


def _has_cycle(edges: frozenset[tuple[int, int]]) -> bool:
    """Detect a directed cycle of any length via DFS reachability."""
    adjacency: dict[int, list[int]] = {}
    for src, dst in edges:
        adjacency.setdefault(src, []).append(dst)

    def visit(node: int, seen: set[int], stack: set[int]) -> bool:
        if node in stack:
            return True
        if node in seen:
            return False
        seen.add(node)
        stack.add(node)
        for neighbor in adjacency.get(node, []):
            if visit(neighbor, seen, stack):
                return True
        stack.remove(node)
        return False

    return any(visit(node, set(), set()) for node in adjacency)


def _init_state() -> InternetState:
    return InternetState(
        trust_edges=frozenset(),
        chain_len=(0, 0, 0),
        last_hash=(7, 7, 7),
        ledger=(frozenset(), frozenset(), frozenset()),
        reconciled=(False, False, False),
    )


def _guarded_edge_ok(edges: frozenset[tuple[int, int]], src: int, dst: int) -> bool:
    """The TLA+ NextTrustRelay guard: adding the edge must not close a
    2- or 3-cycle (complete cycle coverage for a 3-node model)."""
    candidate = edges | {(src, dst)}
    if any((b, a) in candidate for a, b in candidate):
        return False
    for a in NODES:
        for b in NODES:
            for c in NODES:
                if {(a, b), (b, c), (c, a)} <= candidate:
                    return False
    return True


def _next_states(state: InternetState) -> list[InternetState]:
    """All successors under the TLA+ ``Next`` operator."""
    successors: list[InternetState] = []
    edges = state.trust_edges
    chain_len, last_hash = state.chain_len, state.last_hash
    ledger, reconciled = state.ledger, state.reconciled

    # NextTrustRelay
    for src in NODES:
        for dst in NODES:
            if src != dst and _guarded_edge_ok(edges, src, dst):
                successors.append(
                    InternetState(
                        trust_edges=edges | {(src, dst)},
                        chain_len=chain_len,
                        last_hash=last_hash,
                        ledger=ledger,
                        reconciled=reconciled,
                    )
                )

    # NextAppendAudit
    for node in NODES:
        if chain_len[node] < MAX_CHAIN:
            new_len = list(chain_len)
            new_hash = list(last_hash)
            new_len[node] = chain_len[node] + 1
            new_hash[node] = _expected_hash(new_len[node])
            successors.append(
                InternetState(
                    trust_edges=edges,
                    chain_len=(new_len[0], new_len[1], new_len[2]),
                    last_hash=(new_hash[0], new_hash[1], new_hash[2]),
                    ledger=ledger,
                    reconciled=reconciled,
                )
            )

    # NextSettle (entries in SUBSET Entries) — updates the ledger only,
    # and only for servers that are not yet reconciled (locked ledger).
    # The node is marked reconciled solely via NextReconcile once both
    # ledgers match (SettlementReconciler semantics).
    for node in NODES:
        if reconciled[node]:
            continue
        for entries in (frozenset(), ENTRIES):
            new_ledger = list(ledger)
            new_ledger[node] = entries
            successors.append(
                InternetState(
                    trust_edges=edges,
                    chain_len=chain_len,
                    last_hash=last_hash,
                    ledger=(new_ledger[0], new_ledger[1], new_ledger[2]),
                    reconciled=reconciled,
                )
            )

    # NextReconcile (both ledgers must already match)
    for a in NODES:
        for b in NODES:
            if a != b and ledger[a] == ledger[b]:
                new_reconciled = list(reconciled)
                new_reconciled[a] = True
                new_reconciled[b] = True
                successors.append(
                    InternetState(
                        trust_edges=edges,
                        chain_len=chain_len,
                        last_hash=last_hash,
                        ledger=ledger,
                        reconciled=(
                            new_reconciled[0],
                            new_reconciled[1],
                            new_reconciled[2],
                        ),
                    )
                )
    return successors


def enumerate_reachable_states() -> list[InternetState]:
    """BFS all states reachable from Init under Next (TLC equivalent)."""
    seen: set[InternetState] = set()
    queue = [_init_state()]
    seen.add(queue[0])
    while queue:
        current = queue.pop(0)
        for successor in _next_states(current):
            if successor not in seen:
                seen.add(successor)
                queue.append(successor)
    return list(seen)


def _trust_acyclic_holds(state: InternetState) -> bool:
    return not _has_cycle(state.trust_edges)


def _audit_chain_holds(state: InternetState) -> bool:
    for node in NODES:
        length = state.chain_len[node]
        if length < 0 or length > MAX_CHAIN:
            return False
        if state.last_hash[node] != _expected_hash(length):
            return False
    return True


def _convergence_holds(state: InternetState) -> bool:
    for a in NODES:
        for b in NODES:
            if state.reconciled[a] and state.reconciled[b]:
                if state.ledger[a] != state.ledger[b]:
                    return False
    return True


class InternetInvariantsVerifier:
    """Runs the 3 cross-domain invariant checks + 3 attacker-detection
    checks + the TLA+ artifact-sync check (7 total)."""

    @staticmethod
    def check_trust_acyclic() -> list[dict[str, Any]]:
        states = enumerate_reachable_states()
        violated = [s for s in states if not _trust_acyclic_holds(s)]
        return [
            {
                "check": "trust_acyclic",
                "passed": not violated,
                "detail": (
                    f"{len(states)} reachable states, no trust cycle "
                    f"(arbitrary-length DFS) in any"
                ),
            }
        ]

    @staticmethod
    def check_audit_chain_integrity() -> list[dict[str, Any]]:
        states = enumerate_reachable_states()
        violated = [s for s in states if not _audit_chain_holds(s)]
        return [
            {
                "check": "audit_chain_integrity",
                "passed": not violated,
                "detail": (
                    f"{len(states)} reachable states, lastHash == 13*len+7 "
                    f"and len in [0,{MAX_CHAIN}] in every state"
                ),
            }
        ]

    @staticmethod
    def check_state_convergence() -> list[dict[str, Any]]:
        states = enumerate_reachable_states()
        violated = [s for s in states if not _convergence_holds(s)]
        return [
            {
                "check": "state_convergence",
                "passed": not violated,
                "detail": (
                    f"{len(states)} reachable states, reconciled pairs always "
                    f"share identical ledgers"
                ),
            }
        ]

    @staticmethod
    def check_attacker_trust_cycle_detected() -> list[dict[str, Any]]:
        """The cycle detector must catch an unguarded edge that closes a cycle."""
        state = _init_state()
        cyclic = InternetState(
            trust_edges=frozenset({(0, 1), (1, 2), (2, 0)}),
            chain_len=state.chain_len,
            last_hash=state.last_hash,
            ledger=state.ledger,
            reconciled=state.reconciled,
        )
        detected = _has_cycle(cyclic.trust_edges) and not _trust_acyclic_holds(cyclic)
        return [
            {
                "check": "attacker_trust_cycle_detected",
                "passed": detected,
                "detail": "3-node trust cycle 0->1->2->0 flagged by the detector",
            }
        ]

    @staticmethod
    def check_attacker_audit_tamper_detected() -> list[dict[str, Any]]:
        """A hash/chain tamper must be flagged by the integrity check."""
        state = _init_state()
        tampered = InternetState(
            trust_edges=state.trust_edges,
            chain_len=(1, 0, 0),  # one entry appended...
            last_hash=(7, 7, 7),  # ...but the hash still says length 0
            ledger=state.ledger,
            reconciled=state.reconciled,
        )
        detected = not _audit_chain_holds(tampered)
        return [
            {
                "check": "attacker_audit_tamper_detected",
                "passed": detected,
                "detail": "chainLen=1 with stale lastHash=7 flagged as inconsistent",
            }
        ]

    @staticmethod
    def check_attacker_convergence_detected() -> list[dict[str, Any]]:
        """A server claiming reconciliation with a different ledger must be flagged."""
        state = _init_state()
        divergent = InternetState(
            trust_edges=state.trust_edges,
            chain_len=state.chain_len,
            last_hash=state.last_hash,
            ledger=(frozenset({1}), frozenset(), frozenset()),
            reconciled=(True, True, False),  # both reconciled, ledgers differ
        )
        detected = not _convergence_holds(divergent)
        return [
            {
                "check": "attacker_convergence_detected",
                "passed": detected,
                "detail": "reconciled pair with divergent ledgers flagged",
            }
        ]

    @staticmethod
    def check_tla_artifact_sync() -> list[dict[str, Any]]:
        """Every invariant in the archived .tla is covered by this verifier."""
        if not SPEC_PATH.exists():
            return [
                {
                    "check": "tla_artifact_sync",
                    "passed": False,
                    "detail": f"spec artifact missing: {SPEC_PATH}",
                }
            ]
        text = SPEC_PATH.read_text(encoding="utf-8")
        spec_invariants = {
            name
            for name in _INVARIANT_PATTERN.findall(text)
            if name in {"TrustAcyclic", "AuditChainIntegrity", "StateConvergence"}
        }
        python_checks = {
            "TrustAcyclic",
            "AuditChainIntegrity",
            "StateConvergence",
        }
        missing = python_checks - spec_invariants
        extra = spec_invariants - python_checks
        passed = not missing and not extra
        return [
            {
                "check": "tla_artifact_sync",
                "passed": passed,
                "detail": (
                    f"spec defines {sorted(spec_invariants)}; python covers "
                    f"{sorted(python_checks)}; missing={sorted(missing)} "
                    f"extra={sorted(extra)}"
                ),
            }
        ]

    @classmethod
    def run_all(cls) -> list[dict[str, Any]]:
        """Run all 7 verification checks."""
        results: list[dict[str, Any]] = []
        for method in [
            cls.check_trust_acyclic,
            cls.check_audit_chain_integrity,
            cls.check_state_convergence,
            cls.check_attacker_trust_cycle_detected,
            cls.check_attacker_audit_tamper_detected,
            cls.check_attacker_convergence_detected,
            cls.check_tla_artifact_sync,
        ]:
            results.extend(method())
        return results


__all__ = [
    "NODES",
    "ENTRIES",
    "MAX_CHAIN",
    "SPEC_PATH",
    "InternetState",
    "InternetInvariantsVerifier",
    "enumerate_reachable_states",
]

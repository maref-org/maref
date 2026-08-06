"""Phase 3.6 — Agent Internet formal verification.

Model-checks the cross-domain invariants archived in
``src/formal/MAREF_InternetInvariants.tla`` via a dependency-free
state-space enumerator (TLC-equivalent semantics):

- **TrustAcyclic** — trust propagation never forms a cycle
- **AuditChainIntegrity** — audit chains are append-only and hash-consistent
- **StateConvergence** — reconciled federation states always agree

Acceptance: the invariant verification artifacts ship with the codebase —
the archived ``.tla`` spec, the enumerator, and these tests.  TLC itself
is run when a JVM is available; the enumerator provides the same
full-state coverage in CI without one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maref.formal.internet_invariants import (
    SPEC_PATH,
    InternetInvariantsVerifier,
    enumerate_reachable_states,
)

SPEC_INVARIANTS = {
    "TrustAcyclic",
    "AuditChainIntegrity",
    "StateConvergence",
}


def test_spec_artifact_published() -> None:
    """The TLA+ verification artifact ships with the codebase."""
    assert SPEC_PATH.exists()
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert "---- MODULE MAREF_InternetInvariants ----" in text
    for name in SPEC_INVARIANTS:
        assert name in text
    # TLC model-check configuration archived in the spec.
    assert "TLC model-check configuration (archived)" in text
    assert "INVARIANT TrustAcyclic" in text
    assert "INVARIANT StateConvergence" in text


class TestInternetInvariants:
    """7 formal verification checks via the enumerator."""

    def test_all_checks_pass(self) -> None:
        results = InternetInvariantsVerifier.run_all()
        assert len(results) == 7, f"Expected 7 checks, got {len(results)}"
        for result in results:
            assert result["passed"], f"FAILED: {result['check']} — {result['detail']}"
        print("\n  All 7 checks: PASSED")

    def test_trust_acyclic(self) -> None:
        results = InternetInvariantsVerifier.check_trust_acyclic()
        assert results[0]["passed"]

    def test_audit_chain_integrity(self) -> None:
        results = InternetInvariantsVerifier.check_audit_chain_integrity()
        assert results[0]["passed"]

    def test_state_convergence(self) -> None:
        results = InternetInvariantsVerifier.check_state_convergence()
        assert results[0]["passed"]

    def test_attacker_trust_cycle_detected(self) -> None:
        """The detector must catch a 3-node trust cycle."""
        results = InternetInvariantsVerifier.check_attacker_trust_cycle_detected()
        assert results[0]["passed"]

    def test_attacker_audit_tamper_detected(self) -> None:
        """A hash/chain tamper must be flagged."""
        results = InternetInvariantsVerifier.check_attacker_audit_tamper_detected()
        assert results[0]["passed"]

    def test_attacker_convergence_detected(self) -> None:
        """A falsely-reconciled pair with divergent ledgers must be flagged."""
        results = InternetInvariantsVerifier.check_attacker_convergence_detected()
        assert results[0]["passed"]

    def test_tla_artifact_sync(self) -> None:
        """Spec invariants and Python checks must stay in sync."""
        results = InternetInvariantsVerifier.check_tla_artifact_sync()
        assert results[0]["passed"], results[0]["detail"]


class TestModelSemantics:
    """Verify the enumerator reproduces the TLA+ guard semantics."""

    def test_init_matches_tla(self) -> None:
        states = enumerate_reachable_states()
        assert len(states) >= 1
        # Init: no edges, zero chains, hash H(0)=7, empty ledgers, unreconciled.
        assert any(
            not s.trust_edges
            and s.chain_len == (0, 0, 0)
            and s.last_hash == (7, 7, 7)
            and all(not l for l in s.ledger)
            and not any(s.reconciled)
            for s in states
        )

    def test_trust_guard_prevents_cycles(self) -> None:
        """No reachable state contains any directed cycle (any length)."""
        from maref.formal.internet_invariants import _has_cycle

        states = enumerate_reachable_states()
        assert all(not _has_cycle(s.trust_edges) for s in states)
        # The guarded graph must actually grow edges (guard not vacuous).
        assert any(len(s.trust_edges) >= 2 for s in states)

    def test_audit_chain_bounded(self) -> None:
        states = enumerate_reachable_states()
        assert all(0 <= s.chain_len[i] <= 2 for s in states for i in range(3))

    def test_reconcile_requires_matching_ledgers(self) -> None:
        """A pair may only be jointly reconciled when ledgers match."""
        states = enumerate_reachable_states()
        for s in states:
            for a in range(3):
                for b in range(3):
                    if s.reconciled[a] and s.reconciled[b]:
                        assert s.ledger[a] == s.ledger[b]

    def test_enumerator_explores_meaningful_state_space(self) -> None:
        states = enumerate_reachable_states()
        assert len(states) >= 100, f"only {len(states)} states explored"
        # Both reconciliation outcomes are reachable.
        assert any(all(s.reconciled) for s in states)
        assert any(not any(s.reconciled) for s in states)


@pytest.mark.skipif(
    not Path("/usr/bin/tlc").exists() and not Path("/opt/tla/tlc").exists(),
    reason="TLC not available in this environment (zero-external-dependency CI)",
)
def test_tlc_model_check_artifact() -> None:
    """When a JVM/TLC is present, the archived spec must pass model checking."""
    import subprocess

    result = subprocess.run(
        ["tlc", "-workers", "4", str(SPEC_PATH)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert "No error has been found" in result.stdout, result.stdout[-2000:]

"""v0.47 S9 — TrustBoundaryManager injected into GovernancePipeline.

``GovernancePipeline`` gains an optional ``boundary`` parameter.  When
provided, ``govern()`` enforces the trust boundary as a mandatory gate
before the rest of the 8-step pipeline: an out-of-bounds action is denied
(fail-closed, ``E1006`` semantics surfaced as ``Verdict.DENY`` with
``matched_rule="trust_boundary"``).

When no boundary is injected the pipeline keeps its historical behaviour
(backward compatible).

Also verifies the new module is exported from ``maref.governance`` and the
legacy ``maref.security.trust_boundary`` module emits a deprecation warning.
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest

from maref.governance import (
    BoundaryDecision,
    BoundaryViolationError,
    GovernancePipeline,
    GovernanceRequest,
    TrustBoundaryManager,
    Verdict,
)
from maref.governance.core_pipeline import GovernanceResult


def _boundary(**kwargs: Any) -> TrustBoundaryManager:
    return TrustBoundaryManager(**kwargs)


# ── Injection into GovernancePipeline ─────────────────────────────────────


def test_boundary_injected_denies_out_of_bounds_action() -> None:
    """A HIGH-risk action with no scope is denied (fail-closed)."""
    pipe = GovernancePipeline(boundary=_boundary())
    result = pipe.govern(
        GovernanceRequest(
            action="file.delete", agent_id="agent-a", trust_score=90, role=""
        )
    )
    assert result.verdict == Verdict.DENY
    assert result.matched_rule == "trust_boundary"
    assert "boundary" in result.reason.lower() or "fail-closed" in result.reason.lower()


def test_boundary_injected_allows_in_scope_action() -> None:
    """A LOW-risk in-scope action passes the boundary gate."""
    pipe = GovernancePipeline(boundary=_boundary())
    result = pipe.govern(
        GovernanceRequest(
            action="file.read", agent_id="agent-a", trust_score=80, role=""
        )
    )
    assert result.verdict == Verdict.ALLOW


def test_boundary_gate_runs_before_other_rules() -> None:
    """Boundary denial short-circuits (matched_rule is trust_boundary, not a
    policy rule)."""
    pipe = GovernancePipeline(boundary=_boundary())
    result = pipe.govern(
        GovernanceRequest(
            action="payment:transfer", agent_id="agent-a", trust_score=95, role=""
        )
    )
    assert result.verdict == Verdict.DENY
    assert result.matched_rule == "trust_boundary"


def test_boundary_denied_action_records_audit_callback() -> None:
    """The audit callback still fires for a boundary-denied request."""
    audit_events: list[tuple[GovernanceRequest, GovernanceResult]] = []

    def on_audit(req: GovernanceRequest, result: GovernanceResult) -> None:
        audit_events.append((req, result))

    pipe = GovernancePipeline(boundary=_boundary(), audit_callback=on_audit)
    pipe.govern(
        GovernanceRequest(
            action="file.delete", agent_id="agent-a", trust_score=90, role=""
        )
    )
    assert len(audit_events) == 1
    assert audit_events[0][1].verdict == Verdict.DENY


def test_no_boundary_injected_backward_compatible() -> None:
    """Without a boundary the pipeline behaves exactly as before."""
    pipe = GovernancePipeline()
    result = pipe.govern(
        GovernanceRequest(
            action="file.read", agent_id="agent-a", trust_score=90, role=""
        )
    )
    assert result.verdict == Verdict.ALLOW


def test_boundary_with_scope_allows_high_risk() -> None:
    """A HIGH-risk action explicitly allowed by the scope passes."""
    from maref.identity.credential import AuthorizationScope

    scope = AuthorizationScope(
        subject_did="agent-a",
        max_risk_level="HIGH",
        allowed_actions=["file.delete"],
    )
    pipe = GovernancePipeline(boundary=_boundary(scope=scope))
    result = pipe.govern(
        GovernanceRequest(
            action="file.delete", agent_id="agent-a", trust_score=90, role=""
        )
    )
    assert result.verdict == Verdict.ALLOW


# ── Module exports + legacy deprecation ────────────────────────────────────


def test_governance_exports_trust_boundary_symbols() -> None:
    assert TrustBoundaryManager is not None
    assert BoundaryDecision is not None
    assert BoundaryViolationError is not None


def test_legacy_security_trust_boundary_deprecated() -> None:
    """Importing the legacy module emits a DeprecationWarning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import maref.security.trust_boundary  # noqa: F401

    assert any(issubclass(w.category, DeprecationWarning) for w in caught), (
        "legacy maref.security.trust_boundary must emit DeprecationWarning"
    )

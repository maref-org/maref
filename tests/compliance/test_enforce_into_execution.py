"""v0.47 R1 — regulatory ENFORCE wired into execution preflight.

1. ``RiskAuthorizationCheck`` consults the regulatory mapper: an action
   whose jurisdiction maps to ENFORCE is hard-gated through the trust
   boundary (unauthorized → FAIL, not a soft pass).
2. Unknown jurisdictions fail closed to the strictest enforcement level
   (ENFORCE), not the loose fail-open default.
"""

from __future__ import annotations

from maref.compliance.jurisdiction_profile import EnforcementLevel, get_profile
from maref.compliance.regulatory_policy_mapper import RegulatoryPolicyMapper
from maref.governance.task_preflight import (
    PreflightCheckStatus,
    RiskAuthorizationCheck,
)


class TestUnknownJurisdictionFailClosed:
    def test_unknown_jurisdiction_maps_to_enforce(self) -> None:
        """Unknown jurisdiction → strictest enforcement (fail-closed)."""
        mapper = RegulatoryPolicyMapper()
        decision = mapper.map_action("payment:transfer", jurisdiction="unknown-xx")
        assert decision.enforcement == EnforcementLevel.ENFORCE
        assert decision.blocked is True

    def test_unknown_jurisdiction_profile_defaults_strict(self) -> None:
        profile = get_profile("unknown-xx")
        from maref.governance.risk_classifier import RiskLevel

        # Every risk level on an unknown profile must be ENFORCE (not OBSERVE).
        for risk in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.IRREVERSIBLE):
            assert profile.enforcement_for_risk(risk) == EnforcementLevel.ENFORCE


class TestEnforceWiredIntoPreflight:
    def test_enforce_action_requires_authorization(self) -> None:
        """An ENFORCE-class action with no scope fails the preflight."""
        check = RiskAuthorizationCheck()
        result = check.execute(
            {
                "action": "payment:transfer",
                "agent_id": "agent-01",
                "jurisdiction": "eu",
            }
        )
        assert result.status == PreflightCheckStatus.FAIL

    def test_enforce_authorized_action_passes(self) -> None:
        """An ENFORCE action explicitly authorized by scope passes."""
        from maref.identity.credential import AuthorizationScope

        check = RiskAuthorizationCheck()
        scope = AuthorizationScope(
            subject_did="agent-01",
            max_risk_level="IRREVERSIBLE",
            allowed_actions=["payment:transfer"],
        )
        result = check.execute(
            {
                "action": "payment:transfer",
                "agent_id": "agent-01",
                "jurisdiction": "eu",
                "authorization_scope": scope,
            }
        )
        assert result.status == PreflightCheckStatus.PASS

    def test_enforce_decision_blocked_flag(self) -> None:
        """ENFORCE-level actions are flagged blocked by the mapper."""
        mapper = RegulatoryPolicyMapper()
        decision = mapper.map_action("payment:transfer", jurisdiction="eu")
        assert decision.blocked is True

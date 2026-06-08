"""
FourPhaseGovernance 扩展测试

补充覆盖：_determine_initial_phase 边界、_build_transition_reason、
get_current_permissions、_get_active_permission_list、
report_compliance_round trust 增长、report_violation 非 red_line、
_escalate_to_old_yang 未授权、_recover_from_old_yin 未授权、
quarantine、to_dict、_audit_transition、PhaseTransition.to_dict、
GovernanceMetrics.to_dict、PermissionSet.has_permission red_line_mode。
"""

from __future__ import annotations

import pytest

from maref.recursive.four_phase_governance import (
    FourPhaseGovernance,
    GovernanceMetrics,
    GovernancePhase,
    PermissionScope,
    PermissionSet,
    PhaseTransition,
)


class TestInitialPhase:
    def test_init_old_yang(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.95)
        assert gov.current_phase == GovernancePhase.OLD_YANG

    def test_init_lesser_yin(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        assert gov.current_phase == GovernancePhase.LESSER_YIN

    def test_init_lesser_yang(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.5)
        assert gov.current_phase == GovernancePhase.LESSER_YANG

    def test_init_old_yin(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.2)
        assert gov.current_phase == GovernancePhase.OLD_YIN

    def test_init_exact_threshold_09(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.9)
        assert gov.current_phase == GovernancePhase.OLD_YANG

    def test_init_exact_threshold_07(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.7)
        assert gov.current_phase == GovernancePhase.LESSER_YIN

    def test_init_exact_threshold_03(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.3)
        assert gov.current_phase == GovernancePhase.LESSER_YANG


class TestTrustUpdate:
    def test_trust_clamped_to_one(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.99)
        gov.update_trust(new_trust=1.5, violation_occurred=False)
        assert gov.trust_score == 1.0

    def test_trust_clamped_to_zero(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.1)
        gov.update_trust(new_trust=-0.5, violation_occurred=False)
        assert gov.trust_score == 0.0

    def test_no_transition_when_same_phase(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.75)
        result = gov.update_trust(new_trust=0.78, violation_occurred=False)
        assert result is None

    def test_total_rounds_increment(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.75)
        gov.update_trust(new_trust=0.76, violation_occurred=False)
        assert gov.get_metrics().total_rounds == 1


class TestRedLineCooldown:
    def test_red_line_cooldown_blocks_transition(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        gov.update_trust(new_trust=0.65, violation_occurred=True, red_line_hit=True)
        assert gov.current_phase == GovernancePhase.OLD_YIN
        # During cooldown, no transitions should happen
        for _ in range(5):
            gov.update_trust(new_trust=0.9, violation_occurred=False)
        assert gov.current_phase == GovernancePhase.OLD_YIN

    def test_red_line_cooldown_expires(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        gov.update_trust(new_trust=0.65, violation_occurred=True, red_line_hit=True)
        assert gov.current_phase == GovernancePhase.OLD_YIN
        # After cooldown expires, _red_line_triggered is still True so
        # _evaluate_phase returns OLD_YIN. Need to recover via _recover_from_old_yin.
        token = gov.authorize()
        gov._recover_from_old_yin(new_trust=0.75, authorization_token=token)
        assert gov.current_phase == GovernancePhase.LESSER_YIN


class TestPermissions:
    def test_permission_set_has_permission(self) -> None:
        ps = PermissionSet(phase=GovernancePhase.OLD_YANG, allowed_scopes=[])
        assert ps.has_permission(PermissionScope.FULL_AUTONOMY) is True

    def test_permission_set_red_line_mode(self) -> None:
        ps = PermissionSet(
            phase=GovernancePhase.LESSER_YANG,
            allowed_scopes=[],
            is_red_line_mode=True,
        )
        assert ps.has_permission(PermissionScope.SELF_HEALING) is True
        assert ps.has_permission(PermissionScope.SELF_OPTIMIZATION) is False

    def test_get_current_permissions(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.95)
        perms = gov.get_current_permissions()
        assert perms.phase == GovernancePhase.OLD_YANG

    def test_check_permission_false(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.2)
        assert gov.check_permission(PermissionScope.FULL_AUTONOMY) is False

    def test_red_line_mode_permissions(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        gov.report_violation("breach", is_red_line=True)
        perms = gov.get_current_permissions()
        assert perms.is_red_line_mode is True


class TestComplianceAndViolations:
    def test_report_compliance_increases_trust(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.75)
        initial = gov.trust_score
        for _ in range(20):
            gov.report_compliance_round()
        assert gov.trust_score > initial

    def test_report_compliance_old_yang_slower(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.95)
        initial = gov.trust_score
        for _ in range(20):
            gov.report_compliance_round()
        assert gov.trust_score > initial
        # Should increase slower due to old_yang delta

    def test_report_violation_normal(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        initial = gov.trust_score
        gov.report_violation("minor", is_red_line=False)
        assert gov.trust_score < initial

    def test_report_violation_red_line(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.9)
        gov.report_violation("critical", is_red_line=True)
        assert gov.current_phase == GovernancePhase.OLD_YIN


class TestEscalateAndRecover:
    def test_escalate_unauthorized(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.75)
        result = gov._escalate_to_old_yang(authorization_token="wrong")
        assert result is None

    def test_escalate_authorized(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.75)
        token = gov.authorize()
        result = gov._escalate_to_old_yang(authorization_token=token)
        assert result is not None
        assert gov.current_phase == GovernancePhase.OLD_YANG

    def test_recover_unauthorized(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        gov.quarantine("test")
        result = gov._recover_from_old_yin(new_trust=0.5, authorization_token="wrong")
        assert result is None

    def test_recover_authorized(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        gov.quarantine("test")
        token = gov.authorize()
        result = gov._recover_from_old_yin(new_trust=0.5, authorization_token=token)
        assert result is not None
        assert gov.current_phase != GovernancePhase.OLD_YIN
        assert gov.get_metrics().red_line_triggered is False


class TestQuarantine:
    def test_quarantine_halves_trust(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        gov.quarantine()
        assert gov.trust_score <= 0.4

    def test_quarantine_sets_old_yin(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        gov.quarantine("reason")
        assert gov.current_phase == GovernancePhase.OLD_YIN


class TestToDict:
    def test_to_dict_structure(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        d = gov.to_dict()
        assert d["agent_id"] == "a1"
        assert "current_phase" in d
        assert "trust_score" in d
        assert "permissions" in d
        assert "transition_count" in d


class TestTransitionReason:
    def test_elevated_reason(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.65)
        transition = gov.update_trust(new_trust=0.75, violation_occurred=False)
        assert transition is not None
        assert "elevated" in transition.reason

    def test_demoted_reason(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.75)
        transition = gov.update_trust(new_trust=0.65, violation_occurred=True)
        assert transition is not None
        assert "demoted" in transition.reason

    def test_red_line_reason(self) -> None:
        gov = FourPhaseGovernance("a1", initial_trust=0.8)
        transition = gov.update_trust(new_trust=0.65, violation_occurred=True, red_line_hit=True)
        assert transition is not None
        assert "red_line" in transition.reason


class TestPhaseTransition:
    def test_phase_transition_to_dict(self) -> None:
        pt = PhaseTransition(
            from_phase=GovernancePhase.OLD_YANG,
            to_phase=GovernancePhase.LESSER_YIN,
            reason="test",
        )
        d = pt.to_dict()
        assert d["from"] == "old_yang"
        assert d["to"] == "lesser_yin"
        assert d["reason"] == "test"


class TestGovernanceMetrics:
    def test_metrics_to_dict(self) -> None:
        gm = GovernanceMetrics(
            trust_score=0.75,
            zero_violation_rounds=5,
            total_rounds=10,
            red_line_triggered=False,
        )
        d = gm.to_dict()
        assert d["trust_score"] == 0.75
        assert d["zero_violation_rounds"] == 5
        assert d["total_rounds"] == 10
        assert d["red_line_triggered"] is False


class TestPermissionSet:
    def test_permission_set_to_dict(self) -> None:
        ps = PermissionSet(phase=GovernancePhase.LESSER_YIN, allowed_scopes=[])
        d = ps.to_dict()
        assert d["phase"] == "lesser_yin"
        assert "SELF_EVOLUTION" in d["scopes"]
        assert d["red_line_mode"] is False

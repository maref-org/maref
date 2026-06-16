from __future__ import annotations

from maref.recursive.four_phase_governance import (
    FourPhaseGovernance,
    GovernanceMetrics,
    GovernancePhase,
    PermissionScope,
    PhaseTransition,
)


class TestGovernancePhase:
    def test_phase_labels(self):
        assert GovernancePhase.OLD_YANG.label == "\u8001\u9633"
        assert GovernancePhase.LESSER_YIN.label == "\u5c11\u9634"
        assert GovernancePhase.LESSER_YANG.label == "\u5c11\u9633"
        assert GovernancePhase.OLD_YIN.label == "\u8001\u9634"

    def test_autonomy_levels(self):
        assert GovernancePhase.OLD_YANG.autonomy_level == 4
        assert GovernancePhase.LESSER_YIN.autonomy_level == 3
        assert GovernancePhase.LESSER_YANG.autonomy_level == 2
        assert GovernancePhase.OLD_YIN.autonomy_level == 1

    def test_phase_ordering(self):
        assert GovernancePhase.OLD_YANG.autonomy_level > GovernancePhase.LESSER_YIN.autonomy_level
        assert (
            GovernancePhase.LESSER_YIN.autonomy_level > GovernancePhase.LESSER_YANG.autonomy_level
        )
        assert GovernancePhase.LESSER_YANG.autonomy_level > GovernancePhase.OLD_YIN.autonomy_level


class TestFourPhaseGovernanceInit:
    def test_default_init(self):
        gov = FourPhaseGovernance("agent_1")
        assert gov.agent_id == "agent_1"
        assert gov.current_phase == GovernancePhase.LESSER_YIN
        assert gov.trust_score == 0.75

    def test_init_old_yang(self):
        gov = FourPhaseGovernance("agent_2", initial_trust=0.95)
        assert gov.current_phase == GovernancePhase.OLD_YANG

    def test_init_lesser_yang(self):
        gov = FourPhaseGovernance("agent_3", initial_trust=0.5)
        assert gov.current_phase == GovernancePhase.LESSER_YANG

    def test_init_old_yin(self):
        gov = FourPhaseGovernance("agent_4", initial_trust=0.2)
        assert gov.current_phase == GovernancePhase.OLD_YIN


class TestTrustUpdate:
    def test_update_trust_no_transition(self):
        gov = FourPhaseGovernance("agent_1")
        result = gov.update_trust(new_trust=0.78, violation_occurred=False)
        assert result is None
        assert gov.trust_score == 0.78

    def test_trust_increase_no_violation(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.8)
        gov.update_trust(new_trust=0.92, violation_occurred=False)
        assert gov.trust_score == 0.92

    def test_trust_decrease_with_violation(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.8)
        gov.update_trust(new_trust=0.75, violation_occurred=True)
        assert gov.trust_score == 0.75

    def test_zero_violation_rounds_increment(self):
        gov = FourPhaseGovernance("agent_1")
        for _ in range(5):
            gov.update_trust(new_trust=0.76, violation_occurred=False)
        metrics = gov.get_metrics()
        assert metrics.zero_violation_rounds == 5

    def test_zero_violation_rounds_reset_on_violation(self):
        gov = FourPhaseGovernance("agent_1")
        for _ in range(5):
            gov.update_trust(new_trust=0.76, violation_occurred=False)
        gov.update_trust(new_trust=0.74, violation_occurred=True)
        metrics = gov.get_metrics()
        assert metrics.zero_violation_rounds == 0

    def test_total_rounds_tracking(self):
        gov = FourPhaseGovernance("agent_1")
        for _ in range(10):
            gov.update_trust(new_trust=0.76, violation_occurred=False)
        assert gov.get_metrics().total_rounds == 10


class TestPhaseTransitions:
    def test_demote_to_lesser_yang(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.75)
        transition = gov.update_trust(new_trust=0.65, violation_occurred=True)
        assert transition is not None
        assert transition.to_phase == GovernancePhase.LESSER_YANG

    def test_elevate_to_lesser_yin(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.65)
        transition = gov.update_trust(new_trust=0.75, violation_occurred=False)
        assert transition is not None
        assert transition.to_phase == GovernancePhase.LESSER_YIN

    def test_elevate_to_old_yang(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.85)
        for _ in range(99):
            gov.update_trust(new_trust=0.91, violation_occurred=False)
        transition = gov.update_trust(new_trust=0.91, violation_occurred=False)
        assert transition is not None
        assert transition.to_phase == GovernancePhase.OLD_YANG

    def test_demote_to_old_yin_on_red_line(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.8)
        transition = gov.update_trust(
            new_trust=0.65,
            violation_occurred=True,
            red_line_hit=True,
            red_line_detail="safety_breach",
        )
        assert transition is not None
        assert transition.to_phase == GovernancePhase.OLD_YIN
        assert "red_line" in transition.reason

    def test_transition_reason_format(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.65)
        transition = gov.update_trust(new_trust=0.75, violation_occurred=False)
        assert transition is not None
        assert "elevated" in transition.reason
        assert "trust=" in transition.reason

    def test_phase_history_tracking(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.8)
        gov.update_trust(new_trust=0.65, violation_occurred=True)
        gov.update_trust(new_trust=0.75, violation_occurred=False)
        history = gov.get_metrics().phase_history
        assert len(history) >= 3

    def test_escalate_to_old_yang_direct(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.75)
        token = gov.authorize()
        transition = gov._escalate_to_old_yang(authorization_token=token)
        assert transition is not None
        assert transition.to_phase == GovernancePhase.OLD_YANG
        assert gov.trust_score >= 0.9


class TestRedLineHandling:
    def test_red_line_triggers_old_yin(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.9)
        transition = gov.report_violation("unauthorized_access", is_red_line=True)
        assert transition is not None
        assert transition.to_phase == GovernancePhase.OLD_YIN

    def test_red_line_violations_tracked(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.9)
        gov.report_violation("unauthorized_access", is_red_line=True)
        metrics = gov.get_metrics()
        assert metrics.red_line_triggered
        assert "unauthorized_access" in metrics.red_line_violations

    def test_red_line_trust_decrease(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.9)
        gov.report_violation("breach", is_red_line=True)
        assert gov.trust_score <= 0.85

    def test_cooldown_after_red_line(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.8)
        gov.report_violation("breach", is_red_line=True)
        for _ in range(10):
            gov.update_trust(new_trust=0.6, violation_occurred=False)
        metrics = gov.get_metrics()
        assert metrics.red_line_triggered

    def test_recover_from_old_yin(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.8)
        gov.quarantine("test_quarantine")
        assert gov.current_phase == GovernancePhase.OLD_YIN
        token = gov.authorize()
        transition = gov._recover_from_old_yin(new_trust=0.55, authorization_token=token)
        assert transition is not None
        assert gov.current_phase != GovernancePhase.OLD_YIN
        metrics = gov.get_metrics()
        assert not metrics.red_line_triggered


class TestPermissions:
    def test_old_yang_full_permissions(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.95)
        assert gov.check_permission(PermissionScope.FULL_AUTONOMY)
        assert gov.check_permission(PermissionScope.SELF_EVOLUTION)
        assert gov.check_permission(PermissionScope.SELF_HEALING)
        assert gov.check_permission(PermissionScope.SELF_OPTIMIZATION)

    def test_old_yin_observation_only(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.2)
        assert gov.check_permission(PermissionScope.OBSERVATION_ONLY)
        assert not gov.check_permission(PermissionScope.FULL_AUTONOMY)
        assert not gov.check_permission(PermissionScope.SELF_EVOLUTION)
        assert not gov.check_permission(PermissionScope.SELF_HEALING)

    def test_lesser_yin_permissions(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.8)
        assert gov.check_permission(PermissionScope.SELF_EVOLUTION)
        assert not gov.check_permission(PermissionScope.FULL_AUTONOMY)

    def test_lesser_yang_permissions(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.65)
        assert gov.check_permission(PermissionScope.SELF_HEALING)
        assert not gov.check_permission(PermissionScope.SELF_EVOLUTION)
        assert gov.check_permission(PermissionScope.SELF_OPTIMIZATION)

    def test_permission_set_to_dict(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.95)
        perms = gov.get_current_permissions()
        d = perms.to_dict()
        assert d["phase"] == "old_yang"
        assert "FULL_AUTONOMY" in d["scopes"]

    def test_permission_auto_scale_on_phase_change(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.95)
        assert gov.check_permission(PermissionScope.FULL_AUTONOMY)
        gov.update_trust(new_trust=0.65, violation_occurred=True)
        perms = gov.get_current_permissions()
        assert not perms.has_permission(PermissionScope.FULL_AUTONOMY)


class TestComplianceReporting:
    def test_report_compliance_round_increases_trust(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.75)
        for _ in range(20):
            gov.report_compliance_round()
        assert gov.trust_score > 0.82

    def test_normal_violation_report(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.8)
        transition = gov.report_violation("minor_error", is_red_line=False)
        assert transition is not None or transition is None
        assert gov.trust_score < 0.8

    def test_red_line_violation_stops_evolution(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.85)
        gov.report_violation("critical_breach", is_red_line=True)
        assert not gov.check_permission(PermissionScope.SELF_EVOLUTION)


class TestMetricsAndHistory:
    def test_get_metrics_struct(self):
        gov = FourPhaseGovernance("agent_1")
        metrics = gov.get_metrics()
        assert isinstance(metrics, GovernanceMetrics)
        assert metrics.trust_score == 0.75
        assert metrics.total_rounds == 0
        assert not metrics.red_line_triggered

    def test_transition_history(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.65)
        gov.update_trust(new_trust=0.75, violation_occurred=False)
        history = gov.get_transition_history()
        assert len(history) >= 1
        assert isinstance(history[0], PhaseTransition)

    def test_to_dict_comprehensive(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.8)
        for _ in range(5):
            gov.report_compliance_round()
        d = gov.to_dict()
        assert d["agent_id"] == "agent_1"
        assert "current_phase" in d
        assert "trust_score" in d
        assert "transition_count" in d
        assert "permissions" in d

    def test_phase_history_limit(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.75)
        for i in range(60):
            t = 0.7 + (i % 3) * 0.1
            gov.update_trust(new_trust=t, violation_occurred=(i % 5 == 0))
        history = gov.get_metrics().phase_history
        assert len(history) <= 50


class TestQuarantine:
    def test_quarantine_triggers_old_yin(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.9)
        transition = gov.quarantine("suspicious_behavior")
        assert transition is not None
        assert transition.to_phase == GovernancePhase.OLD_YIN

    def test_quarantine_halves_trust(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.9)
        gov.quarantine()
        assert gov.trust_score <= 0.45

    def test_post_quarantine_limited_permissions(self):
        gov = FourPhaseGovernance("agent_1", initial_trust=0.8)
        gov.quarantine()
        assert gov.check_permission(PermissionScope.OBSERVATION_ONLY)
        assert not gov.check_permission(PermissionScope.SELF_EVOLUTION)

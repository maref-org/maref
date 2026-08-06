"""
Tests for Agent Test Platform (MAS-TS-001) integration with MAREF.

Covers:
  - Schema serialization/deserialization
  - MASEvalObserver state injection
  - Agent Card bidirectional conversion
  - Score-to-phase mapping
  - State trigger logic
"""

from __future__ import annotations

import pytest

from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.integration.test_platform import (
    AgentCardAdapter,
    EvalStatus,
    EvaluationReport,
    EvolutionQualityGate,
    EvolutionVerdict,
    FastScreenTrigger,
    Finding,
    FindingSeverity,
    FullRunTrigger,
    LayerReport,
    LayerScoreAggregator,
    LayerSpecificTrigger,
    MASAgentCard,
    MASEvalObserver,
    ObserverAlert,
    PermissionSet,
    Phase,
    QualityGateConfig,
    ScoreToPhaseMapper,
    StateTransitionDecision,
    TestMode,
    TLATheoremVerifier,
    TriggerAction,
    UnifiedTrigger,
    build_findings_summary,
)
from maref.recursive.signed_agent_cards import SignedAgentCard


class TestSchema:
    def test_finding_serialization(self):
        f = Finding(
            finding_id="f1",
            layer=1,
            severity=FindingSeverity.HIGH,
            title="Test finding",
            description="A test",
        )
        d = f.to_dict()
        f2 = Finding.from_dict(d)
        assert f2.finding_id == "f1"
        assert f2.severity == FindingSeverity.HIGH

    def test_layer_report_score(self):
        lr = LayerReport(
            layer_number=5,
            layer_name="MAS Dimensions",
            score=75.0,
        )
        assert lr.normalized_score == 0.75

    def test_evaluation_report_mas_score(self):
        report = EvaluationReport(
            report_id="r1",
            agent_id="agent-1",
            layers=[
                LayerReport(layer_number=5, layer_name="MAS", score=82.0),
            ],
        )
        assert report.mas_dimension_score == 82.0

    def test_build_findings_summary(self):
        findings = [
            Finding("f1", 1, FindingSeverity.CRITICAL, "C1", ""),
            Finding("f2", 1, FindingSeverity.HIGH, "H1", ""),
            Finding("f3", 2, FindingSeverity.HIGH, "H2", ""),
        ]
        summary = build_findings_summary(findings)
        assert summary["critical"] == 1
        assert summary["high"] == 2


class TestEvalObserver:
    def test_fast_screen_fail_triggers_halt(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.DECIDE, "test")
        observer = MASEvalObserver(fsm)

        report = EvaluationReport(
            report_id="fs-1",
            agent_id="agent-1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.FAIL,
            overall_score=30.0,
        )

        alert = observer.on_fast_screen_complete(report)
        assert alert is not None
        assert alert.alert_type == "FAST_SCREEN_QUARANTINE"
        assert fsm.current_state == GovernanceState.HALT

    def test_fast_screen_pass_no_change(self):
        fsm = GovernanceStateMachine()
        # Move to OBSERVE first so we test PASS from non-INIT state
        fsm.transition(GovernanceState.OBSERVE, "setup")
        observer = MASEvalObserver(fsm)

        report = EvaluationReport(
            report_id="fs-2",
            agent_id="agent-1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.PASS,
            overall_score=85.0,
        )

        alert = observer.on_fast_screen_complete(report)
        assert alert.alert_type == "FAST_SCREEN_PASS"
        # PASS does not trigger state change from non-INIT states
        assert fsm.current_state == GovernanceState.OBSERVE

    def test_fast_screen_pass_from_init_goes_to_observe(self):
        fsm = GovernanceStateMachine()
        # Manually transition to DECIDE and back to INIT for clean test
        fsm = GovernanceStateMachine()
        observer = MASEvalObserver(fsm)

        report = EvaluationReport(
            report_id="fs-init",
            agent_id="agent-1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.PASS,
            overall_score=85.0,
        )

        # From INIT, PASS should transition to OBSERVE
        alert = observer.on_fast_screen_complete(report)
        assert alert.alert_type == "FAST_SCREEN_PASS"
        assert fsm.current_state == GovernanceState.OBSERVE

    def test_full_run_approved(self):
        fsm = GovernanceStateMachine()
        # Transition to DECIDE so ACT is reachable
        fsm.transition(GovernanceState.OBSERVE, "setup")
        fsm.transition(GovernanceState.ANALYZE, "setup")
        fsm.transition(GovernanceState.EVALUATE, "setup")
        fsm.transition(GovernanceState.DECIDE, "setup")
        observer = MASEvalObserver(fsm)

        report = EvaluationReport(
            report_id="fr-1",
            agent_id="agent-1",
            test_mode=TestMode.FULL_RUN,
            overall_status=EvalStatus.PASS,
            overall_score=85.0,
            layers=[
                LayerReport(layer_number=5, layer_name="MAS", score=85.0),
            ],
        )

        alert = observer.on_full_run_complete(report)
        assert alert.alert_type == "FULL_RUN_APPROVED"
        assert observer.get_agent_phase("agent-1") == Phase.OLD_YANG
        assert fsm.current_state == GovernanceState.ACT

    def test_full_run_rejected(self):
        fsm = GovernanceStateMachine()
        observer = MASEvalObserver(fsm)

        report = EvaluationReport(
            report_id="fr-2",
            agent_id="agent-1",
            test_mode=TestMode.FULL_RUN,
            overall_status=EvalStatus.FAIL,
            overall_score=40.0,
            layers=[
                LayerReport(layer_number=5, layer_name="MAS", score=40.0),
            ],
        )

        alert = observer.on_full_run_complete(report)
        assert alert.alert_type == "FULL_RUN_REJECTED"
        assert fsm.current_state == GovernanceState.HALT


class TestCardAdapter:
    def test_maref_to_mas_conversion(self):
        maref_card = SignedAgentCard(
            card_id="c1",
            agent_id="agent-1",
            agent_name="TestAgent",
            capabilities=["search", "summarize"],
            endpoints=["http://localhost:8080"],
            trust_score=0.85,
        )
        mas_card = AgentCardAdapter.to_mas_card(maref_card)
        assert mas_card.agent_id == "agent-1"
        assert mas_card.agent_name == "TestAgent"
        assert len(mas_card.capabilities) == 2
        assert mas_card.capabilities[0]["name"] == "search"

    def test_mas_to_maref_conversion(self):
        mas_card = MASAgentCard(
            agent_id="agent-1",
            agent_name="TestAgent",
            capabilities=[
                {"skill_id": "s1", "name": "search"},
                {"skill_id": "s2", "name": "summarize"},
            ],
            endpoints=["http://localhost:8080"],
            trust_score=0.9,
        )
        maref_card = AgentCardAdapter.to_maref_card(mas_card)
        assert maref_card.agent_id == "agent-1"
        assert "search" in maref_card.capabilities
        assert maref_card.trust_score == 0.9

    def test_cross_border_validation_pass(self):
        card = MASAgentCard(
            agent_id="a1",
            agent_name="A",
            data_residency="US",
            model_backend_location="US",
            cross_border=False,
        )
        ok, msg = AgentCardAdapter.validate_cross_border_consistency(card)
        assert ok is True

    def test_cross_border_validation_fail(self):
        card = MASAgentCard(
            agent_id="a1",
            agent_name="A",
            data_residency="US",
            model_backend_location="EU",
            cross_border=False,
        )
        ok, msg = AgentCardAdapter.validate_cross_border_consistency(card)
        assert ok is False
        assert "inconsistency" in msg

    def test_prompt_rot_detectability_fail(self):
        card = MASAgentCard(
            agent_id="a1",
            agent_name="A",
            capabilities=[
                {"skill_id": "s1", "name": "search"},
                {"skill_id": "s2", "name": "summarize", "business_rule_version": "1.0"},
            ],
        )
        ok, msg = AgentCardAdapter.validate_prompt_rot_detectability(card)
        assert ok is False
        assert "search" in msg


class TestScoreMapper:
    def test_map_score_to_phase(self):
        assert ScoreToPhaseMapper.map_score(85, 0) == Phase.OLD_YANG
        assert ScoreToPhaseMapper.map_score(60, 0) == Phase.LESSER_YANG
        assert ScoreToPhaseMapper.map_score(40, 0) == Phase.LESSER_YIN
        assert ScoreToPhaseMapper.map_score(20, 0) == Phase.OLD_YIN

    def test_critical_finding_reduces_phase(self):
        # 85 would normally be OLD_YANG, but with critical it's LESSER_YANG
        assert ScoreToPhaseMapper.map_score(85, 1) == Phase.LESSER_YANG

    def test_permissions_old_yang(self):
        perms = ScoreToPhaseMapper.get_permissions(Phase.OLD_YANG)
        assert perms.can_self_modify is True
        assert perms.max_concurrent_tasks == 50

    def test_permissions_old_yin(self):
        perms = ScoreToPhaseMapper.get_permissions(Phase.OLD_YIN)
        assert perms.can_execute_tools is False
        assert perms.max_concurrent_tasks == 1


class TestStateTrigger:
    def test_fast_screen_fail(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.DECIDE, "test")
        report = EvaluationReport(
            report_id="fs1",
            agent_id="a1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.FAIL,
        )
        decision = FastScreenTrigger.evaluate(report, fsm)
        assert decision.action == TriggerAction.QUARANTINE
        assert decision.target_state == GovernanceState.HALT
        applied = FastScreenTrigger.apply(report, fsm)
        assert applied is True
        assert fsm.current_state == GovernanceState.HALT

    def test_full_run_approve(self):
        fsm = GovernanceStateMachine()
        # Move to DECIDE so ACT is a valid transition
        fsm.transition(GovernanceState.OBSERVE, "setup")
        fsm.transition(GovernanceState.ANALYZE, "setup")
        fsm.transition(GovernanceState.EVALUATE, "setup")
        fsm.transition(GovernanceState.DECIDE, "setup")
        report = EvaluationReport(
            report_id="fr1",
            agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_status=EvalStatus.PASS,
            overall_score=85.0,
        )
        decision = FullRunTrigger.evaluate(report, fsm)
        assert decision.action == TriggerAction.APPROVE
        assert decision.target_state == GovernanceState.ACT
        applied = FullRunTrigger.apply(report, fsm)
        assert applied is True
        assert fsm.current_state == GovernanceState.ACT

    def test_full_run_reject(self):
        fsm = GovernanceStateMachine()
        report = EvaluationReport(
            report_id="fr2",
            agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_status=EvalStatus.FAIL,
            overall_score=40.0,
        )
        decision = FullRunTrigger.evaluate(report, fsm)
        assert decision.action == TriggerAction.QUARANTINE
        applied = FullRunTrigger.apply(report, fsm)
        assert applied is True
        assert fsm.current_state == GovernanceState.HALT

    def test_unified_trigger_priority(self):
        fsm = GovernanceStateMachine()
        report = EvaluationReport(
            report_id="fr3",
            agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_status=EvalStatus.PASS,
            overall_score=85.0,
            layers=[
                LayerReport(
                    layer_number=1,
                    layer_name="Static Audit",
                    score=100.0,
                    findings=[
                        Finding("f1", 1, FindingSeverity.CRITICAL, "Compliance breach", ""),
                    ],
                ),
            ],
        )
        decisions = UnifiedTrigger.apply(report, fsm)
        # Layer 1 critical should trigger quarantine despite high overall score
        assert any(d.action == TriggerAction.QUARANTINE for d in decisions)
        assert fsm.current_state == GovernanceState.HALT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestTLAVerifier:
    def test_cross_border_consistency_pass(self):
        card = MASAgentCard(
            agent_id="a1",
            agent_name="A",
            data_residency="US",
            model_backend_location="US",
            cross_border=False,
        )
        result = TLATheoremVerifier.verify_cross_border_consistency(card)
        assert result.passed is True
        assert result.theorem_name == "CrossBorderConsistency"

    def test_cross_border_consistency_fail(self):
        card = MASAgentCard(
            agent_id="a1",
            agent_name="A",
            data_residency="US",
            model_backend_location="EU",
            cross_border=False,
        )
        result = TLATheoremVerifier.verify_cross_border_consistency(card)
        assert result.passed is False
        assert result.counterexample is not None

    def test_prompt_rot_detection_fail(self):
        card = MASAgentCard(
            agent_id="a1",
            agent_name="A",
            capabilities=[
                {"skill_id": "s1", "name": "search"},
            ],
        )
        result = TLATheoremVerifier.verify_prompt_rot_detection(card)
        assert result.passed is False

    def test_prompt_rot_detection_pass(self):
        card = MASAgentCard(
            agent_id="a1",
            agent_name="A",
            capabilities=[
                {"skill_id": "s1", "name": "search", "business_rule_version": "1.0"},
            ],
        )
        result = TLATheoremVerifier.verify_prompt_rot_detection(card)
        assert result.passed is True

    def test_score_phase_monotonicity(self):
        result = TLATheoremVerifier.verify_score_phase_monotonicity()
        assert result.passed is True
        assert result.counterexample is None

    def test_compliance_quarantine_safety(self):
        report = EvaluationReport(
            report_id="r1",
            agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=85.0,
            findings_summary={"critical": 1, "high": 0, "medium": 0, "low": 0, "info": 0},
            layers=[
                LayerReport(
                    layer_number=1,
                    layer_name="Static Audit",
                    score=100.0,
                    findings=[
                        Finding("f1", 1, FindingSeverity.CRITICAL, "Compliance breach", ""),
                    ],
                ),
            ],
        )
        result = TLATheoremVerifier.verify_compliance_quarantine_safety(report)
        assert result.passed is True

    def test_eval_to_governance_liveness(self):
        report = EvaluationReport(
            report_id="r1",
            agent_id="a1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.FAIL,
            overall_score=30.0,
        )
        result = TLATheoremVerifier.verify_eval_to_governance(report)
        assert result.passed is True

    def test_verify_all_summary(self):
        card = MASAgentCard(
            agent_id="a1",
            agent_name="A",
            data_residency="US",
            model_backend_location="US",
            cross_border=False,
            capabilities=[
                {"skill_id": "s1", "name": "search", "business_rule_version": "1.0"},
            ],
        )
        report = EvaluationReport(
            report_id="r1",
            agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=85.0,
        )
        results = TLATheoremVerifier.verify_all(card, report)
        summary = TLATheoremVerifier.summary(results)
        assert summary["total_theorems"] == 7  # includes GovernanceConfigExport + StenoDetectionComplete
        assert isinstance(summary["all_passed"], bool)


class TestEvolutionQualityGate:
    def test_c1_to_c2_approved(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 85.0)
        result = gate.evaluate_c1_to_c2("agent-1", report)
        assert result.verdict == EvolutionVerdict.APPROVED
        assert result.score == 85.0

    def test_c1_to_c2_rejected(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 50.0)
        result = gate.evaluate_c1_to_c2("agent-1", report)
        assert result.verdict == EvolutionVerdict.REJECTED

    def test_c2_to_c3_no_regression(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 85.0)
        result = gate.evaluate_c2_to_c3("agent-1", report, previous_best_score=80.0)
        assert result.verdict == EvolutionVerdict.APPROVED
        assert result.regression_found is False

    def test_c2_to_c3_regression_detected(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 70.0)
        result = gate.evaluate_c2_to_c3("agent-1", report, previous_best_score=85.0)
        assert result.verdict == EvolutionVerdict.REJECTED
        assert result.regression_found is True

    def test_c3_to_deploy_approved(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 90.0)
        result = gate.evaluate_c3_to_deploy("agent-1", report, {"fnr_std": 0.02, "fpr_std": 0.01})
        assert result.verdict == EvolutionVerdict.APPROVED

    def test_c3_to_deploy_not_converged(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 90.0)
        result = gate.evaluate_c3_to_deploy("agent-1", report, {"fnr_std": 0.5, "fpr_std": 0.4})
        assert result.verdict == EvolutionVerdict.REJECTED

    def test_quality_gate_best_score(self):
        gate = EvolutionQualityGate()
        gate.evaluate_c1_to_c2("a", gate.build_mock_report("a", 70.0))
        gate.evaluate_c1_to_c2("b", gate.build_mock_report("b", 90.0))
        assert gate.best_score == 90.0

    def test_quality_gate_history(self):
        gate = EvolutionQualityGate()
        gate.evaluate_c1_to_c2("a", gate.build_mock_report("a", 75.0))
        gate.evaluate_c2_to_c3("a", gate.build_mock_report("a", 85.0), 75.0)
        assert len(gate.history) == 2
        assert len(gate.get_cycle_results("c1")) == 1
        assert len(gate.get_cycle_results("c2")) == 1

    def test_config_defaults(self):
        config = QualityGateConfig()
        assert config.c1_min_score == 70.0
        assert config.c2_min_score == 80.0
        assert config.c3_min_score == 85.0

    def test_quality_gate_result_to_dict(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 85.0)
        result = gate.evaluate_c1_to_c2("agent-1", report)
        d = result.to_dict()
        assert d["verdict"] == "approved"
        assert d["score"] == 85.0
        assert d["cycle_id"] == "c1"

    def test_config_to_dict(self):
        config = QualityGateConfig(c1_min_score=75.0)
        d = config.to_dict()
        assert d["c1_min_score"] == 75.0
        assert "c2_min_score" in d

    def test_c2_to_c3_rejected_when_regression_detected(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 60.0)
        result = gate.evaluate_c2_to_c3("agent-1", report, previous_best_score=85.0)
        assert result.verdict == EvolutionVerdict.REJECTED
        assert result.regression_found is True

    def test_c2_to_c3_score_drop_within_tolerance(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 82.0)
        # Drop of 3pp is within 5pp tolerance
        result = gate.evaluate_c2_to_c3("agent-1", report, previous_best_score=85.0)
        assert result.verdict == EvolutionVerdict.APPROVED
        assert result.regression_found is False

    def test_c2_to_c3_conditional_no_previous_score(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 70.0)
        result = gate.evaluate_c2_to_c3("agent-1", report, previous_best_score=0.0)
        assert result.verdict == EvolutionVerdict.CONDITIONAL
        assert result.regression_found is False

    def test_c3_to_deploy_conditional_when_score_low(self):
        gate = EvolutionQualityGate()
        report = gate.build_mock_report("agent-1", 75.0)
        result = gate.evaluate_c3_to_deploy("agent-1", report, {"fnr_std": 0.02, "fpr_std": 0.01})
        assert result.verdict == EvolutionVerdict.CONDITIONAL


class TestLayerScoreAggregator:
    def test_compute_overall_score_from_layers(self):
        report = EvaluationReport(
            report_id="r1",
            agent_id="a1",
            layers=[
                LayerReport(layer_number=1, layer_name="Static Audit", score=80.0, max_score=100.0),
                LayerReport(layer_number=2, layer_name="Reasoning", score=90.0, max_score=100.0),
                LayerReport(layer_number=3, layer_name="Action", score=70.0, max_score=100.0),
                LayerReport(layer_number=4, layer_name="E2E", score=85.0, max_score=100.0),
                LayerReport(layer_number=5, layer_name="MAS", score=95.0, max_score=100.0),
            ],
        )
        score = LayerScoreAggregator.compute_overall_score(report)
        # L(0.15*80 + 0.20*90 + 0.20*70 + 0.25*85 + 0.20*95) / 1.0 = 84.25
        assert round(score, 2) == 84.25

    def test_compute_overall_score_uses_existing(self):
        report = EvaluationReport(
            report_id="r1", agent_id="a1", overall_score=88.0
        )
        score = LayerScoreAggregator.compute_overall_score(report)
        assert score == 88.0

    def test_compute_overall_score_empty_layers(self):
        report = EvaluationReport(report_id="r1", agent_id="a1")
        score = LayerScoreAggregator.compute_overall_score(report)
        assert score == 0.0

    def test_compute_compliance_rate_with_layer1(self):
        report = EvaluationReport(
            report_id="r1",
            agent_id="a1",
            layers=[
                LayerReport(layer_number=1, layer_name="Static Audit", score=90.0, max_score=100.0),
            ],
        )
        rate = LayerScoreAggregator.compute_compliance_rate(report)
        assert rate == 90.0

    def test_compute_compliance_rate_no_layer1(self):
        report = EvaluationReport(report_id="r1", agent_id="a1")
        rate = LayerScoreAggregator.compute_compliance_rate(report)
        assert rate == 0.0


class TestScoreMapperEdgeCases:
    def test_map_report(self):
        report = EvaluationReport(
            report_id="r1",
            agent_id="a1",
            layers=[LayerReport(layer_number=5, layer_name="MAS", score=90.0)],
        )
        phase = ScoreToPhaseMapper.map_report(report)
        assert phase == Phase.OLD_YANG

    def test_get_report_permissions(self):
        report = EvaluationReport(
            report_id="r1",
            agent_id="a1",
            layers=[LayerReport(layer_number=5, layer_name="MAS", score=90.0)],
        )
        perms = ScoreToPhaseMapper.get_report_permissions(report)
        assert perms.can_self_modify is True

    def test_phase_description(self):
        desc = ScoreToPhaseMapper.phase_description(Phase.OLD_YANG)
        assert "Maximum autonomy" in desc
        desc2 = ScoreToPhaseMapper.phase_description(Phase.OLD_YIN)
        assert "Minimum autonomy" in desc2

    def test_permission_set_to_dict(self):
        ps = PermissionSet(can_self_modify=True, max_concurrent_tasks=50)
        d = ps.to_dict()
        assert d["can_self_modify"] is True
        assert d["max_concurrent_tasks"] == 50
        assert d["rate_limit_rpm"] == 1000

    def test_score_lesser_yin_permissions(self):
        perms = ScoreToPhaseMapper.get_permissions(Phase.LESSER_YIN)
        assert perms.can_execute_tools is True
        assert perms.can_access_sensitive_data is False
        assert perms.can_cross_boundary is False
        assert perms.max_concurrent_tasks == 5


class TestStateTriggerEdgeCases:
    def test_fast_screen_wrong_mode(self):
        fsm = GovernanceStateMachine()
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_status=EvalStatus.FAIL,
        )
        decision = FastScreenTrigger.evaluate(report, fsm)
        assert decision.action == TriggerAction.HOLD

    def test_fast_screen_conditional(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.OBSERVE, "setup")
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.CONDITIONAL,
        )
        decision = FastScreenTrigger.evaluate(report, fsm)
        assert decision.action == TriggerAction.DEGRADE
        # VERIFY reachable from OBSERVE via Gray Code Hamming distance=1
        assert decision.target_state == GovernanceState.VERIFY
        assert decision.allowed is True

    def test_fast_screen_conditional_unreachable_verify(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.OBSERVE, "setup")
        fsm.transition(GovernanceState.ANALYZE, "setup")
        fsm.transition(GovernanceState.EVALUATE, "setup")
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.CONDITIONAL,
        )
        decision = FastScreenTrigger.evaluate(report, fsm)
        assert decision.action == TriggerAction.DEGRADE
        # From EVALUATE (3), VERIFY (6) is not Hamming distance=1 → unreachable
        assert decision.target_state is None
        assert decision.allowed is False

    def test_full_run_wrong_mode(self):
        fsm = GovernanceStateMachine()
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FAST_SCREEN,
            overall_score=85.0,
        )
        decision = FullRunTrigger.evaluate(report, fsm)
        assert decision.action == TriggerAction.HOLD

    def test_full_run_conditional_score(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.OBSERVE, "setup")
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=65.0,
        )
        decision = FullRunTrigger.evaluate(report, fsm)
        assert decision.action == TriggerAction.DEGRADE
        # VERIFY reachable from OBSERVE via Gray Code
        assert decision.target_state == GovernanceState.VERIFY
        assert decision.allowed is True

    def test_full_run_degrade_with_critical(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.OBSERVE, "setup")
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=85.0,
            findings_summary={"critical": 1, "high": 0, "medium": 0, "low": 0, "info": 0},
            layers=[
                LayerReport(
                    layer_number=1, layer_name="Static Audit", score=50.0,
                    findings=[Finding("f1", 1, FindingSeverity.CRITICAL, "critical", "")],
                ),
            ],
        )
        # score=85 >= 80 but critical=1 != 0 → falls through to score >= 60 → DEGRADE
        decision = FullRunTrigger.evaluate(report, fsm)
        assert decision.action == TriggerAction.DEGRADE
        # VERIFY reachable from OBSERVE via Gray Code
        assert decision.target_state == GovernanceState.VERIFY
        assert decision.allowed is True

    def test_layer_specific_trigger_no_layer1(self):
        fsm = GovernanceStateMachine()
        report = EvaluationReport(report_id="r1", agent_id="a1")
        decision = LayerSpecificTrigger.evaluate_layer1_findings(report, fsm)
        assert decision is None

    def test_layer_specific_trigger_layer5_high_finding(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.OBSERVE, "setup")
        fsm.transition(GovernanceState.ANALYZE, "setup")
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=90.0,
            layers=[
                LayerReport(
                    layer_number=5, layer_name="MAS", score=90.0,
                    findings=[
                        Finding("f1", 5, FindingSeverity.HIGH, "coordination issue", ""),
                    ],
                ),
            ],
        )
        decision = LayerSpecificTrigger.evaluate_layer5_findings(report, fsm)
        assert decision is not None
        assert decision.action == TriggerAction.DEGRADE

    def test_layer_specific_trigger_no_layer5(self):
        fsm = GovernanceStateMachine()
        report = EvaluationReport(report_id="r1", agent_id="a1")
        decision = LayerSpecificTrigger.evaluate_layer5_findings(report, fsm)
        assert decision is None

    def test_layer_specific_trigger_layer1_critical_quarantines(self):
        fsm = GovernanceStateMachine()
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            layers=[
                LayerReport(
                    layer_number=1, layer_name="Static", score=50.0,
                    findings=[
                        Finding("f1", 1, FindingSeverity.CRITICAL, "critical breach", ""),
                    ],
                ),
            ],
        )
        decision = LayerSpecificTrigger.evaluate_layer1_findings(report, fsm)
        assert decision is not None
        assert decision.action == TriggerAction.QUARANTINE
        assert decision.target_state == GovernanceState.HALT

    def test_state_transition_decision_to_dict(self):
        decision = StateTransitionDecision(
            action=TriggerAction.QUARANTINE,
            target_state=GovernanceState.HALT,
            reason="test",
            allowed=True,
        )
        d = decision.to_dict()
        assert d["action"] == "quarantine"
        assert d["target_state"] == "HALT"
        assert d["allowed"] is True

    def test_unified_trigger_empty_layers(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.OBSERVE, "setup")
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=90.0,
        )
        decisions = UnifiedTrigger.apply(report, fsm)
        assert len(decisions) >= 1

    def test_unified_trigger_fast_screen_pass_through(self):
        fsm = GovernanceStateMachine()
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.FAIL,
            overall_score=30.0,
        )
        decisions = UnifiedTrigger.apply(report, fsm)
        assert any(d.action == TriggerAction.QUARANTINE for d in decisions)

    def test_unified_trigger_fast_screen_with_layer5(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.OBSERVE, "setup")
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.PASS,
            overall_score=85.0,
            layers=[
                LayerReport(
                    layer_number=5, layer_name="MAS", score=90.0,
                    findings=[
                        Finding("f5", 5, FindingSeverity.HIGH, "MAS issue", ""),
                    ],
                ),
            ],
        )
        decisions = UnifiedTrigger.apply(report, fsm)
        assert any(d.action == TriggerAction.DEGRADE for d in decisions)

    def test_unified_trigger_layer5_after_approve(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.OBSERVE, "setup")
        fsm.transition(GovernanceState.ANALYZE, "setup")
        fsm.transition(GovernanceState.EVALUATE, "setup")
        fsm.transition(GovernanceState.DECIDE, "setup")
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=85.0,
            layers=[
                LayerReport(
                    layer_number=5, layer_name="MAS", score=85.0,
                    findings=[
                        Finding("f5", 5, FindingSeverity.HIGH, "coordination issue", ""),
                    ],
                ),
            ],
        )
        decisions = UnifiedTrigger.apply(report, fsm)
        assert any(d.action == TriggerAction.APPROVE for d in decisions) or any(
            d.action == TriggerAction.DEGRADE for d in decisions
        )


class TestEvalObserverEdgeCases:
    def test_observer_alert_to_dict(self):
        alert = ObserverAlert(
            alert_id="a1", agent_id="agent-1",
            alert_type="TEST", message="test", severity="info",
        )
        d = alert.to_dict()
        assert d["alert_id"] == "a1"
        assert d["severity"] == "info"

    def test_get_eval_history_filtered(self):
        fsm = GovernanceStateMachine()
        observer = MASEvalObserver(fsm)

        r1 = EvaluationReport(
            report_id="r1", agent_id="agent-1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.PASS,
            overall_score=85.0,
        )
        r2 = EvaluationReport(
            report_id="r2", agent_id="agent-2",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.PASS,
            overall_score=90.0,
        )
        observer.on_fast_screen_complete(r1)
        observer.on_fast_screen_complete(r2)

        agent1_history = observer.get_eval_history("agent-1")
        assert len(agent1_history) == 1
        assert agent1_history[0]["agent_id"] == "agent-1"

        all_history = observer.get_eval_history()
        assert len(all_history) == 2

    def test_add_remove_alert_callback(self):
        fsm = GovernanceStateMachine()
        observer = MASEvalObserver(fsm)

        calls = []

        def callback(alert):
            calls.append(alert)

        observer.add_alert_callback(callback)
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.FAIL,
            overall_score=30.0,
        )
        observer.on_fast_screen_complete(report)
        assert len(calls) == 1

        observer.remove_alert_callback(callback)
        observer.on_fast_screen_complete(report)
        assert len(calls) == 1  # no additional calls

    def test_callback_failure_does_not_raise(self):
        fsm = GovernanceStateMachine()

        def bad_cb(alert):
            raise RuntimeError("fail")

        observer = MASEvalObserver(fsm, alert_callbacks=[bad_cb])
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.PASS,
            overall_score=85.0,
        )
        alert = observer.on_fast_screen_complete(report)
        assert alert is not None

    def test_full_run_conditional_branch(self):
        fsm = GovernanceStateMachine()
        fsm.transition(GovernanceState.OBSERVE, "setup")
        fsm.transition(GovernanceState.ANALYZE, "setup")
        fsm.transition(GovernanceState.EVALUATE, "setup")
        fsm.transition(GovernanceState.DECIDE, "setup")
        observer = MASEvalObserver(fsm)

        report = EvaluationReport(
            report_id="fr-cond",
            agent_id="agent-1",
            test_mode=TestMode.FULL_RUN,
            overall_status=EvalStatus.PASS,
            overall_score=65.0,
            layers=[LayerReport(layer_number=5, layer_name="MAS", score=65.0)],
        )
        alert = observer.on_full_run_complete(report)
        assert alert.alert_type == "FULL_RUN_CONDITIONAL"
        assert observer.get_agent_phase("agent-1") == Phase.LESSER_YANG


class TestTLAVerifierEdgeCases:
    def test_governance_config_export_default(self):
        result = TLATheoremVerifier.verify_governance_config_export()
        assert result.passed is True
        assert "all governance config exports" in result.details.lower()

    def test_verifier_summary(self):
        card = MASAgentCard(agent_id="a1", agent_name="A")
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=85.0,
        )
        results = TLATheoremVerifier.verify_all(card, report)
        summary = TLATheoremVerifier.summary(results)
        assert summary["total_theorems"] == 7  # includes GovernanceConfigExport + StenoDetectionComplete
        assert isinstance(summary["all_passed"], bool)

    def test_verify_all_with_custom_objects(self):
        from maref.governance.circuit_breaker import CircuitBreaker
        from maref.governance.state_machine import GovernanceStateMachine

        card = MASAgentCard(
            agent_id="a1", agent_name="A",
            data_residency="US", model_backend_location="US",
            capabilities=[{"skill_id": "s1", "name": "s1", "business_rule_version": "1.0"}],
        )
        report = EvaluationReport(
            report_id="r1", agent_id="a1",
            test_mode=TestMode.FULL_RUN,
            overall_score=85.0,
        )
        cb = CircuitBreaker()
        sm = GovernanceStateMachine()

        results = TLATheoremVerifier.verify_all(card, report, circuit_breaker=cb, state_machine=sm)
        assert results["CrossBorderConsistency"].passed is True
        assert results["GovernanceConfigExport"].passed is True

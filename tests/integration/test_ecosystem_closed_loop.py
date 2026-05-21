from __future__ import annotations

from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.integration.percv import (
    CyclePhase,
    OrchestratorCycle,
    PERCVResearchOrchestrator,
)
from maref.integration.test_platform import (
    EvalStatus,
    EvaluationReport,
    EvolutionQualityGate,
    LayerReport,
    MASEvalObserver,
    TestMode,
)


class TestEcosystemClosedLoop:
    def test_orchestrator_initializes(self):
        sm = GovernanceStateMachine()
        orch = PERCVResearchOrchestrator(state_machine=sm)
        orch.initialize()
        assert sm.current_state == GovernanceState.OBSERVE

    def test_research_cycle_completes(self):
        sm = GovernanceStateMachine()
        orch = PERCVResearchOrchestrator(state_machine=sm)
        orch.initialize()
        result = orch.run_research_cycle(topic="ecosystem integration test")
        assert result.cycle_type == OrchestratorCycle.RESEARCH
        assert result.phase == CyclePhase.COMPLETED
        assert orch.cycle_count == 1

    def test_evaluate_cycle_quarantines_low_score(self):
        sm = GovernanceStateMachine()
        eval_obs = MASEvalObserver(governance_fsm=sm)
        orch = PERCVResearchOrchestrator(
            state_machine=sm,
            eval_observer=eval_obs,
        )
        orch.initialize()

        report = EvaluationReport(
            report_id="e2e-fail-1",
            agent_id="agent-bad",
            test_mode=TestMode.FAST_SCREEN,
            overall_status=EvalStatus.FAIL,
            overall_score=30.0,
            layers=[
                LayerReport(layer_number=5, layer_name="MAS Dimensions", score=30.0),
            ],
        )

        result = orch.run_evaluate_cycle(agent_id="agent-bad", report=report)
        assert result.cycle_type == OrchestratorCycle.EVALUATE
        assert sm.current_state == GovernanceState.HALT

    def test_evolve_cycle_uses_quality_gate(self):
        qg = EvolutionQualityGate()
        sm = GovernanceStateMachine()
        orch = PERCVResearchOrchestrator(
            state_machine=sm,
            quality_gate=qg,
        )
        orch.initialize()
        result = orch.run_evolve_cycle(candidate_id="candidate-1", score=85.0)
        assert result.cycle_type == OrchestratorCycle.EVOLVE
        assert result.phase == CyclePhase.COMPLETED

    def test_evolve_cycle_rejects_low_score(self):
        qg = EvolutionQualityGate()
        sm = GovernanceStateMachine()
        orch = PERCVResearchOrchestrator(
            state_machine=sm,
            quality_gate=qg,
        )
        orch.initialize()
        result = orch.run_evolve_cycle(candidate_id="candidate-bad", score=45.0)
        assert result.cycle_type == OrchestratorCycle.EVOLVE
        if result.result:
            assert result.result.get("verdict") == "rejected"

    def test_verify_cycle_completes(self):
        sm = GovernanceStateMachine()
        orch = PERCVResearchOrchestrator(state_machine=sm)
        orch.initialize()
        result = orch.run_verify_cycle(agent_id="agent-1")
        assert result.cycle_type == OrchestratorCycle.VERIFY
        assert result.phase == CyclePhase.COMPLETED

    def test_feedback_directions_generated(self):
        sm = GovernanceStateMachine()
        eval_obs = MASEvalObserver(governance_fsm=sm)
        orch = PERCVResearchOrchestrator(
            state_machine=sm,
            eval_observer=eval_obs,
        )
        orch.initialize()

        orch.run_research_cycle(topic="initial")
        orch.run_evaluate_cycle(agent_id="agent-1")

        directions = orch.get_research_directions()
        assert isinstance(directions, list)

    def test_multi_cycle_closed_loop(self):
        sm = GovernanceStateMachine()
        eval_obs = MASEvalObserver(governance_fsm=sm)
        qg = EvolutionQualityGate()
        orch = PERCVResearchOrchestrator(
            state_machine=sm,
            eval_observer=eval_obs,
            quality_gate=qg,
        )
        orch.initialize()

        for i in range(3):
            orch.run_research_cycle(topic=f"cycle-{i}")
            orch.run_evaluate_cycle(agent_id=f"agent-{i}")
            orch.run_evolve_cycle(candidate_id=f"candidate-{i}")

        assert orch.cycle_count == 9
        assert len(orch.get_history()) == 9

    def test_state_machine_tracks_transitions(self):
        sm = GovernanceStateMachine()
        initial_count = sm.transition_count

        eval_obs = MASEvalObserver(governance_fsm=sm)
        orch = PERCVResearchOrchestrator(
            state_machine=sm,
            eval_observer=eval_obs,
        )
        orch.initialize()

        orch.run_research_cycle(topic="state-track")
        orch.run_evaluate_cycle(agent_id="state-agent")

        assert sm.transition_count > initial_count

    def test_cycle_history_has_all_types(self):
        sm = GovernanceStateMachine()
        eval_obs = MASEvalObserver(governance_fsm=sm)
        qg = EvolutionQualityGate()
        orch = PERCVResearchOrchestrator(
            state_machine=sm,
            eval_observer=eval_obs,
            quality_gate=qg,
        )
        orch.initialize()

        types_run: set[str] = set()
        orch.run_research_cycle(topic="t")
        types_run.add("research")
        orch.run_evaluate_cycle(agent_id="a")
        types_run.add("evaluate")
        orch.run_evolve_cycle(candidate_id="c")
        types_run.add("evolve")
        orch.run_verify_cycle(agent_id="a")
        types_run.add("verify")

        history = orch.get_history()
        history_types = {h["cycle_type"] for h in history}
        assert history_types == types_run

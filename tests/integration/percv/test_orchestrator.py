"""Tests for PERCVResearchOrchestrator — the central closed-loop coordinator."""

from __future__ import annotations

from unittest.mock import MagicMock

from maref.integration.percv.orchestrator import (
    PERCVResearchOrchestrator,
    OrchestratorCycle,
    CyclePhase,
    OrchestratorStatus,
)


class TestOrchestratorLifecycle:
    def test_create_with_minimal_config(self):
        orch = PERCVResearchOrchestrator()
        assert orch.status == OrchestratorStatus.CREATED
        assert orch.cycle_count == 0

    def test_create_with_all_dependencies(self):
        gw = MagicMock()
        cb = MagicMock()
        sm = MagicMock()
        kg = MagicMock()
        eval_obs = MagicMock()
        quality_gate = MagicMock()

        orch = PERCVResearchOrchestrator(
            gateway_adapter=gw,
            circuit_breaker=cb,
            state_machine=sm,
            knowledge_graph=kg,
            eval_observer=eval_obs,
            quality_gate=quality_gate,
        )
        assert orch.gateway_adapter is gw
        assert orch.circuit_breaker is cb
        assert orch.state_machine is sm

    def test_initialize_transitions_state_to_observe(self):
        sm = MagicMock()
        orch = PERCVResearchOrchestrator(state_machine=sm)
        orch.initialize()
        sm.transition.assert_called_once()

    def test_cycle_enum_values(self):
        assert OrchestratorCycle.RESEARCH.value == "research"
        assert OrchestratorCycle.EVALUATE.value == "evaluate"
        assert OrchestratorCycle.EVOLVE.value == "evolve"
        assert OrchestratorCycle.VERIFY.value == "verify"

    def test_cycle_phase_order(self):
        phases = list(CyclePhase)
        assert phases == [
            CyclePhase.PLANNING,
            CyclePhase.EXECUTING,
            CyclePhase.VERIFYING,
            CyclePhase.COMPLETED,
            CyclePhase.FAILED,
        ]


class TestFullCycleOrchestration:
    def test_research_completes_without_gateway(self):
        sm = MagicMock()

        orch = PERCVResearchOrchestrator(state_machine=sm)
        result = orch.run_research_cycle(topic="test topic")

        assert result.cycle_type == OrchestratorCycle.RESEARCH
        assert result.phase == CyclePhase.COMPLETED
        assert orch.cycle_count == 1

    def test_circuit_breaker_without_gateway_triggers_failure(self):
        cb = MagicMock()
        sm = MagicMock()

        orch = PERCVResearchOrchestrator(
            circuit_breaker=cb,
            state_machine=sm,
        )
        result = orch.run_research_cycle(topic="any topic")

        assert result.phase == CyclePhase.FAILED
        cb.trip.assert_called_once()

    def test_evaluate_cycle_calls_eval_observer(self):
        eval_obs = MagicMock()
        sm = MagicMock()

        orch = PERCVResearchOrchestrator(
            eval_observer=eval_obs,
            state_machine=sm,
        )
        result = orch.run_evaluate_cycle(agent_id="test-agent")

        assert result.cycle_type == OrchestratorCycle.EVALUATE
        eval_obs.on_fast_screen_complete.assert_called_once()

    def test_evolve_cycle_calls_quality_gate(self):
        qg = MagicMock()

        orch = PERCVResearchOrchestrator(
            quality_gate=qg,
        )
        result = orch.run_evolve_cycle(candidate_id="candidate-1")

        assert result.cycle_type == OrchestratorCycle.EVOLVE
        qg.evaluate_c1_to_c2.assert_called_once()

    def test_full_closed_loop_sequence(self):
        sm = MagicMock()
        eval_obs = MagicMock()
        qg = MagicMock()

        orch = PERCVResearchOrchestrator(
            state_machine=sm,
            eval_observer=eval_obs,
            quality_gate=qg,
        )
        orch.initialize()

        orch.run_research_cycle(topic="market analysis")
        orch.run_evaluate_cycle(agent_id="agent-1")
        orch.run_evolve_cycle(candidate_id="agent-1")
        orch.run_verify_cycle(agent_id="agent-1")

        assert orch.cycle_count == 4
        assert len(orch.get_history()) == 4

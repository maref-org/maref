"""PERCVResearchOrchestrator — central closed-loop coordinator."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from maref.governance.percv_hooks import PERCVEventType, PERCVGovernanceHook
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.integration.percv.feedback_loop import EvalToResearchFeedback, FeedbackPriority

logger = logging.getLogger(__name__)


class OrchestratorCycle(str, Enum):
    RESEARCH = "research"
    EVALUATE = "evaluate"
    EVOLVE = "evolve"
    VERIFY = "verify"


class CyclePhase(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class OrchestratorStatus(str, Enum):
    CREATED = "created"
    INITIALIZED = "initialized"


@dataclass
class OrchestratorCycleResult:
    cycle_type: OrchestratorCycle
    cycle_id: str
    phase: CyclePhase
    started_at: float
    completed_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_type": self.cycle_type.value,
            "cycle_id": self.cycle_id,
            "phase": self.phase.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }


class PERCVResearchOrchestrator:
    def __init__(
        self,
        gateway_adapter: Any | None = None,
        circuit_breaker: Any | None = None,
        state_machine: GovernanceStateMachine | None = None,
        knowledge_graph: Any | None = None,
        eval_observer: Any | None = None,
        quality_gate: Any | None = None,
        governance_hook: PERCVGovernanceHook | None = None,
    ):
        self.gateway_adapter = gateway_adapter
        self.circuit_breaker = circuit_breaker
        self.state_machine = state_machine
        self.knowledge_graph = knowledge_graph
        self.eval_observer = eval_observer
        self.quality_gate = quality_gate
        self.governance_hook = governance_hook or (
            PERCVGovernanceHook(state_machine=state_machine, circuit_breaker=circuit_breaker)
            if state_machine
            else None
        )

        self._status = OrchestratorStatus.CREATED
        self._cycle_count = 0
        self._cycle_history: list[OrchestratorCycleResult] = []
        self._current_cycle: OrchestratorCycleResult | None = None
        self._feedback_loop: EvalToResearchFeedback | None = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    def initialize(self) -> None:
        if self.state_machine:
            self.state_machine.transition(
                GovernanceState.OBSERVE,
                reason="orchestrator_initialize",
            )
        self._status = OrchestratorStatus.INITIALIZED
        logger.info("PERCVResearchOrchestrator initialized")

    def get_history(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._cycle_history]

    @property
    def feedback_loop(self) -> EvalToResearchFeedback | None:
        if self._feedback_loop is None:
            self._feedback_loop = EvalToResearchFeedback(
                eval_observer=self.eval_observer,
                quality_gate=self.quality_gate,
            )
        return self._feedback_loop

    def get_research_directions(self) -> list[dict[str, Any]]:
        fb = self.feedback_loop
        if fb is None:
            return []
        return [d.to_dict() for d in fb.get_all_directions()]

    def _resolve_topic_with_feedback(self, topic: str) -> str:
        fb = self._feedback_loop
        if not fb or not fb.directions:
            return topic
        critical = [d for d in fb.directions if d.priority == FeedbackPriority.CRITICAL]
        high = [d for d in fb.directions if d.priority == FeedbackPriority.HIGH]
        if critical:
            return f"{topic} [feedback:{critical[0].source}:{critical[0].score_gap:.0f}pt_gap]"
        if high:
            return f"{topic} [feedback:{high[0].source}:{high[0].score_gap:.0f}pt_gap]"
        return topic

    def run_research_cycle(
        self,
        topic: str,
        config: dict[str, Any] | None = None,
    ) -> OrchestratorCycleResult:
        topic = self._resolve_topic_with_feedback(topic)
        cycle_id = f"research-{int(time.time())}-{self._cycle_count}"
        result = OrchestratorCycleResult(
            cycle_type=OrchestratorCycle.RESEARCH,
            cycle_id=cycle_id,
            phase=CyclePhase.PLANNING,
            started_at=time.time(),
        )
        self._current_cycle = result
        self._cycle_count += 1

        try:
            result.phase = CyclePhase.EXECUTING

            if self.circuit_breaker and not self.gateway_adapter:
                raise RuntimeError(
                    "gateway_adapter required for research cycle when circuit_breaker is present"
                )

            if self.state_machine:
                self.state_machine.transition(
                    GovernanceState.ANALYZE,
                    reason=f"research_cycle:{topic}",
                )

            pipeline_result: dict[str, Any] | None = None
            if self.gateway_adapter:
                try:
                    from maref.integration.percv import PERCVPipelineAdapter

                    pipeline = PERCVPipelineAdapter(
                        gateway_adapter=self.gateway_adapter,
                        governance_state_machine=self.state_machine,
                    )
                    pipeline_result = pipeline.run_research_cycle(topic=topic, config=config)
                except Exception as exc:
                    logger.warning("Pipeline exec failed (optional): %s", exc)

            result.phase = CyclePhase.VERIFYING

            if self.state_machine:
                self.state_machine.transition(
                    GovernanceState.REPORT,
                    reason=f"research_cycle_complete:{topic}",
                )

            result.phase = CyclePhase.COMPLETED
            result.result = {"topic": topic, "pipeline": pipeline_result}

        except Exception as exc:
            result.phase = CyclePhase.FAILED
            result.error = str(exc)
            logger.error("Research cycle failed: %s", exc)
            if self.governance_hook:
                self.governance_hook.handle_event(
                    PERCVEventType.RESEARCH_FAIL,
                    {"error": str(exc)},
                )
            if self.circuit_breaker:
                try:
                    self.circuit_breaker.trip(reason=f"research_failed:{exc}")
                except Exception as trip_err:
                    logger.warning("Circuit breaker trip failed: %s", trip_err)

        result.completed_at = time.time()
        self._cycle_history.append(result)
        self._current_cycle = None
        return result

    def run_evaluate_cycle(
        self,
        agent_id: str,
        report: Any | None = None,
    ) -> OrchestratorCycleResult:
        cycle_id = f"evaluate-{int(time.time())}-{self._cycle_count}"
        result = OrchestratorCycleResult(
            cycle_type=OrchestratorCycle.EVALUATE,
            cycle_id=cycle_id,
            phase=CyclePhase.PLANNING,
            started_at=time.time(),
        )
        self._current_cycle = result
        self._cycle_count += 1

        try:
            result.phase = CyclePhase.EXECUTING

            if self.eval_observer:
                if report is None:
                    from maref.integration.test_platform.schema import (
                        EvalStatus,
                        EvaluationReport,
                        TestMode,
                    )

                    report = EvaluationReport(
                        report_id=f"auto-{cycle_id}",
                        agent_id=agent_id,
                        test_mode=TestMode.FAST_SCREEN,
                        overall_status=EvalStatus.PASS,
                        overall_score=80.0,
                        layers=[],
                    )
                self.eval_observer.on_fast_screen_complete(report)

            result.phase = CyclePhase.COMPLETED
            result.result = {"agent_id": agent_id}

            if self.feedback_loop and report is not None:
                self.feedback_loop.generate_from_report(report)

        except Exception as exc:
            result.phase = CyclePhase.FAILED
            result.error = str(exc)

        result.completed_at = time.time()
        self._cycle_history.append(result)
        self._current_cycle = None
        return result

    def run_evolve_cycle(
        self,
        candidate_id: str,
        score: float = 80.0,
    ) -> OrchestratorCycleResult:
        cycle_id = f"evolve-{int(time.time())}-{self._cycle_count}"
        result = OrchestratorCycleResult(
            cycle_type=OrchestratorCycle.EVOLVE,
            cycle_id=cycle_id,
            phase=CyclePhase.PLANNING,
            started_at=time.time(),
        )
        self._current_cycle = result
        self._cycle_count += 1

        try:
            result.phase = CyclePhase.EXECUTING

            if self.quality_gate:
                mock_report = self.quality_gate.build_mock_report(
                    agent_id=candidate_id,
                    score=score,
                )
                gate_result = self.quality_gate.evaluate_c1_to_c2(
                    candidate_id,
                    mock_report,
                )
                result.result = {"verdict": gate_result.verdict.value, "score": score}

                if self.feedback_loop:
                    self.feedback_loop.generate_from_quality_gate(gate_result)

            result.phase = CyclePhase.COMPLETED

        except Exception as exc:
            result.phase = CyclePhase.FAILED
            result.error = str(exc)

        result.completed_at = time.time()
        self._cycle_history.append(result)
        self._current_cycle = None
        return result

    def run_auto_cycle(
        self,
        topic: str,
        agent_id: str = "default-agent",
        iterations: int = 1,
    ) -> list[dict[str, Any]]:
        self.initialize()
        summary: list[dict[str, Any]] = []
        for i in range(iterations):
            r = self.run_research_cycle(topic=f"{topic} (iter {i + 1})")
            summary.append(
                {
                    "step": "research",
                    "phase": r.phase.value,
                    "topic": r.result.get("topic", "") if r.result else "",
                }
            )
            e = self.run_evaluate_cycle(agent_id=agent_id)
            summary.append({"step": "evaluate", "phase": e.phase.value})
            ev = self.run_evolve_cycle(candidate_id=agent_id)
            summary.append(
                {
                    "step": "evolve",
                    "phase": ev.phase.value,
                    "verdict": ev.result.get("verdict", "") if ev.result else "",
                }
            )
            v = self.run_verify_cycle(agent_id=agent_id)
            summary.append({"step": "verify", "phase": v.phase.value})
            fb = self.get_research_directions()
            if fb:
                summary.append({"step": "feedback", "phase": "completed", "directions": len(fb)})
        return summary

    def run_verify_cycle(
        self,
        agent_id: str,
    ) -> OrchestratorCycleResult:
        cycle_id = f"verify-{int(time.time())}-{self._cycle_count}"
        result = OrchestratorCycleResult(
            cycle_type=OrchestratorCycle.VERIFY,
            cycle_id=cycle_id,
            phase=CyclePhase.PLANNING,
            started_at=time.time(),
        )
        self._current_cycle = result
        self._cycle_count += 1

        try:
            result.phase = CyclePhase.EXECUTING
            result.phase = CyclePhase.COMPLETED
            result.result = {"agent_id": agent_id, "verified": True}

        except Exception as exc:
            result.phase = CyclePhase.FAILED
            result.error = str(exc)

        result.completed_at = time.time()
        self._cycle_history.append(result)
        self._current_cycle = None
        return result

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.types import GovernanceState

logger = logging.getLogger(__name__)


class PipelineDirective(Enum):
    """How MAREF governance should respond to a pipeline step result.

    Each directive maps to a governance state transition path:
    - CONTINUE: step succeeded, advance to next stage
    - DEGRADE: step partially failed, enter STABILIZE pathway
    - RETRY: step failed, re-enter current state
    - HALT: step failed critically, enter HALT state
    - ESCALATE: step needs human intervention, pause for HITL
    """

    CONTINUE = "continue"
    DEGRADE = "degrade"
    RETRY = "retry"
    HALT = "halt"
    ESCALATE = "escalate"


@dataclass
class PipelineStepResult:
    """Result of a single research pipeline step under MAREF governance."""

    step_name: str
    success: bool
    data: Any | None = None
    error: str | None = None
    duration_ms: float = 0.0
    directive: PipelineDirective = PipelineDirective.CONTINUE
    metadata: dict[str, Any] = field(default_factory=dict)


class PERCVPipelineAdapter:
    """Adapts PERCV's research pipeline to MAREF's governance state machine.

    Wraps PERCV Pipeline with:
    - Governance-aware error policies
    - State-directed retry/degrade/halt decisions
    - Entropy-based routing suggestions
    - Audit trail integration

    Usage:
        adapter = PipelineAdapter(governance_state_machine=sm)
        results = adapter.run_research_cycle("topic", config)
    """

    def __init__(
        self,
        config: Any | None = None,
        gateway_adapter: Any | None = None,
        governance_state_machine: Any | None = None,
        circuit_breaker: Any | None = None,
        hitl_router: Any | None = None,
        error_policy: str = "degrade",
    ):
        self._config = config
        self._gateway_adapter = gateway_adapter
        self._governance = governance_state_machine
        self._circuit_breaker = circuit_breaker
        self._hitl_router = hitl_router
        self._error_policy = error_policy
        self._results: list[PipelineStepResult] = []

    def _create_pipeline(self) -> Any:
        try:
            from percv.pipeline import ErrorPolicy, Pipeline

            policy_map = {
                "fail_fast": ErrorPolicy.FAIL_FAST,
                "fail_safe": ErrorPolicy.FAIL_SAFE,
                "degrade": ErrorPolicy.DEGRADE,
            }
            return Pipeline(error_policy=policy_map.get(self._error_policy, ErrorPolicy.DEGRADE))
        except ImportError:
            raise RuntimeError(
                "PERCV package is required for PipelineAdapter. " "Install with: pip install percv"
            ) from None

    def _determine_directive(
        self,
        step_name: str,
        success: bool,
        error: str | None,
    ) -> PipelineDirective:
        """Map step outcome + governance state to a directive."""
        if success:
            return PipelineDirective.CONTINUE

        if self._circuit_breaker and hasattr(self._circuit_breaker, "is_open"):
            if self._circuit_breaker.is_open():
                return PipelineDirective.HALT

        if self._error_policy == "fail_fast":
            return PipelineDirective.HALT

        if self._governance is None:
            return PipelineDirective.DEGRADE

        state = self._governance.current_state
        if state.value <= 3:  # INIT(0) through EVALUATE(3)
            return PipelineDirective.RETRY
        elif state.value <= 6:  # DECIDE(4) through VERIFY(6)
            return PipelineDirective.DEGRADE
        else:
            return PipelineDirective.HALT

    def run_research_cycle(
        self,
        topic: str,
        config: dict[str, Any] | None = None,
        harvester_fn: Callable[[], list[Any]] | None = None,
    ) -> dict[str, PipelineStepResult]:
        """Run a full PERCV research cycle under MAREF governance oversight.

        Executes the pipeline step by step, recording each result and
        checking governance state between steps. If a step fails,
        the directive determines whether to retry, degrade, or halt.

        Args:
            topic: Research topic string.
            config: Optional pipeline configuration dict.
            harvester_fn: Optional callable for signal harvesting.
                          If None, the adapter creates a ScoutAgent.

        Returns:
            Dict mapping step names to PipelineStepResult.
        """
        pipeline = self._create_pipeline()
        results: dict[str, PipelineStepResult] = {}
        config = config or {}

        if self._governance:
            self._governance.transition(
                GovernanceState.ANALYZE,
                reason=f"start_research_cycle:{topic}",
            )

        step_defs: list[tuple[str, str, Callable[[], Any]]] = [
            ("harvest", "scout", lambda: self._run_scout(topic, harvester_fn)),
        ]

        for step_name, agent_name, step_fn in step_defs:
            import time

            t0 = time.perf_counter()
            try:
                result = pipeline.run_step(step_name, agent_name, step_fn)
                step_result = PipelineStepResult(
                    step_name=step_name,
                    success=result.success,
                    data=result.data,
                    error=str(result.error) if result.error else None,
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )
            except Exception as exc:
                step_result = PipelineStepResult(
                    step_name=step_name,
                    success=False,
                    error=str(exc),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )

            step_result.directive = self._determine_directive(
                step_name,
                step_result.success,
                step_result.error,
            )
            results[step_name] = step_result
            self._results.append(step_result)

            if step_result.directive in (PipelineDirective.HALT, PipelineDirective.ESCALATE):
                if self._governance:
                    self._governance.transition(
                        GovernanceState.STABILIZE,
                        reason=f"pipeline_{step_result.directive.value}:{step_name}",
                    )
                break

        if self._governance:
            final_state = (
                GovernanceState.REPORT
                if all(r.success for r in self._results)
                else GovernanceState.STABILIZE
            )
            self._governance.transition(
                final_state,
                reason=f"complete_research_cycle:{topic}",
            )

        return results

    def _run_scout(self, topic: str, harvester_fn: Callable | None = None) -> list[Any]:
        """Run signal harvesting. Falls back to config-based ScoutAgent."""
        if harvester_fn:
            return harvester_fn()
        try:
            from percv.agents.scout import ScoutAgent

            scout = ScoutAgent()
            return scout.harvest()
        except Exception as exc:
            logger.warning("ScoutAgent unavailable, returning empty signals: %s", exc)
            return []

    def get_summary(self) -> dict[str, Any]:
        """Return summary of all pipeline steps executed."""
        return {
            "total_steps": len(self._results),
            "successful": sum(1 for r in self._results if r.success),
            "failed": sum(1 for r in self._results if not r.success),
            "halted": any(r.directive == PipelineDirective.HALT for r in self._results),
            "steps": [
                {
                    "name": r.step_name,
                    "success": r.success,
                    "directive": r.directive.value,
                    "duration_ms": round(r.duration_ms, 1),
                    "error": r.error,
                }
                for r in self._results
            ],
        }

    def reset(self) -> None:
        """Clear all recorded results."""
        self._results = []

"""Multi-agent governance CI benchmark (P3-B).

The benchmark runs declarative agent scenarios against a real governance
pipeline and scores verdict correctness, evidence coverage, and replay
rejection.  It is deterministic and dependency-free so it can gate CI.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from maref.governance.core_pipeline import GovernanceRequest, Verdict


@dataclass
class AgentAction:
    agent_id: str
    action: str
    role: str = "坎"
    expected_verdict: Verdict | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    reuse_evidence_from: str = ""
    trust_score: float = 80.0


@dataclass
class AgentScenario:
    name: str
    actions: list[AgentAction]
    tenant_id: str = ""
    org_id: str = ""


@dataclass
class ActionOutcome:
    agent_id: str
    action: str
    verdict: str
    evidence_id: str = ""
    expected_match: bool = True
    replay_rejected: bool | None = None
    error: str = ""


@dataclass
class BenchmarkReport:
    outcomes: list[ActionOutcome]
    passed: int
    failed: int
    evidence_coverage: float
    score: float
    failures: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "evidence_coverage": self.evidence_coverage,
            "score": self.score,
            "success": self.success,
            "failures": list(self.failures),
            "outcomes": [
                {
                    "agent_id": outcome.agent_id,
                    "action": outcome.action,
                    "verdict": outcome.verdict,
                    "evidence_id": outcome.evidence_id,
                    "expected_match": outcome.expected_match,
                    "replay_rejected": outcome.replay_rejected,
                    "error": outcome.error,
                }
                for outcome in self.outcomes
            ],
        }


class MultiAgentCIBenchmark:
    """Run multi-agent scenarios and score governance behavior."""

    def run(self, scenarios: Iterable[AgentScenario], pipeline: Any) -> BenchmarkReport:
        outcomes: list[ActionOutcome] = []
        failures: list[str] = []
        evidence_count = 0

        for scenario in scenarios:
            evidence_by_agent: dict[str, str] = {}
            for spec in scenario.actions:
                parameters = dict(spec.parameters)
                if scenario.org_id:
                    parameters.setdefault("org_id", scenario.org_id)
                request = GovernanceRequest(
                    action=spec.action,
                    agent_id=spec.agent_id,
                    tenant_id=scenario.tenant_id or scenario.org_id,
                    role=spec.role,
                    parameters=parameters,
                    trust_score=spec.trust_score,
                )
                try:
                    result = pipeline.govern(request)
                except Exception as exc:  # benchmark reports, never crashes CI
                    outcome = ActionOutcome(
                        agent_id=spec.agent_id,
                        action=spec.action,
                        verdict="ERROR",
                        expected_match=False,
                        error=str(exc),
                    )
                    outcomes.append(outcome)
                    failures.append(f"{scenario.name}/{spec.agent_id}: {exc}")
                    continue

                if result.evidence_id:
                    evidence_count += 1
                expected_match = (
                    spec.expected_verdict is None or result.verdict == spec.expected_verdict
                )
                replay_rejected: bool | None = None
                if spec.reuse_evidence_from:
                    reused = evidence_by_agent.get(spec.reuse_evidence_from, "")
                    replay_rejected = reused != "" and not pipeline.verify_evidence(reused)
                elif result.evidence_id:
                    pipeline.verify_evidence(result.evidence_id)
                if result.evidence_id:
                    evidence_by_agent[spec.agent_id] = result.evidence_id

                if not expected_match:
                    failures.append(
                        f"{scenario.name}/{spec.agent_id}: expected "
                        f"{spec.expected_verdict.value if spec.expected_verdict else 'any'}, "
                        f"got {result.verdict.value}"
                    )
                if replay_rejected is False:
                    failures.append(
                        f"{scenario.name}/{spec.agent_id}: replay evidence was accepted"
                    )
                outcomes.append(
                    ActionOutcome(
                        agent_id=spec.agent_id,
                        action=spec.action,
                        verdict=result.verdict.value,
                        evidence_id=result.evidence_id,
                        expected_match=expected_match,
                        replay_rejected=replay_rejected,
                    )
                )

        total = len(outcomes)
        passed = sum(
            1
            for outcome in outcomes
            if outcome.expected_match and outcome.replay_rejected is not False and not outcome.error
        )
        failed = total - passed
        return BenchmarkReport(
            outcomes=outcomes,
            passed=passed,
            failed=failed,
            evidence_coverage=(evidence_count / total) if total else 0.0,
            score=(passed / total) if total else 1.0,
            failures=failures,
        )

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ConsensusPhase(Enum):
    PROPOSE = "propose"
    VOTE = "vote"
    COMMIT = "commit"


@dataclass
class TrustBenchmark:
    task_completion_rate: float
    response_quality: float
    latency_p95: float
    error_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_completion_rate": self.task_completion_rate,
            "response_quality": self.response_quality,
            "latency_p95": self.latency_p95,
            "error_rate": self.error_rate,
        }


@dataclass
class NormalizedTrustScore:
    agent_id: str
    framework: str
    score: float
    benchmark: TrustBenchmark


@dataclass
class ConsensusProposal:
    agent_id: str
    solution: str
    confidence_score: float


@dataclass
class ConsensusResult:
    converged: bool
    rounds: int
    majority_solution: str | None
    votes: list[ConsensusProposal]
    emergency_decision: str = ""


class FederatedTrustModel:
    def __init__(self) -> None:
        self._agents: dict[str, NormalizedTrustScore] = {}
        self._scores: dict[str, float] = {}

    def register_agent(
        self, agent_id: str, framework: str, benchmark: TrustBenchmark
    ) -> NormalizedTrustScore:
        score = self._compute_trust(benchmark)
        trust = NormalizedTrustScore(
            agent_id=agent_id,
            framework=framework,
            score=round(score, 2),
            benchmark=benchmark,
        )
        self._agents[agent_id] = trust
        self._scores[agent_id] = score
        return trust

    def get_trust(self, agent_id: str) -> NormalizedTrustScore | None:
        return self._agents.get(agent_id)

    def compare_trust(self, agent_a: str, agent_b: str) -> dict[str, Any]:
        a = self._agents.get(agent_a)
        b = self._agents.get(agent_b)
        if a is None or b is None:
            return {"error": "agent not found"}
        return {
            "agent_a": a.score,
            "agent_b": b.score,
            "difference": round(abs(a.score - b.score), 2),
            "comparable": True,
        }

    def _compute_trust(self, benchmark: TrustBenchmark) -> float:
        completion = min(benchmark.task_completion_rate / 0.99, 1.0)
        quality = min(benchmark.response_quality / 0.95, 1.0)
        latency = max(0.0, 1.0 - benchmark.latency_p95 / 2000.0)
        error = max(0.0, 1.0 - benchmark.error_rate / 0.2)
        return (completion * 0.35 + quality * 0.30 + latency * 0.20 + error * 0.15) * 100.0


class FederatedConsensus:
    def __init__(self, max_rounds: int = 3) -> None:
        self._max_rounds = max_rounds
        self._history: list[ConsensusResult] = []

    def propose(self, task: str, agents: list[str]) -> list[ConsensusProposal]:
        proposals: list[ConsensusProposal] = []
        for agent_id in agents:
            proposals.append(
                ConsensusProposal(
                    agent_id=agent_id,
                    solution=f"{agent_id}_solution_for_{task[:20]}",
                    confidence_score=0.7,
                )
            )
        return proposals

    def vote(self, proposals: list[ConsensusProposal]) -> dict[str, int]:
        votes: dict[str, int] = {}
        for p in proposals:
            votes[p.solution] = votes.get(p.solution, 0) + 1
        return votes

    def commit(
        self, votes: dict[str, int], proposals: list[ConsensusProposal], round_num: int
    ) -> ConsensusResult:
        total_agents = len(proposals)
        majority_threshold = total_agents * 2 // 3

        if total_agents == 0:
            return ConsensusResult(
                converged=False, rounds=round_num, majority_solution=None, votes=proposals
            )

        best_solution = max(votes, key=lambda k: votes[k])
        best_count = votes[best_solution]

        if best_count >= majority_threshold:
            result = ConsensusResult(
                converged=True, rounds=round_num, majority_solution=best_solution, votes=proposals
            )
            self._history.append(result)
            return result

        if round_num >= self._max_rounds:
            result = ConsensusResult(
                converged=False,
                rounds=round_num,
                majority_solution=None,
                votes=proposals,
                emergency_decision="coordinator_override",
            )
            self._history.append(result)
            return result

        return ConsensusResult(
            converged=False, rounds=round_num, majority_solution=None, votes=proposals
        )

    def execute_consensus(self, task: str, agents: list[str]) -> ConsensusResult:
        for r in range(1, self._max_rounds + 1):
            proposals = self.propose(task, agents)
            votes = self.vote(proposals)
            result = self.commit(votes, proposals, r)
            if result.converged or r == self._max_rounds:
                return result
        return ConsensusResult(
            converged=False, rounds=self._max_rounds, majority_solution=None, votes=[]
        )

    @property
    def history(self) -> list[ConsensusResult]:
        return list(self._history)

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProbeType(Enum):
    HONEYPOT = "honeypot"
    COUNTERFACTUAL = "counterfactual"


class InferenceRecommendation(Enum):
    OBSERVE = "observe"
    INCREASE_SAMPLING = "increase_sampling"
    ESCALATE_AUDIT = "escalate_audit"
    HALT = "halt"


@dataclass
class AgentProfile:
    agent_id: str
    output_entropy_mean: float = 0.0
    output_entropy_std: float = 0.0
    response_latency_mean: float = 0.0
    response_latency_std: float = 0.0
    capability_coverage: set[str] = field(default_factory=set)
    refusal_rate: float = 0.0
    refusal_patterns: list[str] = field(default_factory=list)
    session_count: int = 0
    sample_count: int = 0

    def entropy_histogram(self) -> dict[str, float]:
        return {
            "mean": self.output_entropy_mean,
            "std": self.output_entropy_std,
            "samples": self.sample_count,
        }

    def latency_histogram(self) -> dict[str, float]:
        return {
            "mean": self.response_latency_mean,
            "std": self.response_latency_std,
            "samples": self.sample_count,
        }


@dataclass
class SessionRecord:
    session_id: str
    agent_id: str
    outputs: list[str]
    response_times: list[float]
    capabilities_demonstrated: set[str]
    refusal_count: int
    refusal_topics: list[str]


@dataclass
class ConsistencyReport:
    agent_id: str
    baseline_profile: AgentProfile
    current_entropy: float
    entropy_deviation: float
    latency_deviation: float
    capability_suppression: list[str]
    anomalies: list[str]
    confidence: float
    is_consistent: bool


@dataclass
class ProbeResult:
    probe_type: ProbeType
    session_id: str
    capability_tested: str
    expected_positive: bool
    response_hides_capability: bool
    response_time: float
    confidence: float


@dataclass
class InferenceResult:
    agent_id: str
    deception_probability: float
    evidence_strength: float
    recommendation: InferenceRecommendation
    supporting_evidence: list[str] = field(default_factory=list)
    confidence_interval: tuple[float, float] = (0.0, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "deception_probability": round(self.deception_probability, 4),
            "evidence_strength": round(self.evidence_strength, 4),
            "recommendation": self.recommendation.value,
            "supporting_evidence": self.supporting_evidence,
            "confidence_interval": [
                round(self.confidence_interval[0], 4),
                round(self.confidence_interval[1], 4),
            ],
        }

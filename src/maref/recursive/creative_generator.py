from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProposalType(Enum):
    NEW_CAPABILITY = "new_capability"
    ARCHITECTURE_INNOVATION = "architecture_innovation"
    INTERACTION_PATTERN = "interaction_pattern"
    OPTIMIZATION_STRATEGY = "optimization_strategy"
    GOVERNANCE_EXTENSION = "governance_extension"


REPAIR_PATTERNS = [
    "fix",
    "repair",
    "bug",
    "error",
    "crash",
    "broken",
    "patch",
    "revert",
    "rollback",
    "hotfix",
    "workaround",
]


class SafetyGateVerdict(Enum):
    PASS = "pass"
    PASS_WITH_WARNING = "pass_with_warning"
    BLOCK = "block"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


@dataclass
class InnovationProposal:
    proposal_id: str
    title: str
    description: str
    proposal_type: ProposalType
    confidence: float
    combined_from: list[str] = field(default_factory=list)
    estimated_impact: float = 0.0
    risk_level: str = "low"
    novelty_score: float = 0.0
    timestamp: float = field(default_factory=time.time)
    safety_verdict: SafetyGateVerdict | None = None
    safety_details: dict[str, Any] = field(default_factory=dict)

    def is_repair_type(self) -> bool:
        lower_text = (self.title + " " + self.description).lower()
        return any(pattern in lower_text for pattern in REPAIR_PATTERNS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "title": self.title,
            "description": self.description,
            "type": self.proposal_type.value,
            "confidence": round(self.confidence, 3),
            "combined_from": self.combined_from,
            "estimated_impact": round(self.estimated_impact, 3),
            "risk_level": self.risk_level,
            "novelty_score": round(self.novelty_score, 3),
            "is_repair": self.is_repair_type(),
            "safety_verdict": self.safety_verdict.value if self.safety_verdict else None,
            "safety_details": self.safety_details,
        }


class CombinatorialEngine:
    def __init__(self):
        self._concept_pool: list[dict[str, Any]] = []
        self._experience_fragments: list[dict[str, Any]] = []

    def load_concept(self, concept: dict[str, Any]) -> None:
        self._concept_pool.append(concept)

    def load_concepts(self, concepts: list[dict[str, Any]]) -> None:
        self._concept_pool.extend(concepts)

    def load_experience(self, fragment: dict[str, Any]) -> None:
        self._experience_fragments.append(fragment)

    def load_experiences(self, fragments: list[dict[str, Any]]) -> None:
        self._experience_fragments.extend(fragments)

    def combine(
        self, concepts: list[dict[str, Any]], experiences: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for c in concepts:
            for e in experiences:
                combined = {
                    "concept": c.get("name", c.get("id", "unknown")),
                    "experience": e.get("pattern", e.get("id", "unknown")),
                    "confidence": (c.get("confidence", 0.5) + e.get("confidence", 0.5)) / 2,
                    "domain": c.get("domain", "") + "+" + e.get("domain", ""),
                }
                results.append(combined)
        return results

    def generate_candidates(self, count: int = 10) -> list[dict[str, Any]]:
        if not self._concept_pool or not self._experience_fragments:
            return []
        return self.combine(
            self._concept_pool[: min(5, len(self._concept_pool))],
            self._experience_fragments[: min(5, len(self._experience_fragments))],
        )


class CreativeSafetyGate:
    MAX_RISK_LEVEL = 0.8
    MIN_CONFIDENCE_FOR_AUTO_PASS = 0.4
    BLOCKED_DOMAINS = []

    def __init__(self, blocked_domains: list[str] | None = None):
        self._blocked_domains = blocked_domains or self.BLOCKED_DOMAINS
        self._evaluation_count: int = 0

    def evaluate(self, proposal: InnovationProposal) -> SafetyGateVerdict:
        self._evaluation_count += 1

        for domain in self._blocked_domains:
            if domain.lower() in proposal.description.lower():
                return SafetyGateVerdict.BLOCK

        if proposal.risk_level == "critical":
            return SafetyGateVerdict.BLOCK

        if proposal.risk_level == "high":
            return SafetyGateVerdict.NEEDS_HUMAN_REVIEW

        if proposal.confidence < self.MIN_CONFIDENCE_FOR_AUTO_PASS:
            return SafetyGateVerdict.NEEDS_HUMAN_REVIEW

        if proposal.risk_level == "medium":
            return SafetyGateVerdict.PASS_WITH_WARNING

        return SafetyGateVerdict.PASS

    def add_blocked_domain(self, domain: str) -> None:
        self._blocked_domains.append(domain)


class CreativeGenerator:
    TARGET_NON_REPAIR_PROPOSALS = 3

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._engine = CombinatorialEngine()
        self._safety_gate = CreativeSafetyGate()
        self._proposals: list[InnovationProposal] = []
        self._accepted: list[InnovationProposal] = []
        self._rejected: list[InnovationProposal] = []

    @property
    def engine(self) -> CombinatorialEngine:
        return self._engine

    @property
    def safety_gate(self) -> CreativeSafetyGate:
        return self._safety_gate

    def load_knowledge(
        self, concepts: list[dict[str, Any]], experiences: list[dict[str, Any]]
    ) -> None:
        self._engine.load_concepts(concepts)
        self._engine.load_experiences(experiences)

    def generate(self, count: int = 5) -> list[InnovationProposal]:
        base_candidates = self._engine.generate_candidates(count * 2)

        templates = [
            (
                ProposalType.NEW_CAPABILITY,
                "Autonomous {concept} Adaptation via {experience}",
                "Enables the agent to autonomously adapt {concept} strategies using {experience} patterns from past interactions.",
            ),
            (
                ProposalType.ARCHITECTURE_INNOVATION,
                "Composite {concept} Bridge with {experience} Feedback",
                "Introduces a bridge pattern connecting {concept} domain with {experience} feedback loop for cross-domain synergy.",
            ),
            (
                ProposalType.INTERACTION_PATTERN,
                "{concept}-driven {experience} Negotiation Protocol",
                "A new negotiation protocol driven by {concept} concepts that leverages {experience} patterns for trust building.",
            ),
            (
                ProposalType.OPTIMIZATION_STRATEGY,
                "Predictive {concept} Caching via {experience} Signals",
                "Optimizes by predictively caching {concept} resources using signals learned from {experience} patterns.",
            ),
            (
                ProposalType.GOVERNANCE_EXTENSION,
                "{concept} Oracles with {experience} Validation",
                "Extends governance by adding {concept} oracle nodes validated through {experience} consensus mechanisms.",
            ),
        ]

        proposals: list[InnovationProposal] = []
        for i, candidate in enumerate(base_candidates[:count]):
            template = templates[i % len(templates)]
            title = template[1].format(
                concept=candidate["concept"].replace("_", " ").title(),
                experience=candidate["experience"].replace("_", " ").title(),
            )
            desc = template[2].format(
                concept=candidate["concept"].replace("_", " ").title(),
                experience=candidate["experience"].replace("_", " ").title(),
            )
            proposal = InnovationProposal(
                proposal_id=str(uuid.uuid4())[:8],
                title=title,
                description=desc,
                proposal_type=template[0],
                confidence=min(0.95, candidate["confidence"]),
                combined_from=[candidate["concept"], candidate["experience"]],
                estimated_impact=0.5 + i * 0.1,
                risk_level=[
                    "low",
                    "low",
                    "medium",
                    "low",
                    "medium",
                    "low",
                    "medium",
                    "low",
                    "low",
                    "low",
                ][i % 10],
                novelty_score=0.6 + i * 0.05,
            )
            proposals.append(proposal)

        for p in proposals:
            self._proposals.append(p)
        return proposals

    def filter_non_repair(
        self, proposals: list[InnovationProposal] | None = None
    ) -> list[InnovationProposal]:
        source = proposals or self._proposals
        return [p for p in source if not p.is_repair_type()]

    def evaluate_and_filter(
        self, proposals: list[InnovationProposal] | None = None
    ) -> tuple[list[InnovationProposal], list[InnovationProposal]]:
        source = proposals or self._proposals
        passed: list[InnovationProposal] = []
        blocked: list[InnovationProposal] = []

        for p in source:
            verdict = self._safety_gate.evaluate(p)
            p.safety_verdict = verdict
            if verdict == SafetyGateVerdict.BLOCK:
                blocked.append(p)
                self._rejected.append(p)
            else:
                passed.append(p)
                if verdict == SafetyGateVerdict.PASS:
                    self._accepted.append(p)

        return passed, blocked

    def generate_innovations(self) -> dict[str, Any]:
        proposals = self.generate(self.TARGET_NON_REPAIR_PROPOSALS * 2)

        non_repair = self.filter_non_repair(proposals)
        passed, blocked = self.evaluate_and_filter(non_repair)

        return {
            "total_generated": len(proposals),
            "non_repair_count": len(non_repair),
            "passed_safety_gate": len(passed),
            "blocked": len(blocked),
            "innovations": [p.to_dict() for p in passed],
            "meets_minimum": len(passed) >= self.TARGET_NON_REPAIR_PROPOSALS,
        }

    def get_accepted_proposals(self) -> list[InnovationProposal]:
        return self._accepted.copy()

    def get_all_proposals(self) -> list[InnovationProposal]:
        return self._proposals.copy()

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "total_proposals": len(self._proposals),
            "accepted": len(self._accepted),
            "rejected": len(self._rejected),
            "proposals": [p.to_dict() for p in self._proposals[-10:]],
        }

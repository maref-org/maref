from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.evolution.shadow_registry import ShadowRegistry


class FractureType(Enum):
    KNOWLEDGE_CONFIDENCE = "knowledge_confidence"
    SYSTEMIC_FAILURE = "systemic_failure"
    TRUST_DECAY = "trust_decay"
    LINEAGE_DIVERGENCE = "lineage_divergence"
    TOOL_MISUSE_PATTERN = "tool_misuse_pattern"


class StratumStatus(Enum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    VALIDATED = "validated"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


@dataclass
class FractureReport:
    fracture_id: str
    fracture_type: FractureType
    agent_ids: list[str]
    death_causes: list[str]
    severity: float
    description: str
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fracture_id": self.fracture_id,
            "fracture_type": self.fracture_type.value,
            "agent_ids": self.agent_ids,
            "death_causes": self.death_causes,
            "severity": round(self.severity, 4),
            "description": self.description,
            "detected_at": self.detected_at,
        }


@dataclass
class Stratum:
    stratum_id: str
    fracture_id: str
    fracture_type: FractureType
    description: str
    healing_strategy: str
    affected_agents: list[str]
    new_knowledge: list[str]
    corrected_biases: dict[str, float]
    status: StratumStatus = StratumStatus.PROPOSED
    created_at: float = field(default_factory=time.time)
    validated_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stratum_id": self.stratum_id,
            "fracture_id": self.fracture_id,
            "fracture_type": self.fracture_type.value,
            "description": self.description,
            "healing_strategy": self.healing_strategy,
            "affected_agents": self.affected_agents,
            "new_knowledge": self.new_knowledge,
            "corrected_biases": {
                k: round(v, 4) for k, v in self.corrected_biases.items()
            },
            "status": self.status.value,
            "created_at": self.created_at,
            "validated_at": self.validated_at,
        }

    def apply(self) -> None:
        self.status = StratumStatus.APPLIED

    def validate(self) -> None:
        self.status = StratumStatus.VALIDATED
        self.validated_at = time.time()

    def reject(self) -> None:
        self.status = StratumStatus.REJECTED

    def supersede(self) -> None:
        self.status = StratumStatus.SUPERSEDED


FRACTURE_DESCRIPTIONS: dict[FractureType, str] = {
    FractureType.KNOWLEDGE_CONFIDENCE: (
        "Agent exhibited high confidence incorrect reasoning leading to hallucination. "
        "Stratum should inject reality-anchoring constraints."
    ),
    FractureType.SYSTEMIC_FAILURE: (
        "Multiple agents failed from same cause. Systemic pattern detected. "
        "Stratum should harden shared infrastructure."
    ),
    FractureType.TRUST_DECAY: (
        "Agent trust legacy consistently declining across lives. "
        "Stratum should recalibrate trust evaluation metrics."
    ),
    FractureType.LINEAGE_DIVERGENCE: (
        "Agent lineage shows divergent failure patterns between generations. "
        "Stratum should re-align evolution paths."
    ),
    FractureType.TOOL_MISUSE_PATTERN: (
        "Agent consistently misusing specific tools across lives. "
        "Stratum should add tool-call validation layers."
    ),
}


class LoRAMendingEngine:
    HALLUCINATION_FRACTURE_TRUST_THRESHOLD = 0.6
    SYSTEMIC_FRACTURE_MIN_AGENTS = 3
    TRUST_DECAY_MIN_LIVES = 2

    def __init__(self, shadow_registry: ShadowRegistry) -> None:
        self._shadow = shadow_registry
        self._fractures: dict[str, FractureReport] = {}
        self._strata: dict[str, Stratum] = {}

    def detect_knowledge_confidence_fractures(self) -> list[FractureReport]:
        entries = self._shadow.get_by_death_cause("hallucination")
        agent_groups: dict[str, list[Any]] = {}
        for e in entries:
            agent_groups.setdefault(e.agent_id, []).append(e)

        found: list[FractureReport] = []
        for agent_id, agent_entries in agent_groups.items():
            avg_trust = sum(e.trust_legacy for e in agent_entries) / len(agent_entries)
            if avg_trust > self.HALLUCINATION_FRACTURE_TRUST_THRESHOLD:
                fid = f"frac-kc-{agent_id}-{uuid.uuid4().hex[:6]}"
                report = FractureReport(
                    fracture_id=fid,
                    fracture_type=FractureType.KNOWLEDGE_CONFIDENCE,
                    agent_ids=[agent_id],
                    death_causes=["hallucination"],
                    severity=avg_trust,
                    description=FRACTURE_DESCRIPTIONS[FractureType.KNOWLEDGE_CONFIDENCE],
                )
                self._fractures[fid] = report
                found.append(report)
        return found

    def detect_systemic_failure_fractures(self) -> list[FractureReport]:
        entries = self._shadow.get_all()
        cause_counts: dict[str, list[str]] = {}
        for e in entries:
            cause_counts.setdefault(e.death_cause, []).append(e.agent_id)

        found: list[FractureReport] = []
        for cause, agents in cause_counts.items():
            unique_agents = list(set(agents))
            if len(unique_agents) >= self.SYSTEMIC_FRACTURE_MIN_AGENTS:
                fid = f"frac-sf-{cause}-{uuid.uuid4().hex[:6]}"
                report = FractureReport(
                    fracture_id=fid,
                    fracture_type=FractureType.SYSTEMIC_FAILURE,
                    agent_ids=unique_agents,
                    death_causes=[cause],
                    severity=len(unique_agents) / 10.0,
                    description=FRACTURE_DESCRIPTIONS[FractureType.SYSTEMIC_FAILURE],
                )
                self._fractures[fid] = report
                found.append(report)
        return found

    def detect_trust_decay_fractures(self) -> list[FractureReport]:
        entries = self._shadow.get_all()
        agent_entries: dict[str, list[Any]] = {}
        for e in entries:
            agent_entries.setdefault(e.agent_id, []).append(e)

        found: list[FractureReport] = []
        for agent_id, agent_entries_list in agent_entries.items():
            if len(agent_entries_list) < self.TRUST_DECAY_MIN_LIVES:
                continue
            sorted_by_time = sorted(agent_entries_list, key=lambda x: x.timestamp)
            trust_values = [e.trust_legacy for e in sorted_by_time]
            if trust_values[-1] < trust_values[0] * 0.5:
                fid = f"frac-td-{agent_id}-{uuid.uuid4().hex[:6]}"
                report = FractureReport(
                    fracture_id=fid,
                    fracture_type=FractureType.TRUST_DECAY,
                    agent_ids=[agent_id],
                    death_causes=[e.death_cause for e in sorted_by_time],
                    severity=trust_values[0] - trust_values[-1],
                    description=FRACTURE_DESCRIPTIONS[FractureType.TRUST_DECAY],
                )
                self._fractures[fid] = report
                found.append(report)
        return found

    def detect_all_fractures(self) -> list[FractureReport]:
        results: list[FractureReport] = []
        results.extend(self.detect_knowledge_confidence_fractures())
        results.extend(self.detect_systemic_failure_fractures())
        results.extend(self.detect_trust_decay_fractures())
        return results

    def create_stratum(self, fracture_id: str) -> Stratum | None:
        report = self._fractures.get(fracture_id)
        if report is None:
            return None

        sid = f"stratum-{uuid.uuid4().hex[:10]}"
        fracture_type = report.fracture_type

        corrected_biases: dict[str, float] = {
            "confidence_penalty": -0.1,
            "tool_validation_weight": 0.15,
            "trust_recalibration_rate": 0.05,
        }

        new_knowledge: list[str] = []
        if fracture_type == FractureType.KNOWLEDGE_CONFIDENCE:
            new_knowledge = [
                "apply_reality_anchoring_on_high_confidence",
                "cross_validate_before_execution",
            ]
            corrected_biases["reality_anchor_weight"] = 0.2
        elif fracture_type == FractureType.SYSTEMIC_FAILURE:
            new_knowledge = [
                "hardened_infrastructure_for_shared_failure",
                "circuit_breaker_on_systemic_cause",
            ]
            corrected_biases["systemic_resilience_weight"] = 0.25
        elif fracture_type == FractureType.TRUST_DECAY:
            new_knowledge = [
                "trust_decay_monitoring",
                "adaptive_trust_recalibration",
            ]
            corrected_biases["adaptive_trust_factor"] = 0.15

        stratum = Stratum(
            stratum_id=sid,
            fracture_id=fracture_id,
            fracture_type=fracture_type,
            description=f"LoRA stratum for {fracture_type.value}: {report.description[:60]}",
            healing_strategy=f"Apply corrected biases and inject {len(new_knowledge)} knowledge patches",
            affected_agents=report.agent_ids,
            new_knowledge=new_knowledge,
            corrected_biases=corrected_biases,
        )

        self._strata[sid] = stratum
        return stratum

    def heal_fracture(self, fracture_id: str) -> Stratum | None:
        stratum = self.create_stratum(fracture_id)
        if stratum is not None:
            stratum.apply()
            stratum.validate()
        return stratum

    def heal_all_fractures(self) -> list[Stratum]:
        self.detect_all_fractures()
        strata: list[Stratum] = []
        for fid in self._fractures:
            s = self.heal_fracture(fid)
            if s is not None:
                strata.append(s)
        return strata

    def get_fracture(self, fracture_id: str) -> FractureReport | None:
        return self._fractures.get(fracture_id)

    def get_stratum(self, stratum_id: str) -> Stratum | None:
        return self._strata.get(stratum_id)

    def get_all_fractures(self) -> list[FractureReport]:
        return list(self._fractures.values())

    def get_all_strata(self) -> list[Stratum]:
        return list(self._strata.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_fractures": len(self._fractures),
            "total_strata": len(self._strata),
            "fractures": [f.to_dict() for f in self._fractures.values()],
            "strata": [s.to_dict() for s in self._strata.values()],
        }

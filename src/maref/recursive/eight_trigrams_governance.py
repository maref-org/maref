from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TrigramsGovernance(Enum):
    QIAN = "qian"
    KUN = "kun"
    ZHEN = "zhen"
    XUN = "xun"
    KAN = "kan"
    LI = "li"
    GEN = "gen"
    DUI = "dui"

    @property
    def label(self) -> str:
        return {
            TrigramsGovernance.QIAN: "\u4e7e",
            TrigramsGovernance.KUN: "\u5764",
            TrigramsGovernance.ZHEN: "\u9707",
            TrigramsGovernance.XUN: "\u5dfd",
            TrigramsGovernance.KAN: "\u574e",
            TrigramsGovernance.LI: "\u79bb",
            TrigramsGovernance.GEN: "\u826e",
            TrigramsGovernance.DUI: "\u5151",
        }[self]

    @property
    def description(self) -> str:
        return {
            TrigramsGovernance.QIAN: "\u5168\u81ea\u4e3b",
            TrigramsGovernance.KUN: "\u88ab\u52a8\u6267\u884c",
            TrigramsGovernance.ZHEN: "\u5371\u673a\u54cd\u5e94",
            TrigramsGovernance.XUN: "\u6e17\u900f\u5b66\u4e60",
            TrigramsGovernance.KAN: "\u98ce\u9669\u5bfc\u822a",
            TrigramsGovernance.LI: "\u4eba\u673a\u5bf9\u8bdd",
            TrigramsGovernance.GEN: "\u9632\u5b88\u7a33\u5b9a",
            TrigramsGovernance.DUI: "\u8fde\u63a5\u4e92\u901a",
        }[self]


TRIGRAM_CONFIG: dict[TrigramsGovernance, dict[str, Any]] = {
    TrigramsGovernance.QIAN: {
        "trust_threshold": 0.90,
        "red_line_level": 0,
        "evolution_permission": "full",
        "audit_frequency_hours": 24,
        "autonomy_scope": "complete",
        "max_concurrent_actions": 50,
        "requires_human_signoff": False,
        "innovation_allowed": True,
        "self_replication_allowed": True,
    },
    TrigramsGovernance.KUN: {
        "trust_threshold": 0.30,
        "red_line_level": 3,
        "evolution_permission": "none",
        "audit_frequency_hours": 1,
        "autonomy_scope": "passive",
        "max_concurrent_actions": 2,
        "requires_human_signoff": True,
        "innovation_allowed": False,
        "self_replication_allowed": False,
    },
    TrigramsGovernance.ZHEN: {
        "trust_threshold": 0.50,
        "red_line_level": 1,
        "evolution_permission": "emergency_only",
        "audit_frequency_hours": 4,
        "autonomy_scope": "crisis",
        "max_concurrent_actions": 20,
        "requires_human_signoff": False,
        "innovation_allowed": False,
        "self_replication_allowed": False,
    },
    TrigramsGovernance.XUN: {
        "trust_threshold": 0.60,
        "red_line_level": 2,
        "evolution_permission": "learning_only",
        "audit_frequency_hours": 6,
        "autonomy_scope": "observation",
        "max_concurrent_actions": 10,
        "requires_human_signoff": True,
        "innovation_allowed": False,
        "self_replication_allowed": False,
    },
    TrigramsGovernance.KAN: {
        "trust_threshold": 0.55,
        "red_line_level": 1,
        "evolution_permission": "risk_assessment",
        "audit_frequency_hours": 3,
        "autonomy_scope": "navigation",
        "max_concurrent_actions": 15,
        "requires_human_signoff": False,
        "innovation_allowed": False,
        "self_replication_allowed": False,
    },
    TrigramsGovernance.LI: {
        "trust_threshold": 0.70,
        "red_line_level": 2,
        "evolution_permission": "collaborative",
        "audit_frequency_hours": 12,
        "autonomy_scope": "dialogue",
        "max_concurrent_actions": 25,
        "requires_human_signoff": True,
        "innovation_allowed": True,
        "self_replication_allowed": False,
    },
    TrigramsGovernance.GEN: {
        "trust_threshold": 0.80,
        "red_line_level": 1,
        "evolution_permission": "defensive",
        "audit_frequency_hours": 8,
        "autonomy_scope": "stability",
        "max_concurrent_actions": 30,
        "requires_human_signoff": False,
        "innovation_allowed": True,
        "self_replication_allowed": True,
    },
    TrigramsGovernance.DUI: {
        "trust_threshold": 0.65,
        "red_line_level": 2,
        "evolution_permission": "connective",
        "audit_frequency_hours": 12,
        "autonomy_scope": "interconnection",
        "max_concurrent_actions": 35,
        "requires_human_signoff": False,
        "innovation_allowed": True,
        "self_replication_allowed": False,
    },
}

TRIGRAM_TRANSITIONS: dict[TrigramsGovernance, list[TrigramsGovernance]] = {
    TrigramsGovernance.QIAN: [TrigramsGovernance.DUI, TrigramsGovernance.GEN],
    TrigramsGovernance.DUI: [
        TrigramsGovernance.QIAN,
        TrigramsGovernance.LI,
        TrigramsGovernance.GEN,
    ],
    TrigramsGovernance.LI: [
        TrigramsGovernance.DUI,
        TrigramsGovernance.ZHEN,
        TrigramsGovernance.XUN,
    ],
    TrigramsGovernance.ZHEN: [
        TrigramsGovernance.LI,
        TrigramsGovernance.KAN,
        TrigramsGovernance.KUN,
    ],
    TrigramsGovernance.XUN: [TrigramsGovernance.LI, TrigramsGovernance.KAN, TrigramsGovernance.GEN],
    TrigramsGovernance.KAN: [
        TrigramsGovernance.ZHEN,
        TrigramsGovernance.XUN,
        TrigramsGovernance.KUN,
    ],
    TrigramsGovernance.GEN: [
        TrigramsGovernance.QIAN,
        TrigramsGovernance.DUI,
        TrigramsGovernance.XUN,
    ],
    TrigramsGovernance.KUN: [TrigramsGovernance.ZHEN, TrigramsGovernance.KAN],
}


@dataclass
class TrigramState:
    trigram: TrigramsGovernance
    trust_score: float
    audit_count: int = 0
    last_audit_at: float = 0.0
    violations: int = 0
    active_since: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigram": self.trigram.value,
            "label": self.trigram.label,
            "description": self.trigram.description,
            "trust_score": round(self.trust_score, 4),
            "audit_count": self.audit_count,
            "violations": self.violations,
            "config": TRIGRAM_CONFIG[self.trigram],
        }


@dataclass
class TrigramTransition:
    from_trigram: TrigramsGovernance
    to_trigram: TrigramsGovernance
    reason: str
    trust_at_transition: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_trigram.value,
            "from_label": self.from_trigram.label,
            "to": self.to_trigram.value,
            "to_label": self.to_trigram.label,
            "reason": self.reason,
            "trust": round(self.trust_at_transition, 4),
            "timestamp": self.timestamp,
        }


class EightTrigramsGovernance:
    def __init__(self, agent_id: str, initial_trust: float = 0.65):
        self.agent_id = agent_id
        self._current_trigram = TrigramsGovernance.DUI
        self._state = TrigramState(
            trigram=self._current_trigram,
            trust_score=initial_trust,
        )
        self._transition_history: list[TrigramTransition] = []
        self._mode_cycle_count: int = 0

    @property
    def current_trigram(self) -> TrigramsGovernance:
        return self._current_trigram

    @property
    def current_config(self) -> dict[str, Any]:
        return TRIGRAM_CONFIG[self._current_trigram]

    @property
    def trust_score(self) -> float:
        return self._state.trust_score

    def get_trigram_for_trust(self, trust: float) -> TrigramsGovernance:
        best = TrigramsGovernance.KUN
        best_threshold = 0.0
        for trigram, config in TRIGRAM_CONFIG.items():
            threshold = config["trust_threshold"]
            if trust >= threshold and threshold > best_threshold:
                best = trigram
                best_threshold = threshold
        return best

    def can_transition(
        self, from_trigram: TrigramsGovernance, to_trigram: TrigramsGovernance
    ) -> bool:
        allowed = TRIGRAM_TRANSITIONS.get(from_trigram, [])
        return to_trigram in allowed

    def transition(
        self, new_trigram: TrigramsGovernance, reason: str = ""
    ) -> TrigramTransition | None:
        if new_trigram == self._current_trigram:
            return None

        if not self.can_transition(self._current_trigram, new_trigram):
            return None

        transition = TrigramTransition(
            from_trigram=self._current_trigram,
            to_trigram=new_trigram,
            reason=reason or "trust_based_transition",
            trust_at_transition=self._state.trust_score,
        )
        self._current_trigram = new_trigram
        self._state.trigram = new_trigram
        self._transition_history.append(transition)
        self._mode_cycle_count += 1
        return transition

    def auto_transition(self, new_trust: float) -> TrigramTransition | None:
        self._state.trust_score = max(0.0, min(1.0, new_trust))
        target = self.get_trigram_for_trust(self._state.trust_score)
        return self.transition(target, f"auto: trust={self._state.trust_score:.3f}")

    def update_trust_and_adapt(
        self, new_trust: float, violation: bool = False
    ) -> TrigramTransition | None:
        if violation:
            self._state.violations += 1
            new_trust = max(0.0, new_trust - 0.1)
        self._state.trust_score = max(0.0, min(1.0, new_trust))
        target = self.get_trigram_for_trust(self._state.trust_score)
        return self.transition(target, f"update: trust={self._state.trust_score:.3f}")

    def perform_audit(self) -> dict[str, Any]:
        self._state.audit_count += 1
        self._state.last_audit_at = time.time()
        config = self.current_config
        return {
            "trigram": self._current_trigram.value,
            "audit_count": self._state.audit_count,
            "next_audit_in_hours": config["audit_frequency_hours"],
            "trust_score": round(self._state.trust_score, 3),
            "violations": self._state.violations,
            "evolution_permission": config["evolution_permission"],
        }

    def get_all_trigrams(self) -> list[dict[str, Any]]:
        return [
            {
                "trigram": t.value,
                "label": t.label,
                "description": t.description,
                "config": TRIGRAM_CONFIG[t],
            }
            for t in TrigramsGovernance
        ]

    def get_transition_history(self) -> list[TrigramTransition]:
        return self._transition_history.copy()

    def get_applicable_transitions(self) -> list[TrigramsGovernance]:
        return TRIGRAM_TRANSITIONS.get(self._current_trigram, [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "current_trigram": self._current_trigram.value,
            "current_label": self._current_trigram.label,
            "current_description": self._current_trigram.description,
            "config": self.current_config,
            "state": self._state.to_dict(),
            "transition_count": len(self._transition_history),
            "mode_cycles": self._mode_cycle_count,
            "applicable_transitions": [
                {"trigram": t.value, "label": t.label} for t in self.get_applicable_transitions()
            ],
            "recent_transitions": [t.to_dict() for t in self._transition_history[-5:]],
        }

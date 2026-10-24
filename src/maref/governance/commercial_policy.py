"""Commercial action risk policy (P0-A).

Loads ``configs/commercial_actions.yaml`` and classifies commercial agent
actions into L0-L3.  The classification drives route-evidence enforcement:
L2/L3 actions must carry a valid ``model_route_decision`` before they are
allowed to run.

The policy is fail-closed: unknown levels, malformed rules and unclassified
actions never silently become L0.  Unclassified actions fall back to
``default_level`` (L3 by default).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import yaml


class CommercialRiskLevel(str, Enum):
    """Commercial action risk levels (L0 read-only ... L3 funds/contracts)."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


_DEFAULT_ROUTE_REQUIRED = frozenset({CommercialRiskLevel.L2, CommercialRiskLevel.L3})
_LEVEL_RISK_SCORE: dict[CommercialRiskLevel, float] = {
    CommercialRiskLevel.L0: 5.0,
    CommercialRiskLevel.L1: 25.0,
    CommercialRiskLevel.L2: 60.0,
    CommercialRiskLevel.L3: 90.0,
}


@dataclass(frozen=True)
class CommercialAction:
    """Classification result for a single action."""

    action: str
    level: CommercialRiskLevel
    purpose_id: str
    matched_pattern: str = ""
    risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "level": self.level.value,
            "purpose_id": self.purpose_id,
            "matched_pattern": self.matched_pattern,
            "risk_score": self.risk_score,
        }


@dataclass(frozen=True)
class _ActionRule:
    pattern: str
    level: CommercialRiskLevel
    purpose_id: str


@dataclass
class CommercialActionPolicy:
    """Ordered action rules with fail-closed defaults."""

    actions: tuple[_ActionRule, ...] = ()
    default_level: CommercialRiskLevel = CommercialRiskLevel.L3
    route_required_levels: frozenset[CommercialRiskLevel] = field(
        default_factory=lambda: _DEFAULT_ROUTE_REQUIRED
    )
    version: str = ""
    epoch: str = ""
    source: str = ""
    document_hash: str = ""

    @classmethod
    def from_path(cls, path: str | Path) -> CommercialActionPolicy:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"Commercial action policy not found: {source}")
        raw = source.read_bytes()
        data = yaml.safe_load(raw.decode("utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Commercial action policy must be a mapping: {source}")
        policy = cls.from_dict(data, source=str(source))
        return CommercialActionPolicy(
            actions=policy.actions,
            default_level=policy.default_level,
            route_required_levels=policy.route_required_levels,
            version=policy.version,
            epoch=policy.epoch,
            source=policy.source,
            document_hash=hashlib.sha256(raw).hexdigest(),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "") -> CommercialActionPolicy:
        raw_actions = data.get("actions") or []
        if not isinstance(raw_actions, list):
            raise ValueError("commercial_actions.actions must be a list")

        actions: list[_ActionRule] = []
        for index, raw in enumerate(raw_actions):
            if not isinstance(raw, dict):
                raise ValueError(f"commercial_actions.actions[{index}] must be a mapping")
            pattern = str(raw.get("match", "")).strip()
            purpose_id = str(raw.get("purpose_id", "")).strip()
            if not pattern or not purpose_id:
                raise ValueError(
                    f"commercial_actions.actions[{index}] requires match and purpose_id"
                )
            actions.append(
                _ActionRule(
                    pattern=pattern,
                    level=_parse_level(raw.get("level"), context=f"actions[{index}]"),
                    purpose_id=purpose_id,
                )
            )

        required = data.get("route_required_levels")
        if required is None:
            route_required = _DEFAULT_ROUTE_REQUIRED
        else:
            if not isinstance(required, list):
                raise ValueError("route_required_levels must be a list")
            route_required = frozenset(
                _parse_level(value, context="route_required_levels") for value in required
            )

        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()
        return cls(
            actions=tuple(actions),
            default_level=_parse_level(data.get("default_level", "L3"), context="default_level"),
            route_required_levels=route_required,
            version=str(data.get("version", "")),
            epoch=str(data.get("epoch", "")),
            source=source,
            document_hash=hashlib.sha256(canonical).hexdigest(),
        )

    def classify(self, action: str) -> CommercialAction:
        for rule in self.actions:
            if fnmatchcase(action, rule.pattern):
                return CommercialAction(
                    action=action,
                    level=rule.level,
                    purpose_id=rule.purpose_id,
                    matched_pattern=rule.pattern,
                    risk_score=_LEVEL_RISK_SCORE[rule.level],
                )
        return CommercialAction(
            action=action,
            level=self.default_level,
            purpose_id="commerce.unclassified",
            matched_pattern="",
            risk_score=_LEVEL_RISK_SCORE[self.default_level],
        )

    def requires_route_evidence(self, action: str) -> bool:
        classification = self.classify(action)
        return classification.level in self.route_required_levels


def _parse_level(value: Any, *, context: str) -> CommercialRiskLevel:
    text = str(value or "").strip().upper()
    try:
        return CommercialRiskLevel(text)
    except ValueError as exc:
        raise ValueError(f"Invalid commercial risk level in {context}: {value!r}") from exc


__all__ = [
    "CommercialAction",
    "CommercialActionPolicy",
    "CommercialRiskLevel",
]

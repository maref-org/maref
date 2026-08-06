"""
MAREF DriftGuard Type Definitions

Core data structures for the LoRA drift detection pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class DriftSeverity(Enum):
    """Severity levels for detected drift."""

    NONE = auto()
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class DriftAction(Enum):
    """Actions the pipeline can take in response to drift."""

    NONE = auto()
    ALERT = auto()
    QUARANTINE = auto()
    BASE_RESET = auto()
    HUMAN_REVIEW = auto()
    EMERGENCY_HALT = auto()


class GateStatus(Enum):
    """Status of the human-in-the-loop arbitration gate."""

    AUTO = auto()
    PENDING_REVIEW = auto()
    APPROVED = auto()
    REJECTED = auto()
    TIMEOUT = auto()


@dataclass(frozen=True)
class ModelSignature:
    """Identifier for a model checkpoint."""

    name: str
    version: str
    checkpoint_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.name}:{self.version}"


@dataclass
class DriftReading:
    """A single drift measurement reading."""

    timestamp: datetime
    kl_divergence: float
    js_divergence: float
    hellinger_distance: float
    severity: DriftSeverity
    threshold: float
    model: ModelSignature
    baseline: ModelSignature

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "kl_divergence": self.kl_divergence,
            "js_divergence": self.js_divergence,
            "hellinger_distance": self.hellinger_distance,
            "severity": self.severity.name,
            "threshold": self.threshold,
            "model": str(self.model),
            "baseline": str(self.baseline),
        }


@dataclass
class DriftEvent:
    """A drift event that triggered an action."""

    event_id: str
    timestamp: datetime
    reading: DriftReading
    action_taken: DriftAction
    gate_status: GateStatus
    reason: str
    resolved: bool = False
    resolution_time: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "reading": self.reading.to_dict(),
            "action_taken": self.action_taken.name,
            "gate_status": self.gate_status.name,
            "reason": self.reason,
            "resolved": self.resolved,
            "resolution_time": (self.resolution_time.isoformat() if self.resolution_time else None),
        }


@dataclass
class PipelineConfig:
    """Configuration for the drift detection pipeline."""

    # KL divergence thresholds
    kl_warning: float = 0.1
    kl_critical: float = 0.5
    kl_max: float = 1.0

    # Hellinger distance thresholds
    hellinger_warning: float = 0.2
    hellinger_critical: float = 0.5

    # Gate configuration
    human_review_threshold: DriftSeverity = DriftSeverity.HIGH
    auto_action_threshold: DriftSeverity = DriftSeverity.MEDIUM
    review_timeout_seconds: float = 300.0

    # Base model reset config
    reset_on_critical: bool = True
    reset_cooldown_seconds: float = 60.0

    # Sampling config
    check_interval_seconds: float = 60.0
    sample_size: int = 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "kl_warning": self.kl_warning,
            "kl_critical": self.kl_critical,
            "kl_max": self.kl_max,
            "hellinger_warning": self.hellinger_warning,
            "hellinger_critical": self.hellinger_critical,
            "human_review_threshold": self.human_review_threshold.name,
            "auto_action_threshold": self.auto_action_threshold.name,
            "review_timeout_seconds": self.review_timeout_seconds,
            "reset_on_critical": self.reset_on_critical,
            "reset_cooldown_seconds": self.reset_cooldown_seconds,
            "check_interval_seconds": self.check_interval_seconds,
            "sample_size": self.sample_size,
        }

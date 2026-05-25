"""Skill Marketplace Layer for MAREF.

Provides skill registration, discovery, version negotiation, and reputation.

Key components:
- SkillRegistry: manifest-based skill registration with validation
- SemanticMatcher: task-to-skill vector matching
- VersionNegotiator: schema version compatibility checking
- ReputationTracker: skill success/failure scoring
"""

from maref.marketplace.registry import (
    SkillManifest,
    SkillRegistry,
    SkillValidationResult,
)
from maref.marketplace.semantic_matcher import (
    MatchScore,
    SemanticMatcher,
)
from maref.marketplace.version_negotiator import (
    VersionNegotiator,
    VersionNegotiationResult,
)
from maref.marketplace.reputation import (
    ReputationRecord,
    ReputationTracker,
)

__all__ = [
    "MatchScore",
    "ReputationRecord",
    "ReputationTracker",
    "SemanticMatcher",
    "SkillManifest",
    "SkillRegistry",
    "SkillValidationResult",
    "VersionNegotiator",
    "VersionNegotiationResult",
]

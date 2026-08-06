"""Skill Marketplace Layer for MAREF.

Provides skill registration, discovery, version negotiation, and reputation.

Key components:
- SkillRegistry: manifest-based skill registration with validation
- SemanticMatcher: task-to-skill vector matching
- VersionNegotiator: schema version compatibility checking
- ReputationTracker: skill success/failure scoring
"""

from maref.marketplace.adapter import ManifestAdapter
from maref.marketplace.execution import approve_and_execute, execute_skill
from maref.marketplace.loader import MarketplaceSkillLoader
from maref.marketplace.registry import (
    SkillManifest,
    SkillRegistry,
    SkillValidationResult,
)
from maref.marketplace.reputation import (
    ReputationRecord,
    ReputationTracker,
)
from maref.marketplace.semantic_matcher import (
    MatchScore,
    SemanticMatcher,
)
from maref.marketplace.version_negotiator import (
    VersionNegotiationResult,
    VersionNegotiator,
)

__all__ = [
    "ManifestAdapter",
    "MarketplaceSkillLoader",
    "MatchScore",
    "ReputationRecord",
    "ReputationTracker",
    "SemanticMatcher",
    "SkillManifest",
    "SkillRegistry",
    "SkillValidationResult",
    "VersionNegotiator",
    "VersionNegotiationResult",
    "approve_and_execute",
    "execute_skill",
]

"""MAREF Learning — meta-learning optimization, replay buffer, A/B comparison, adaptive goal discovery."""

from maref.learning.ab_test import (
    ABDecision,
    ABResult,
    ABWinner,
    MetricSnapshot,
    StrategyComparator,
)
from maref.learning.adaptive_goal_discovery import (
    AdaptiveGoalDiscoverer,
    GoalDiscoveryReport,
    ImprovementGoal,
)
from maref.learning.online_engine import (
    DOMAIN_PRIOR_TEMPLATES,
    OnlineLearningEngine,
    OnlineWeightRecord,
    build_domain_prior,
)
from maref.learning.replay import DecisionOutcome, ExperienceStore
from maref.learning.rewards import (
    MultiGranularityRewardAssembler,
    PotentialShaping,
    PotentialShapingConfig,
    RoleReward,
    RoleRewardFn,
)
from maref.learning.scheduler import LearningRateScheduler, SchedulerConfig, SchedulerState

__all__ = [
    "AdaptiveGoalDiscoverer",
    "GoalDiscoveryReport",
    "ImprovementGoal",
    "DecisionOutcome",
    "ExperienceStore",
    "LearningRateScheduler",
    "SchedulerConfig",
    "SchedulerState",
    "StrategyComparator",
    "ABResult",
    "ABDecision",
    "ABWinner",
    "MetricSnapshot",
    "OnlineLearningEngine",
    "OnlineWeightRecord",
    "DOMAIN_PRIOR_TEMPLATES",
    "build_domain_prior",
    "MultiGranularityRewardAssembler",
    "PotentialShaping",
    "PotentialShapingConfig",
    "RoleReward",
    "RoleRewardFn",
]

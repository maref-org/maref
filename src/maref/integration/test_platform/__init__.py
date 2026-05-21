"""
Agent Test Platform (MAS-TS-001) Integration Module

Provides the data-layer bridge between MAS-TS-001 evaluation reports
and MAREF governance state machine.

Components:
  - schema: Unified evaluation report schema (5 layers)
  - eval_observer: MASEvalObserver injects eval results into governance
  - card_adapter: Bidirectional Agent Card format conversion
  - score_mapper: Layer 5 score → 4-phase autonomy mapping
  - state_trigger: Fast-Screen/Full-Run → Gray Code transitions
  - tla_verifier: Runtime TLA+ theorem verification
"""

from maref.integration.test_platform.card_adapter import (
    MASAgentCard,
    AgentCardAdapter,
    MAS_TS001_AGENT_CARD_SCHEMA,
)
from maref.integration.test_platform.eval_observer import (
    Phase,
    ObserverAlert,
    MASEvalObserver,
)
from maref.integration.test_platform.schema import (
    EvalStatus,
    FindingSeverity,
    TestMode,
    Finding,
    LayerReport,
    EvaluationReport,
    build_findings_summary,
)
from maref.integration.test_platform.score_mapper import (
    PermissionLevel,
    PermissionSet,
    ScoreToPhaseMapper,
    LayerScoreAggregator,
)
from maref.integration.test_platform.state_trigger import (
    TriggerAction,
    StateTransitionDecision,
    FastScreenTrigger,
    FullRunTrigger,
    LayerSpecificTrigger,
    UnifiedTrigger,
)
from maref.integration.test_platform.tla_verifier import (
    TheoremResult,
    TLATheoremVerifier,
)
from maref.integration.test_platform.quality_gate import (
    EvolutionVerdict,
    QualityGateResult,
    QualityGateConfig,
    EvolutionQualityGate,
)

__all__ = [
    # Schema
    "EvalStatus",
    "FindingSeverity",
    "TestMode",
    "Finding",
    "LayerReport",
    "EvaluationReport",
    "build_findings_summary",
    # Observer
    "Phase",
    "ObserverAlert",
    "MASEvalObserver",
    # Card Adapter
    "MASAgentCard",
    "AgentCardAdapter",
    "MAS_TS001_AGENT_CARD_SCHEMA",
    # Score Mapper
    "PermissionLevel",
    "PermissionSet",
    "ScoreToPhaseMapper",
    "LayerScoreAggregator",
    # State Trigger
    "TriggerAction",
    "StateTransitionDecision",
    "FastScreenTrigger",
    "FullRunTrigger",
    "LayerSpecificTrigger",
    "UnifiedTrigger",
    # TLA+ Verifier
    "TheoremResult",
    "TLATheoremVerifier",
    # Quality Gate
    "EvolutionVerdict",
    "QualityGateResult",
    "QualityGateConfig",
    "EvolutionQualityGate",
]

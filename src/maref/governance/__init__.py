"""MAREF Governance — state machine + audit + circuit breaker + oscillation fix.

v0.36.0+: Unified governance pipeline (@governed decorator, GovernancePipeline,
GovernedPipeline) is available for auto-injection governance.
"""

from maref.governance.audit import AuditEntry, AuditLogger
from maref.governance.audit_bus import AuditBus
from maref.governance.budget_breaker import BudgetBreaker, BudgetBreakerState, BudgetBreakerTrip
from maref.governance.circuit_breaker import BreakerState, BreakerTrip, CircuitBreaker

# P1-A2 治理提案底线语义预检 (PoC 盲点 C)
from maref.governance.governance_baseline_gate import (
    BASELINE_PATTERNS,
    SOFT_PATTERNS,
    BaselineDecision,
    BaselineVerdict,
    GovernanceBaselineGate,
)

# v0.36.0+: Unified governance pipeline
from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    GovernanceResult,
    Verdict,
)
from maref.governance.cross_instance import (
    CrossInstanceGovernor,
    InstanceStatus,
    SyncResult,
    WeightPoisonDetector,
)
from maref.governance.decorators import (
    GovernanceDeniedError,
    get_default_pipeline,
    governed,
    set_default_pipeline,
)
from maref.governance.economic import (
    AgentInsurancePricing,
    BountyStatus,
    InvestmentCategory,
    RiskTier,
    SafetyInvestmentAuditor,
    VulnerabilityBountyBoard,
)
from maref.governance.geopolitical_risk import (
    JURISDICTION_REGISTRY,
    DataFlowRisk,
    GeoPoliticalRiskAssessor,
    Jurisdiction,
    JurisdictionMapper,
    RiskAssessment,
    RiskLevel,
    SovereignAIValidationResult,
    SovereignAIValidator,
)
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.oscillation import OscillationEvent, OscillationFixLoop, OscillationStage
from maref.governance.percv_hooks import (
    PERCVEventType,
    PERCVGovernanceHook,
    handle_percv_event,
)
from maref.governance.social_impact import (
    DeploymentVerdict,
    ImpactLevel,
    SocialImpactAssessor,
    SocialImpactReport,
)
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.threat_bridge import ThreatGovernanceBridge, ThreatGovernanceMapping
from maref.governance.trust_bridge import (
    GovernanceBridge,
    GovernanceQuery,
    RecursiveEvent,
    RecursiveEventType,
)
from maref.governance.types import GovernanceState, StateMachineSnapshot, StateTransition
from maref.governance.verifier_consensus import (
    ConsensusResult,
    ConsensusStrategy,
    VerifierConsensus,
)
from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry, VerifierStatus
from maref.metacognition import MetaCognitiveAuditor

# G2: Subgoal Interceptor
from maref.subgoal import (
    ControlRiskReport,
    CoTMonitor,
    CoTReport,
    CreepReport,
    DelegationGraph,
    GoalInferencer,
    InterceptorAction,
    SubgoalInterceptor,
)

__all__ = [
    "GovernanceState",
    "GovernanceStateMachine",
    "StateTransition",
    "StateMachineSnapshot",
    "AuditLogger",
    "AuditEntry",
    "AuditBus",
    "CircuitBreaker",
    "BreakerState",
    "BreakerTrip",
    "BudgetBreaker",
    "BudgetBreakerState",
    "BudgetBreakerTrip",
    # P1-A2 治理提案底线语义预检
    "GovernanceBaselineGate",
    "BaselineDecision",
    "BaselineVerdict",
    "BASELINE_PATTERNS",
    "SOFT_PATTERNS",
    "OscillationFixLoop",
    "OscillationStage",
    "OscillationEvent",
    "PERCVEventType",
    "PERCVGovernanceHook",
    "handle_percv_event",
    "GovernanceBridge",
    "GovernanceQuery",
    "RecursiveEvent",
    "RecursiveEventType",
    "ThreatGovernanceBridge",
    "ThreatGovernanceMapping",
    # Verifier Registry
    "VerifierRegistry",
    "VerifierEntry",
    "VerifierStatus",
    # Verifier Consensus
    "VerifierConsensus",
    "ConsensusStrategy",
    "ConsensusResult",
    # Meta-Cognitive Audit
    "MetaCognitiveAuditor",
    # Subgoal Interceptor (G2)
    "SubgoalInterceptor",
    "InterceptorAction",
    "CoTMonitor",
    "CoTReport",
    "GoalInferencer",
    "ControlRiskReport",
    "DelegationGraph",
    "CreepReport",
    # Social Impact Assessment
    "SocialImpactAssessor",
    "SocialImpactReport",
    "ImpactLevel",
    "DeploymentVerdict",
    # Economic Governance
    "SafetyInvestmentAuditor",
    "AgentInsurancePricing",
    "VulnerabilityBountyBoard",
    "InvestmentCategory",
    "RiskTier",
    "BountyStatus",
    # Cross-Instance Governance
    "CrossInstanceGovernor",
    "InstanceStatus",
    "SyncResult",
    "WeightPoisonDetector",
    # Core Pipeline
    "GovernancePipeline",
    "GovernanceRequest",
    "GovernanceResult",
    "Verdict",
    # @governed decorator
    "governed",
    "GovernanceDeniedError",
    "set_default_pipeline",
    "get_default_pipeline",
    # Batteries-included assembly
    "GovernedPipeline",
    # Geopolitical Risk Assessment
    "RiskLevel",
    "Jurisdiction",
    "DataFlowRisk",
    "RiskAssessment",
    "SovereignAIValidationResult",
    "JURISDICTION_REGISTRY",
    "JurisdictionMapper",
    "GeoPoliticalRiskAssessor",
    "SovereignAIValidator",
]

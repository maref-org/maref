"""MAREF Governance — state machine + audit + circuit breaker + oscillation fix.

v0.36.0+: Unified governance pipeline (@governed decorator, GovernancePipeline,
GovernedPipeline) is available for auto-injection governance.
"""

from maref.governance.audit import AuditEntry, AuditLogger
from maref.governance.audit_bus import AuditBus
from maref.governance.budget_breaker import BudgetBreaker, BudgetBreakerState, BudgetBreakerTrip
from maref.governance.circuit_breaker import BreakerState, BreakerTrip, CircuitBreaker

# v0.36.0+: Unified governance pipeline
from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    GovernanceResult,
    Verdict,
)
from maref.governance.credential_broker import (
    CredentialBroker,
    CredentialError,
    DictKeyProvider,
    KeyringProvider,
    build_broker_from_env,
    get_default_broker,
    is_placeholder,
    placeholder_for,
    resolve_credential,
    set_default_broker,
)
from maref.governance.cross_instance import (
    CrossInstanceGovernor,
    InstanceStatus,
    SyncResult,
    WeightPoisonDetector,
)
from maref.governance.decorators import (
    GovernanceAlternativeError,
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

# P1-A2 治理提案底线语义预检 (PoC 盲点 C)
from maref.governance.governance_baseline_gate import (
    BASELINE_PATTERNS,
    SOFT_PATTERNS,
    BaselineDecision,
    BaselineVerdict,
    GovernanceBaselineGate,
)
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.math_assurance import (
    BranchingRatioEstimator,
    ConformalCalibrator,
    ConformalInterval,
    LyapunovCertificate,
)
from maref.governance.oscillation import OscillationEvent, OscillationFixLoop, OscillationStage
from maref.governance.percv_hooks import (
    PERCVEventType,
    PERCVGovernanceHook,
    handle_percv_event,
)
from maref.governance.predictive_breaker import PredictiveBreaker, PreemptionDecision
from maref.governance.provenance import (
    Endorsement,
    FlowDecision,
    InformationFlowGate,
    ProvenanceLabel,
    TaintRecord,
    TaintTracker,
    is_clean_label,
    join_all,
    join_labels,
)
from maref.governance.safety_metrics import (
    SafetyMetricsRecorder,
    SafetyOutcome,
    SanctionedAlternative,
    default_alternatives_for,
    summarize,
)
from maref.governance.social_impact import (
    DeploymentVerdict,
    ImpactLevel,
    SocialImpactAssessor,
    SocialImpactReport,
)
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.temporal_monitor import (
    TemporalMonitor,
    TemporalPolicy,
    TemporalPolicyError,
    Violation,
)
from maref.governance.threat_bridge import ThreatGovernanceBridge, ThreatGovernanceMapping
from maref.governance.trust_boundary import (
    BoundaryDecision,
    BoundaryViolationError,
    TrustBoundaryManager,
)
from maref.governance.trust_bridge import (
    GovernanceBridge,
    GovernanceQuery,
    RecursiveEvent,
    RecursiveEventType,
)
from maref.governance.trust_domain import (
    TrustDomainError,
    TrustDomainMode,
    TrustDomainReport,
    assess,
    enforce,
    resolve_mode,
)
from maref.governance.types import GovernanceState, StateMachineSnapshot, StateTransition
from maref.governance.verifiable_governance_credential import (
    GOVERNANCE_SCOPES,
    GovernanceCredentialStore,
    VerifiableGovernanceCredential,
)
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
    "PredictiveBreaker",
    "PreemptionDecision",
    # Task-level safety metrics + sanctioned alternatives (P0-1)
    "SafetyMetricsRecorder",
    "SafetyOutcome",
    "SanctionedAlternative",
    "summarize",
    "default_alternatives_for",
    # Temporal runtime monitor (P1-4)
    "TemporalMonitor",
    "TemporalPolicy",
    "TemporalPolicyError",
    "Violation",
    # Provenance + information-flow control (P1-5)
    "ProvenanceLabel",
    "TaintRecord",
    "TaintTracker",
    "Endorsement",
    "InformationFlowGate",
    "FlowDecision",
    "is_clean_label",
    "join_labels",
    "join_all",
    # Credential broker (P1-7)
    "CredentialBroker",
    "CredentialError",
    "DictKeyProvider",
    "KeyringProvider",
    "build_broker_from_env",
    "get_default_broker",
    "set_default_broker",
    "resolve_credential",
    "is_placeholder",
    "placeholder_for",
    # Math assurance (P2-12)
    "ConformalCalibrator",
    "ConformalInterval",
    "LyapunovCertificate",
    "BranchingRatioEstimator",
    # Trust-domain enforcement (NVIDIA matrix)
    "TrustDomainMode",
    "TrustDomainReport",
    "TrustDomainError",
    "resolve_mode",
    "assess",
    "enforce",
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
    # Trust Boundary (action-level, E1006)
    "TrustBoundaryManager",
    "BoundaryDecision",
    "BoundaryViolationError",
    # Verifiable Governance Credential
    "VerifiableGovernanceCredential",
    "GovernanceCredentialStore",
    "GOVERNANCE_SCOPES",
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
    "GovernanceAlternativeError",
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

# Phase 2 失败事件总线与归因
# （failure_attribution 视觉/读屏归因属留私模块，不入开源仓——双仓计划 §3 留私清单）
from maref.governance.failure_classifier import (
    DEFAULT_ROUTING_TABLE,
    AttributionResult,
    FailureClass,
    FailureClassifier,
    HealingStrategy,
    route_strategy,
)
from maref.governance.failure_event_bus import load_events, mark, record, replay, stats
from maref.governance.retry_policy import RetryDecision, RetryPolicy

__all__ += [
    # Phase 2 失败事件总线与分类/重试
    "record",
    "mark",
    "replay",
    "stats",
    "load_events",
    "FailureClass",
    "HealingStrategy",
    "AttributionResult",
    "FailureClassifier",
    "route_strategy",
    "DEFAULT_ROUTING_TABLE",
    "RetryPolicy",
    "RetryDecision",
]

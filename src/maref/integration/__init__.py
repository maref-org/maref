"""
MAREF Integration — bridges to Athena v0.2.0 subsystems.

M6: Provides clean interfaces for plugging MAREF into:
- DeerFlow DAG workflow engine
- Symphony protocol messaging
- HITL (Human-in-the-Loop) approval pipeline
- Feature Flag (GrowthBook-compatible) canary rollout
- Memory system (autoDream + Karpathy Wiki)
- LLM Gateway routing decisions
"""

from maref.integration.a2a_bridge import A2ABridge, CommunicationBlockedError
from maref.integration.a2a_types import (
    A2ASkillDefinition,
    A2ATaskContext,
    A2ATaskState,
    DelegatedTask,
    map_a2a_to_maref,
    map_maref_to_a2a,
    validate_agent_card_json,
)
from maref.integration.deerflow_bridge import DeerFlowBridge, DeerFlowDAG, DeerFlowNode
from maref.integration.flag_bridge import FeatureFlag, FlagBridge, PolicySnapshot, RolloutStage
from maref.integration.gateway import (
    GatewayRoute,
    GatewayRouter,
    RoutingDecision,
)
from maref.integration.mcp_governance import (
    AllowKnownSafeMCPTools,
    AllowMCPProtocolSignals,
    BlockDangerousArgs,
    BlockDangerousMCPTools,
    MCPCircuitBreakerMonitor,
    MCPDecisionVerdict,
    MCPGovernance,
    MCPGovernanceResult,
    MCPMappedPolicyEngine,
    MCPPolicyContext,
    MCPPolicyEngine,
    MCPPolicyMapping,
    MCPPolicyRule,
    MCPToolCallStats,
    TrustLevelBasedGate,
    WriteToolRequiresHITL,
    sign_audit_entry,
    verify_audit_signature,
)

# PERCV integration (optional)
try:
    from maref.integration.percv import (
        CyclePhase,
        OrchestratorCycle,
        OrchestratorCycleResult,
        PERCVConfig,
        PERCVGatewayAdapter,
        PERCVPipelineAdapter,
        PERCVResearchOrchestrator,
    )
    from maref.integration.percv import (
        RatchetBridge as PERCVRatchetBridge,
    )
    from maref.integration.percv import (
        VerificationBridge as PERCVVerificationBridge,
    )
    __PERCV_AVAILABLE__ = True
except ImportError:
    __PERCV_AVAILABLE__ = False
    # Create placeholder classes
    class PERCVConfig:
        """Placeholder when PERCV is not available."""
        pass

    class PERCVGatewayAdapter:
        """Placeholder when PERCV is not available."""
        pass

    class PERCVPipelineAdapter:
        """Placeholder when PERCV is not available."""
        pass

    class PERCVRatchetBridge:
        """Placeholder when PERCV is not available."""
        pass

    class PERCVVerificationBridge:
        """Placeholder when PERCV is not available."""
        pass

    class PERCVResearchOrchestrator:
        """Placeholder when PERCV is not available."""
        pass

    class OrchestratorCycle:
        """Placeholder when PERCV is not available."""
        pass

    class OrchestratorCycleResult:
        """Placeholder when PERCV is not available."""
        pass

    class CyclePhase:
        """Placeholder when PERCV is not available."""
        pass

# Test Platform integration (MAS-TS-001) — optional
try:
    from maref.integration.test_platform import (
        AgentCardAdapter,
        EvaluationReport,
        FastScreenTrigger,
        FullRunTrigger,
        MASAgentCard,
        MASEvalObserver,
        PermissionSet,
        Phase,
        ScoreToPhaseMapper,
        TriggerAction,
        UnifiedTrigger,
    )
    __TEST_PLATFORM_AVAILABLE__ = True
except ImportError:
    __TEST_PLATFORM_AVAILABLE__ = False
    class EvaluationReport:
        """Placeholder when Test Platform is not available."""
        pass
    class MASEvalObserver:
        """Placeholder when Test Platform is not available."""
        pass
    class AgentCardAdapter:
        """Placeholder when Test Platform is not available."""
        pass
    class MASAgentCard:
        """Placeholder when Test Platform is not available."""
        pass
    class ScoreToPhaseMapper:
        """Placeholder when Test Platform is not available."""
        pass
    class PermissionSet:
        """Placeholder when Test Platform is not available."""
        pass
    class FastScreenTrigger:
        """Placeholder when Test Platform is not available."""
        pass
    class FullRunTrigger:
        """Placeholder when Test Platform is not available."""
        pass
    class UnifiedTrigger:
        """Placeholder when Test Platform is not available."""
        pass
    class Phase:
        """Placeholder when Test Platform is not available."""
        pass
    class TriggerAction:
        """Placeholder when Test Platform is not available."""
        pass

from maref.integration.hitl import HITLEvent, HITLRouter, HITLStatus, HITLTier
from maref.integration.memory_bridge import (
    KnowledgeInsight,
    MemoryBridge,
    MemoryEntry,
    MemoryPriority,
    MemoryStage,
)
from maref.integration.symphony import SymphonyAdapter, SymphonyMessage, SymphonyMessageType

__all__ = [
    "A2ABridge",
    "A2ASkillDefinition",
    "A2ATaskContext",
    "A2ATaskState",
    "CommunicationBlockedError",
    "DelegatedTask",
    "map_a2a_to_maref",
    "map_maref_to_a2a",
    "validate_agent_card_json",
    "DeerFlowBridge",
    "DeerFlowDAG",
    "DeerFlowNode",
    "SymphonyAdapter",
    "SymphonyMessage",
    "SymphonyMessageType",
    "HITLRouter",
    "HITLEvent",
    "HITLStatus",
    "HITLTier",
    "FlagBridge",
    "FeatureFlag",
    "PolicySnapshot",
    "RolloutStage",
    "MemoryBridge",
    "MemoryEntry",
    "MemoryPriority",
    "MemoryStage",
    "KnowledgeInsight",
    "GatewayRouter",
    "GatewayRoute",
    "RoutingDecision",
    # MCP Governance
    "MCPDecisionVerdict",
    "MCPGovernance",
    "MCPGovernanceResult",
    "MCPPolicyContext",
    "MCPPolicyEngine",
    "MCPPolicyRule",
    "MCPCircuitBreakerMonitor",
    "MCPToolCallStats",
    "MCPPolicyMapping",
    "MCPMappedPolicyEngine",
    "AllowMCPProtocolSignals",
    "AllowKnownSafeMCPTools",
    "BlockDangerousMCPTools",
    "BlockDangerousArgs",
    "WriteToolRequiresHITL",
    "TrustLevelBasedGate",
    "sign_audit_entry",
    "verify_audit_signature",
    # PERCV integration
    "PERCVConfig",
    "PERCVGatewayAdapter",
    "PERCVPipelineAdapter",
    "PERCVRatchetBridge",
    "PERCVVerificationBridge",
    "PERCVResearchOrchestrator",
    "OrchestratorCycle",
    "OrchestratorCycleResult",
    "CyclePhase",
    # Test Platform integration
    "EvaluationReport",
    "MASEvalObserver",
    "AgentCardAdapter",
    "MASAgentCard",
    "ScoreToPhaseMapper",
    "PermissionSet",
    "FastScreenTrigger",
    "FullRunTrigger",
    "UnifiedTrigger",
    "Phase",
    "TriggerAction",
]

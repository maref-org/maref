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
from maref.integration.a2a_client import A2AClient
from maref.integration.a2a_discovery import A2ADiscovery
from maref.integration.a2a_secure_transport import A2ASecureTransport, CertificateManager
from maref.integration.a2a_server import create_a2a_router
from maref.integration.a2a_types import (
    A2A_PROTOCOL_VERSION,
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
from maref.integration.trajectory import (
    TaskTrajectory,
    TrajectoryCollector,
    TrajectoryEvent,
    TrajectoryEventType,
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
    class PERCVConfig:  # type: ignore[no-redef]
        """Placeholder when PERCV is not available."""

        pass

    class PERCVGatewayAdapter:  # type: ignore[no-redef]
        """Placeholder when PERCV is not available."""

        pass

    class PERCVPipelineAdapter:  # type: ignore[no-redef]
        """Placeholder when PERCV is not available."""

        pass

    class PERCVRatchetBridge:  # type: ignore[no-redef]
        """Placeholder when PERCV is not available."""

        pass

    class PERCVVerificationBridge:  # type: ignore[no-redef]
        """Placeholder when PERCV is not available."""

        pass

    class PERCVResearchOrchestrator:  # type: ignore[no-redef]
        """Placeholder when PERCV is not available."""

        pass

    class OrchestratorCycle:  # type: ignore[no-redef]
        """Placeholder when PERCV is not available."""

        pass

    class OrchestratorCycleResult:  # type: ignore[no-redef]
        """Placeholder when PERCV is not available."""

        pass

    class CyclePhase:  # type: ignore[no-redef]
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

    class EvaluationReport:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass

    class MASEvalObserver:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass

    class AgentCardAdapter:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass

    class MASAgentCard:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass

    class ScoreToPhaseMapper:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass

    class PermissionSet:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass

    class FastScreenTrigger:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass

    class FullRunTrigger:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass

    class UnifiedTrigger:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass

    class Phase:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass

    class TriggerAction:  # type: ignore[no-redef]
        """Placeholder when Test Platform is not available."""

        pass


from maref.integration.hitl import HITLEvent, HITLRouter, HITLStatus, HITLTier
from maref.integration.maref_loop_adapter import MAREFLoop
from maref.integration.memory_bridge import (
    KnowledgeInsight,
    MemoryBridge,
    MemoryEntry,
    MemoryPriority,
    MemoryStage,
)
from maref.integration.remote_bridge import (
    BridgeState,
    RemoteBridge,
    RemoteCommand,
    RemoteCommandResult,
)
from maref.integration.symphony import SymphonyAdapter, SymphonyMessage, SymphonyMessageType

__all__ = [
    "A2A_PROTOCOL_VERSION",
    "A2ABridge",
    "A2AClient",
    "A2ADiscovery",
    "A2ASecureTransport",
    "A2ASkillDefinition",
    "A2ATaskContext",
    "A2ATaskState",
    "CertificateManager",
    "CommunicationBlockedError",
    "create_a2a_router",
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
    # Remote Bridge
    "BridgeState",
    "RemoteBridge",
    "RemoteCommand",
    "RemoteCommandResult",
    # MAREFLoop adapter
    "MAREFLoop",
    # Trajectory collection (MAS-TS-001 D2/D3)
    "TaskTrajectory",
    "TrajectoryCollector",
    "TrajectoryEvent",
    "TrajectoryEventType",
]

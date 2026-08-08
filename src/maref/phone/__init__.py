"""手机终端智能模块 — PhoneAgent。"""

from maref.phone.agent import PhoneAgent, PhoneAgentConfig, PhoneAgentState
from maref.phone.capability import CapabilityRegistry, PhoneCapability
from maref.phone.learning import ExecutionRecord, LearningEngine, LearningStats, PatternMatch
from maref.phone.mobile_bridge import (
    BridgeConfig,
    BridgeConnectionState,
    BridgeRouteDecision,
    BridgeTaskResult,
    MobileBridge,
)
from maref.phone.safety import (
    PhoneSafetyGate,
    PhoneThreatAssessment,
    PhoneThreatCategory,
    PhoneThreatSeverity,
)
from maref.phone.telemetry import Telemetry
from maref.phone.vlm_backend import (
    BaseVLMBackend,
    FaraBackend,
    LocalFallbackBackend,
    OllamaLlavaBackend,
    VLMContext,
    VLMDecision,
    create_backend,
)
from maref.phone.vlm_engine import EngineMode, VLMDecisionEngine, VLMEngineConfig
from maref.phone.vlm_prompt import (
    build_decision_prompt,
    build_reflection_prompt,
    build_system_prompt,
    build_verify_prompt,
)

__all__ = [
    "PhoneAgent", "PhoneAgentConfig", "PhoneAgentState",
    "CapabilityRegistry", "PhoneCapability",
    "PhoneSafetyGate", "PhoneThreatAssessment", "PhoneThreatCategory", "PhoneThreatSeverity",
    "ExecutionRecord", "LearningEngine", "LearningStats", "PatternMatch",
    "Telemetry",
    "MobileBridge", "BridgeConfig", "BridgeConnectionState", "BridgeRouteDecision", "BridgeTaskResult",
    "VLMDecision", "VLMContext", "BaseVLMBackend", "LocalFallbackBackend",
    "FaraBackend", "OllamaLlavaBackend", "create_backend",
    "EngineMode", "VLMDecisionEngine", "VLMEngineConfig",
    "build_system_prompt", "build_decision_prompt", "build_reflection_prompt", "build_verify_prompt",
]

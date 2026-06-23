"""MAREF Meta-Cognitive Audit Layer (G1).

Detects agent deception, capability hiding, and behavioral manipulation
through multi-layer analysis: behavior baseline profiling, stealth probes,
and Bayesian intention inference.
"""

from maref.metacognition.auditor import MetaCognitiveAuditor
from maref.metacognition.behavior_baseline import BehaviorBaseline
from maref.metacognition.intention_inference import DeceptionInferenceEngine
from maref.metacognition.models import (
    AgentProfile,
    ConsistencyReport,
    InferenceRecommendation,
    InferenceResult,
    ProbeResult,
    ProbeType,
    SessionRecord,
)
from maref.metacognition.stealth_probe import ProbeAnalyst, StealthProbe

__all__ = [
    "MetaCognitiveAuditor",
    "BehaviorBaseline",
    "StealthProbe",
    "ProbeAnalyst",
    "DeceptionInferenceEngine",
    "AgentProfile",
    "ConsistencyReport",
    "InferenceResult",
    "InferenceRecommendation",
    "ProbeResult",
    "ProbeType",
    "SessionRecord",
]

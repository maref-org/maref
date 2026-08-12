"""MAREF Consensus Layer — causal consistency, NACK protocol, and dynamic degradation.

Exports vector clocks, NACK message building/handling, consistency-level
DSL primitives, and the dynamic consistency degrader.
"""

from __future__ import annotations

from maref.consensus.consistency_dsl import (
    ConsistencyCost,
    ConsistencyLevel,
    CostEstimator,
    DynamicDegrader,
)
from maref.consensus.nack_protocol import (
    NackBuilder,
    NackCode,
    NackHandler,
    NackMessage,
    Recoverability,
    RecoveryDecision,
    RetryPolicy,
)
from maref.consensus.vector_clock import (
    CausalContext,
    CausalRelation,
    VectorClock,
)

__all__ = [
    # Vector clocks
    "VectorClock",
    "CausalRelation",
    "CausalContext",
    # NACK protocol
    "NackCode",
    "Recoverability",
    "NackMessage",
    "NackBuilder",
    "NackHandler",
    "RetryPolicy",
    "RecoveryDecision",
    # Consistency DSL
    "ConsistencyLevel",
    "ConsistencyCost",
    "CostEstimator",
    "DynamicDegrader",
]

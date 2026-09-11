"""GovernedPipeline — batteries-included governance assembly.

One-call setup for all governance components. Sets itself as the default
pipeline for the @governed decorator, and exposes all individual components
for advanced use.

Usage:
    pipeline = GovernedPipeline()
    pipeline.set_as_default()

    @governed(require="file.write")
    def save(path, content): ...
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maref.governance.audit import AuditLogger
from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    GovernanceResult,
)
from maref.governance.decorators import set_default_pipeline
from maref.recursive.permission_matrix import PermissionMatrix

if TYPE_CHECKING:
    from maref.gaas.cb_pool import CircuitBreakerPool
    from maref.integration.hitl import HITLRouter

logger = logging.getLogger(__name__)


class GovernedPipeline:
    """Batteries-included governance assembly.

    Initializes all governance components with sensible defaults:
      - AuditLogger (HMAC-signed, from MAREF_HMAC_SECRET_KEY env var)
      - HITLRouter (tier-based human-in-the-loop)
      - PermissionMatrix (I Ching role-based access)
      - CircuitBreakerPool (per-tenant/per-agent/per-action CB)
      - GovernancePipeline (unified 8-step pipeline)
      - GovernanceWatchdog (self-health monitoring)

    Call set_as_default() to make this the global default for @governed.
    """

    def __init__(
        self,
        audit_path: str | Path | None = None,
        hmac_key: str | None = None,
        cb_pool: CircuitBreakerPool | None = None,
        hitl: HITLRouter | None = None,
        permission: PermissionMatrix | None = None,
        boundary: Any | None = None,
        task_preflight: Any | None = None,
        behavior_probe: Any | None = None,
        consensus: Any | None = None,
    ) -> None:
        # 1. Audit logger with HMAC
        hmac_key = hmac_key or os.environ.get("MAREF_HMAC_SECRET_KEY")
        resolved_key: bytes | None = (
            (hmac_key.encode("utf-8") if isinstance(hmac_key, str) else hmac_key)
            if hmac_key
            else None
        )
        self.audit = AuditLogger(
            log_path=audit_path or Path("governance_audit.jsonl"),
            hmac_key=resolved_key,
        )

        # 2. HITL router
        from maref.integration.hitl import HITLRouter as _HITLRouter

        self.hitl = hitl or _HITLRouter()

        # 3. Permission matrix (I Ching roles)
        self.permission = permission or PermissionMatrix()

        # 4. Circuit breaker pool (per-tenant/per-agent/per-action)
        self.cb_pool = (
            cb_pool
            or (
                lambda: __import__(
                    "maref.gaas.cb_pool", fromlist=["CircuitBreakerPool"]
                ).CircuitBreakerPool()
            )()
        )

        # 5. v0.47/v0.48 governance gates (W1: unified closed-loop assembly)
        from maref.governance.audit_bus import AuditBus
        from maref.governance.task_preflight import TaskPreflight
        from maref.governance.trust_boundary import TrustBoundaryManager

        # Shared audit bus: the behavior probe subscribes to the same stream
        # the pipeline audits into, closing the loop (W2).
        self.audit_bus = AuditBus(hmac_key=resolved_key)
        self.boundary = boundary if boundary is not None else TrustBoundaryManager()
        self.task_preflight = task_preflight if task_preflight is not None else TaskPreflight()
        if behavior_probe is not None:
            self.behavior_probe = behavior_probe
        else:
            from maref.agent.behavior_analyzer import (
                assemble_runtime_behavior_probe,
            )

            self.behavior_probe = assemble_runtime_behavior_probe(audit_bus=self.audit_bus)
        if consensus is not None:
            self.consensus = consensus
        else:
            from maref.governance.federated_consensus import FederatedConsensus

            self.consensus = FederatedConsensus()

        # 6. Unified governance pipeline with all components
        # v0.52.1 G2-C7: 链级意图推理生产接线。
        from maref.governance.intent.factory import build_chain_intent_gate

        intent_tracker, intent_gate = build_chain_intent_gate()
        self.pipeline = GovernancePipeline(
            hitl=self.hitl,
            permission=self.permission,
            audit_callback=self._audit_decision,
            boundary=self.boundary,
            intent_tracker=intent_tracker,
            intent_gate=intent_gate,
        )

        logger.info(
            "GovernedPipeline initialized: audit=%s, hitl=%s, permission=%s, cb=%s, "
            "boundary=%s, preflight=%s, probe=%s, consensus=%s",
            type(self.audit).__name__,
            type(self.hitl).__name__,
            type(self.permission).__name__,
            type(self.cb_pool).__name__,
            type(self.boundary).__name__,
            type(self.task_preflight).__name__,
            type(self.behavior_probe).__name__,
            type(self.consensus).__name__,
        )

    def set_as_default(self) -> None:
        """Set this pipeline as the global default for @governed decorator."""
        set_default_pipeline(self.pipeline)
        logger.info("GovernedPipeline set as global default")

    def govern(self, request: GovernanceRequest) -> GovernanceResult:
        """Execute governance check through the unified pipeline."""
        return self.pipeline.govern(request)

    def _audit_decision(self, request: GovernanceRequest, result: GovernanceResult) -> None:
        """Persist governance decisions to the append-only audit log AND the
        shared audit bus (W2: closes the loop to the behavior probe)."""
        self.audit.log(
            event_type="governance_decision",
            actor=request.agent_id,
            action=request.action,
            details=f"{result.verdict.value}: {result.reason}",
            metadata={
                "tenant_id": request.tenant_id,
                "matched_rule": result.matched_rule,
                "hitl_tier": result.hitl_tier.name if result.hitl_tier else "",
            },
        )
        # Publish to the shared audit bus so the behavior probe (subscribed
        # to the "audit" topic) receives the governance decision event.
        self.audit_bus.log(
            event_type="audit",
            actor=request.agent_id,
            action=request.action,
            details=f"{result.verdict.value}: {result.reason}",
            metadata={
                "governance_event": "governance_decision",
                "tenant_id": request.tenant_id,
                "matched_rule": result.matched_rule,
                "verdict": result.verdict.value,
            },
        )

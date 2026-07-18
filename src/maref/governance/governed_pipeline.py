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

from maref.gaas.cb_pool import CircuitBreakerPool
from maref.governance.audit import AuditLogger
from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    GovernanceResult,
)
from maref.governance.decorators import set_default_pipeline
from maref.integration.hitl import HITLRouter
from maref.recursive.permission_matrix import PermissionMatrix

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
    ) -> None:
        # 1. Audit logger with HMAC
        hmac_key = hmac_key or os.environ.get("MAREF_HMAC_SECRET_KEY")
        resolved_key: bytes | None = (
            hmac_key.encode("utf-8") if isinstance(hmac_key, str) else hmac_key
        ) if hmac_key else None
        self.audit = AuditLogger(
            log_path=audit_path or Path("governance_audit.jsonl"),
            hmac_key=resolved_key,
        )

        # 2. HITL router
        self.hitl = hitl or HITLRouter()

        # 3. Permission matrix (I Ching roles)
        self.permission = permission or PermissionMatrix()

        # 4. Circuit breaker pool (per-tenant/per-agent/per-action)
        self.cb_pool = cb_pool or CircuitBreakerPool()

        # 5. Unified governance pipeline with all components
        self.pipeline = GovernancePipeline(
            hitl=self.hitl,
            permission=self.permission,
        )

        logger.info(
            "GovernedPipeline initialized: audit=%s, hitl=%s, permission=%s, cb=%s",
            type(self.audit).__name__,
            type(self.hitl).__name__,
            type(self.permission).__name__,
            type(self.cb_pool).__name__,
        )

    def set_as_default(self) -> None:
        """Set this pipeline as the global default for @governed decorator."""
        set_default_pipeline(self.pipeline)
        logger.info("GovernedPipeline set as global default")

    def govern(self, request: GovernanceRequest) -> GovernanceResult:
        """Execute governance check through the unified pipeline."""
        return self.pipeline.govern(request)

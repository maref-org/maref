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

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maref.governance.audit import AuditLogger
from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    GovernanceResult,
    Verdict,
)
from maref.governance.decorators import set_default_pipeline
from maref.governance.org_policy import OrganizationPolicy
from maref.recursive.permission_matrix import PermissionMatrix

if TYPE_CHECKING:
    from maref.gaas.cb_pool import CircuitBreakerPool
    from maref.integration.hitl import HITLRouter

logger = logging.getLogger(__name__)


def _default_pipeline_audit_path() -> Path:
    """解析 GovernedPipeline 审计落盘路径（P1-A）。

    优先级:
    1. MAREF_PIPELINE_AUDIT_LOG — 专用绝对路径（sidecar/管线，避免与 state_machine 链混写）
    2. MAREF_AUDIT_PATH 指向文件 → 该文件
    3. MAREF_AUDIT_PATH 为目录 → <dir>/pipeline_governance_audit.jsonl（与 state_machine 的 governance_audit.jsonl 分离）
    4. cwd/governance_audit.jsonl（历史行为，解析为绝对路径）
    """
    dedicated = os.environ.get("MAREF_PIPELINE_AUDIT_LOG")
    if dedicated:
        p = Path(dedicated)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return p
    env = os.environ.get("MAREF_AUDIT_PATH")
    if env:
        p = Path(env)
        if p.suffix:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            return p
        candidate = p / "pipeline_governance_audit.jsonl"
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return candidate
    return Path("governance_audit.jsonl").resolve()


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
        org_policy: OrganizationPolicy | None = None,
        otel_exporter: Any | None = None,
        social_content_gate: Any | None = None,
    ) -> None:
        # 1. Audit logger with HMAC
        hmac_key = hmac_key or os.environ.get("MAREF_HMAC_SECRET_KEY")
        resolved_key: bytes | None = (
            (hmac_key.encode("utf-8") if isinstance(hmac_key, str) else hmac_key)
            if hmac_key
            else None
        )
        self.audit = AuditLogger(
            log_path=audit_path or _default_pipeline_audit_path(),
            hmac_key=resolved_key,
        )
        self.policy_version = os.environ.get("MAREF_POLICY_VERSION", "core-pipeline-v1")
        self.policy_epoch = os.environ.get("MAREF_POLICY_EPOCH", "")
        if org_policy is None:
            org_policy_path = os.environ.get("MAREF_ORG_POLICY_PATH", "")
            if org_policy_path:
                try:
                    org_policy = OrganizationPolicy.from_path(org_policy_path)
                except Exception as exc:
                    logger.warning("Failed to load organization policy %s: %s", org_policy_path, exc)
        self.org_policy = org_policy
        self.otel_exporter = otel_exporter
        if social_content_gate is None:
            from maref.governance.social_content_gate import SocialContentGate

            social_content_gate = SocialContentGate()
        self.social_content_gate = social_content_gate
        self.evidence_ttl_s = float(os.environ.get("MAREF_EVIDENCE_TTL_SECONDS", "300"))
        self.clock = time.time
        self._evidence_lock = threading.Lock()
        self._evidence_cache: dict[str, float] = {}
        self._evidence_cache_loaded = False
        audit_file = getattr(self.audit, "_path", None)
        consumed_env = os.environ.get("MAREF_EVIDENCE_CONSUMED_PATH")
        self._evidence_consumed_path: Path | None = (
            Path(consumed_env)
            if consumed_env
            else (
                Path(str(audit_file)).with_name(Path(str(audit_file)).name + ".consumed.jsonl")
                if audit_file is not None
                else None
            )
        )
        self._evidence_consumed: dict[str, float] = {}
        self._load_consumed_evidence()

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
            policy_version=self.policy_version,
            policy_epoch=self.policy_epoch,
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
        """Execute organization policy and the unified governance pipeline."""
        result = self._govern_org_policy(request)
        if result is None:
            result = self.pipeline.govern(request)
        if self.otel_exporter is not None:
            self.otel_exporter.record_decision(request, result)
        return result

    def review_social_content(self, content: Any) -> Any:
        """Review platform content and emit an auditable governance decision."""
        import hashlib

        decision = self.social_content_gate.review(content)
        verdict = {
            "allow": Verdict.ALLOW,
            "review": Verdict.ASK_USER,
            "block": Verdict.DENY,
        }[decision.verdict]
        tenant_id = str(content.metadata.get("tenant_id", ""))
        request = GovernanceRequest(
            action=f"content.publish.{content.platform}",
            agent_id=str(content.metadata.get("agent_id", "content-pipeline")),
            tenant_id=tenant_id,
            role=str(content.metadata.get("role", "坎")),
            parameters={
                "platform": content.platform,
                "text_hash": hashlib.sha256(content.text.encode("utf-8")).hexdigest(),
            },
        )
        reasons = list(decision.reasons)
        matched_rule = f"social_content_gate:{decision.verdict}"
        if self.org_policy is not None:
            org_id = str(content.metadata.get("org_id", "") or tenant_id)
            if org_id:
                org_decision = self.org_policy.evaluate(org_id, request.role, request.action)
                if org_decision.decision == "deny":
                    verdict = Verdict.DENY
                    reasons.append(f"organization policy: {org_decision.reason}")
                    matched_rule = "org_policy:deny"
                elif org_decision.decision == "require_approval":
                    if verdict != Verdict.DENY:
                        verdict = Verdict.ASK_USER
                    reasons.append(f"organization policy: {org_decision.reason}")
                    matched_rule = "org_policy:require_approval"
        result = GovernanceResult(
            verdict=verdict,
            reason="; ".join(reasons) or "content gate passed",
            matched_rule=matched_rule,
            risk_score=decision.risk_score,
            policy_version=self.policy_version,
            policy_epoch=self.policy_epoch,
        )
        if verdict == Verdict.ASK_USER:
            from maref.integration.hitl import HITLTier as _HITLTier

            event = self.hitl.request(
                tenant_id=request.tenant_id or "default",
                agent_id=request.agent_id,
                action=request.action,
                description=result.reason,
                parameters=request.parameters,
                tier=_HITLTier.P1_ESCALATE,
            )
            result.hitl_tier = _HITLTier.P1_ESCALATE
            result.hitl_event_id = event.event_id
        self._audit_decision(request, result)
        if self.otel_exporter is not None:
            self.otel_exporter.record_decision(request, result)
        if verdict == Verdict.DENY and decision.verdict != "block":
            decision.required_actions.append("obtain_org_authorization")
        elif verdict == Verdict.ASK_USER and decision.verdict == "allow":
            decision.required_actions.append("human_review_required")
        decision.verdict = {
            Verdict.ALLOW: "allow",
            Verdict.ASK_USER: "review",
            Verdict.DENY: "block",
        }[verdict]
        decision.allowed = verdict == Verdict.ALLOW
        decision.reasons = reasons
        decision.evidence_id = result.evidence_id
        decision.hitl_event_id = result.hitl_event_id
        return decision

    def export_regulatory_evidence(self) -> Any:
        """Build an EU AI Act evidence bundle from this pipeline's audit log."""
        from maref.governance.regulatory_evidence import RegulatoryEvidenceMapper

        return RegulatoryEvidenceMapper().map_entries(self.audit.read_all())

    def _govern_org_policy(self, request: GovernanceRequest) -> GovernanceResult | None:
        if self.org_policy is None:
            return None
        org_id = str(request.parameters.get("org_id") or request.tenant_id or "")
        if not org_id:
            return None
        decision = self.org_policy.evaluate(org_id, request.role, request.action)
        if decision.decision == "unmanaged" or decision.decision == "allow":
            return None

        if decision.decision == "require_approval":
            from maref.integration.hitl import HITLTier as _HITLTier

            event = self.hitl.request(
                tenant_id=request.tenant_id or org_id,
                agent_id=request.agent_id,
                action=request.action,
                description=decision.reason,
                parameters=request.parameters,
                tier=_HITLTier.P1_ESCALATE,
            )
            result = GovernanceResult(
                verdict=Verdict.ASK_USER,
                reason=decision.reason,
                hitl_tier=_HITLTier.P1_ESCALATE,
                hitl_event_id=event.event_id,
                matched_rule=decision.matched_rule,
                policy_version=decision.policy_version or self.policy_version,
                policy_epoch=decision.policy_epoch or self.policy_epoch,
            )
        else:
            result = GovernanceResult(
                verdict=Verdict.DENY,
                reason=decision.reason,
                matched_rule=decision.matched_rule,
                policy_version=decision.policy_version or self.policy_version,
                policy_epoch=decision.policy_epoch or self.policy_epoch,
            )
        self._audit_decision(request, result)
        return result

    def _ensure_evidence_cache(self) -> None:
        if self._evidence_cache_loaded:
            return
        for entry in self.audit.read_all(max_entries=10000):
            if entry.event_type == "governance_decision":
                self._evidence_cache.setdefault(entry.id, entry.timestamp)
        self._evidence_cache_loaded = True

    def _load_consumed_evidence(self) -> None:
        """Load consumed evidence ids so one-time claims survive restarts."""
        path = self._evidence_consumed_path
        if path is None or not path.exists():
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("Failed to read consumed-evidence ledger %s: %s", path, exc)
            return
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                evidence_id = str(data["evidence_id"])
                consumed_at = float(data.get("consumed_at", 0.0))
            except (ValueError, KeyError, TypeError):
                logger.warning("Ignoring malformed consumed-evidence record in %s", path)
                continue
            self._evidence_consumed[evidence_id] = consumed_at

    def _persist_consumed_evidence(self, evidence_id: str, consumed_at: float) -> None:
        path = self._evidence_consumed_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"evidence_id": evidence_id, "consumed_at": consumed_at},
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())

    def verify_evidence(
        self,
        evidence_id: str,
        *,
        consume: bool = True,
        now: float | None = None,
    ) -> bool:
        """Verify and optionally consume a one-time execution evidence id.

        Evidence ids are audit-entry ids emitted on governance decisions.
        Verification fails when the id is unknown, expired, or already
        consumed.  Consuming is the default so a signed decision cannot be
        replayed by another action.
        """
        valid = self._verify_evidence(evidence_id, consume=consume, now=now)
        if self.otel_exporter is not None:
            reason = "" if valid else "unknown, expired, or already consumed"
            self.otel_exporter.record_evidence_check(evidence_id, valid, reason=reason)
        return valid

    def _verify_evidence(
        self,
        evidence_id: str,
        *,
        consume: bool = True,
        now: float | None = None,
    ) -> bool:
        if not evidence_id:
            return False
        current = self.clock() if now is None else now
        with self._evidence_lock:
            self._ensure_evidence_cache()
            timestamp = self._evidence_cache.get(evidence_id)
            if timestamp is None or evidence_id in self._evidence_consumed:
                return False
            age = current - timestamp
            if age < -5.0 or age > self.evidence_ttl_s:
                return False
            if consume:
                try:
                    self._persist_consumed_evidence(evidence_id, current)
                except OSError as exc:
                    logger.error(
                        "Refusing evidence consumption: cannot persist one-time claim: %s", exc
                    )
                    return False
                del self._evidence_cache[evidence_id]
                self._evidence_consumed[evidence_id] = current
            return True

    def _audit_decision(self, request: GovernanceRequest, result: GovernanceResult) -> None:
        """Persist governance decisions to the append-only audit log AND the
        shared audit bus (W2: closes the loop to the behavior probe)."""
        entry = self.audit.log(
            event_type="governance_decision",
            actor=request.agent_id,
            action=request.action,
            details=f"{result.verdict.value}: {result.reason}",
            metadata={
                "tenant_id": request.tenant_id,
                "matched_rule": result.matched_rule,
                "hitl_tier": result.hitl_tier.name if result.hitl_tier else "",
                "policy_version": result.policy_version or self.policy_version,
                "policy_epoch": result.policy_epoch or self.policy_epoch,
                "risk_score": result.risk_score,
            },
        )
        result.evidence_id = entry.id
        with self._evidence_lock:
            self._evidence_cache[entry.id] = entry.timestamp
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
                "policy_version": result.policy_version or self.policy_version,
                "policy_epoch": result.policy_epoch or self.policy_epoch,
                "evidence_id": result.evidence_id,
            },
        )

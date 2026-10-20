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

from maref.governance.audit import AuditEntry, AuditLogger
from maref.governance.canonical_json import (
    CANONICAL_JSON_VERSION,
    CanonicalJSONError,
    canonical_hash,
)
from maref.governance.commercial_policy import CommercialActionPolicy
from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    GovernanceResult,
    Verdict,
)
from maref.governance.decorators import set_default_pipeline
from maref.governance.interaction_evidence import InteractionRecorder
from maref.governance.model_route import ModelRouteRecorder
from maref.governance.org_policy import OrganizationPolicy
from maref.recursive.permission_matrix import PermissionMatrix

if TYPE_CHECKING:
    from maref.gaas.cb_pool import CircuitBreakerPool
    from maref.integration.hitl import HITLRouter

logger = logging.getLogger(__name__)


def _params_hash(value: Any) -> tuple[str, str]:
    """Return ``(hash, status)``; unsupported values fail closed."""

    try:
        return canonical_hash(value), "ok"
    except (CanonicalJSONError, TypeError, ValueError):
        return "", "unhashable"


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
        commercial_action_policy: CommercialActionPolicy | None = None,
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
        if commercial_action_policy is None:
            policy_path = os.environ.get("MAREF_COMMERCIAL_ACTIONS_PATH", "")
            if policy_path:
                # Explicitly configured policy must load: a broken policy file
                # is a governance failure, not a reason to fall back to allow.
                commercial_action_policy = CommercialActionPolicy.from_path(policy_path)
        self.commercial_action_policy = commercial_action_policy
        self.route_recorder = (
            ModelRouteRecorder(self.audit) if commercial_action_policy is not None else None
        )
        self.interaction_recorder = InteractionRecorder(self.audit)
        self.evidence_ttl_s = float(os.environ.get("MAREF_EVIDENCE_TTL_SECONDS", "300"))
        self.clock = time.time
        self._evidence_lock = threading.Lock()
        self._evidence_cache: dict[str, float] = {}
        self._evidence_entry_cache: dict[str, AuditEntry] = {}
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
        """Execute route, organization and unified governance checks."""
        route_result = self._enforce_route_evidence(request)
        if route_result is not None:
            if self.otel_exporter is not None:
                self.otel_exporter.record_decision(request, route_result)
            return route_result
        result = self._govern_org_policy(request)
        if result is None:
            result = self.pipeline.govern(request)
        if self.otel_exporter is not None:
            self.otel_exporter.record_decision(request, result)
        return result

    def _enforce_route_evidence(self, request: GovernanceRequest) -> GovernanceResult | None:
        """Deny L2/L3 commercial actions without valid route evidence (P0-A)."""
        policy = self.commercial_action_policy
        if policy is None:
            return None
        classification = policy.classify(request.action)
        if classification.level not in policy.route_required_levels:
            return None

        reason = ""
        matched_rule = ""
        _, params_status = _params_hash(request.parameters)
        if params_status != "ok":
            reason = (
                f"商业动作 {request.action} ({classification.level.value}) "
                "参数无法规范化为 JSON，拒绝生成不可复算的证据"
            )
            matched_rule = "commercial_params:unhashable"
        elif not request.model_route_id:
            reason = (
                f"商业动作 {request.action} ({classification.level.value}) "
                "缺少模型路由证据 (model_route_decision)"
            )
            matched_rule = "commercial_route:missing"
        elif not request.model_version:
            reason = (
                f"商业动作 {request.action} ({classification.level.value}) "
                "缺少实际运行的 model_version，无法绑定路由证据"
            )
            matched_rule = "commercial_route:missing_model_version"
        elif self.route_recorder is None or not self.route_recorder.verify(
            request.model_route_id,
            tenant_id=request.tenant_id,
            model_version=request.model_version,
        ):
            reason = (
                f"模型路由证据 {request.model_route_id} 无效，"
                "或与租户/模型版本不匹配"
            )
            matched_rule = "commercial_route:invalid"
        else:
            return None

        result = GovernanceResult(
            verdict=Verdict.DENY,
            reason=reason,
            matched_rule=matched_rule,
            risk_score=classification.risk_score,
            policy_version=self.policy_version,
            policy_epoch=self.policy_epoch,
        )
        self._audit_decision(request, result)
        return result

    def _purpose_id(self, request: GovernanceRequest) -> str:
        """Purpose comes from the policy file, never from request parameters."""
        if self.commercial_action_policy is None:
            return ""
        return self.commercial_action_policy.classify(request.action).purpose_id

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

    def verify_evidence_for(
        self,
        evidence_id: str,
        *,
        action: str,
        params_hash: str,
        tenant_id: str,
        params_hash_version: str = CANONICAL_JSON_VERSION,
        allow_legacy: bool = False,
        org_id: str = "",
        purpose_id: str = "",
        route_decision_id: str = "",
        model_version: str = "",
        detector_set_hash: str = "",
        consume: bool = True,
        now: float | None = None,
    ) -> bool:
        """Verify evidence *and* that it was issued for this exact purpose.

        ``verify_evidence`` only proves an id exists.  This method binds the
        evidence to action, canonical params, tenant, policy purpose, route and
        detector snapshot so an ALLOW for one action cannot vouch for another.

        ``params_hash_version`` must match the recorded hashing scheme.  Entries
        written before canonical JSON v2 require ``allow_legacy=True``; this is
        an explicit migration window, not the default.
        """
        entry = self._resolve_evidence(evidence_id)
        if entry is None or entry.event_type != "governance_decision":
            return False
        metadata = entry.metadata or {}
        if entry.action != action:
            return False
        if str(metadata.get("params_hash_status", "ok")) != "ok":
            return False
        entry_version = str(metadata.get("params_hash_version", "1"))
        if params_hash_version and entry_version != params_hash_version:
            return False
        if entry_version != CANONICAL_JSON_VERSION and not allow_legacy:
            return False
        if str(metadata.get("params_hash", "")) != params_hash:
            return False
        entry_tenant = entry.tenant_id or str(metadata.get("tenant_id", ""))
        if entry_tenant != tenant_id:
            return False

        expected = {
            "org_id": org_id,
            "purpose_id": purpose_id,
            "route_decision_id": route_decision_id,
            "model_version": model_version,
            "detector_set_hash": detector_set_hash,
        }
        for key, value in expected.items():
            if value and str(metadata.get(key, "")) != value:
                return False

        valid = self._verify_evidence(evidence_id, consume=consume, now=now)
        if self.otel_exporter is not None:
            reason = "" if valid else "binding mismatch or evidence already consumed"
            self.otel_exporter.record_evidence_check(evidence_id, valid, reason=reason)
        return valid

    def _resolve_evidence(self, evidence_id: str) -> AuditEntry | None:
        """Resolve an evidence entry, falling back to an on-disk lookup.

        The in-memory cache only holds recent entries; older evidence must
        remain verifiable after a restart instead of silently returning False.
        """
        if not evidence_id:
            return None
        with self._evidence_lock:
            cached = self._evidence_entry_cache.get(evidence_id)
        if cached is not None:
            return cached
        entry = self.audit.find_by_id(evidence_id)
        if entry is None:
            return None
        if not self.audit.verify_entry(entry):
            logger.warning("Rejecting tampered or unsigned evidence: %s", evidence_id)
            return None
        with self._evidence_lock:
            self._evidence_entry_cache[evidence_id] = entry
            self._evidence_cache.setdefault(evidence_id, entry.timestamp)
            if len(self._evidence_entry_cache) > 5000:
                oldest = next(iter(self._evidence_entry_cache))
                self._evidence_entry_cache.pop(oldest, None)
        return entry

    def _verify_evidence(
        self,
        evidence_id: str,
        *,
        consume: bool = True,
        now: float | None = None,
    ) -> bool:
        if not evidence_id:
            return False
        if self._resolve_evidence(evidence_id) is None:
            return False
        current = self.clock() if now is None else now
        with self._evidence_lock:
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
                self._evidence_cache.pop(evidence_id, None)
                self._evidence_consumed[evidence_id] = current
            return True

    def _audit_decision(self, request: GovernanceRequest, result: GovernanceResult) -> None:
        """Persist governance decisions to the append-only audit log AND the
        shared audit bus (W2: closes the loop to the behavior probe)."""
        parameters = request.parameters if isinstance(request.parameters, dict) else {}
        params_hash, params_hash_status = _params_hash(request.parameters)
        entry = self.audit.log(
            event_type="governance_decision",
            actor=request.agent_id,
            action=request.action,
            details=f"{result.verdict.value}: {result.reason}",
            metadata={
                "tenant_id": request.tenant_id,
                "org_id": str(parameters.get("org_id") or ""),
                "matched_rule": result.matched_rule,
                "hitl_tier": result.hitl_tier.name if result.hitl_tier else "",
                "policy_version": result.policy_version or self.policy_version,
                "policy_epoch": result.policy_epoch or self.policy_epoch,
                "risk_score": result.risk_score,
                # P0-C: bind the decision to what it authorised.
                "params_hash": params_hash,
                "params_hash_version": CANONICAL_JSON_VERSION,
                "params_hash_status": params_hash_status,
                "purpose_id": self._purpose_id(request),
                "trace_id": request.trace_id,
                "route_decision_id": request.model_route_id,
                "interaction_id": request.interaction_id,
                "model_version": request.model_version,
                "detector_set_hash": request.detector_set_hash,
                "commercial_policy_version": (
                    self.commercial_action_policy.version
                    if self.commercial_action_policy is not None
                    else ""
                ),
                "commercial_policy_hash": (
                    self.commercial_action_policy.document_hash
                    if self.commercial_action_policy is not None
                    else ""
                ),
            },
            parent_action_id=request.interaction_id or request.model_route_id,
            tenant_id=request.tenant_id,
        )
        result.evidence_id = entry.id
        with self._evidence_lock:
            self._evidence_cache[entry.id] = entry.timestamp
            self._evidence_entry_cache[entry.id] = entry
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

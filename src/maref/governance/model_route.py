"""Model route decision evidence (P0-A).

A multi-LLM route is a governance decision, not a telemetry detail.  This
module records *why* a model was selected (policy, eligibility, fallback,
residency) as a first-class, signed evidence event in the audit chain.

External routers (for example ``unified_proxy``) live outside MAREF and can
lie about what they did.  ``RouteIngestAdapter`` therefore only accepts route
records signed by an independent router key and rejects replayed attestations.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.governance.audit import AuditLogger
from maref.governance.canonical_json import canonical_bytes

MODEL_ROUTE_EVENT = "model_route_decision"
MODEL_ROUTE_SCHEMA_VERSION = "1"

# 路由/模型输出只提供建议，不构成授权；标注不可由调用方改写。
MODEL_ROUTE_ADVISORY = True
MODEL_ROUTE_AUTHORITY = "none"


class RouteAttestationError(RuntimeError):
    """Raised when an external route record fails signature or replay checks."""


class RouteEvidenceError(RuntimeError):
    """Raised when a route evidence record is malformed or missing."""


def _require(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise RouteEvidenceError(f"Route evidence missing required field: {key}")
    return value


@dataclass(frozen=True)
class RouteEligibility:
    """Eligibility gates that were evaluated before selecting a model."""

    cost_band_ok: bool = True
    latency_slo_ok: bool = True
    data_residency_ok: bool = True
    safety_clearance_ok: bool = True
    context_window_ok: bool = True

    def to_dict(self) -> dict[str, bool]:
        return {
            "cost_band_ok": self.cost_band_ok,
            "latency_slo_ok": self.latency_slo_ok,
            "data_residency_ok": self.data_residency_ok,
            "safety_clearance_ok": self.safety_clearance_ok,
            "context_window_ok": self.context_window_ok,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> RouteEligibility:
        data = data or {}
        return cls(
            cost_band_ok=bool(data.get("cost_band_ok", True)),
            latency_slo_ok=bool(data.get("latency_slo_ok", True)),
            data_residency_ok=bool(data.get("data_residency_ok", True)),
            safety_clearance_ok=bool(data.get("safety_clearance_ok", True)),
            context_window_ok=bool(data.get("context_window_ok", True)),
        )


@dataclass(frozen=True)
class ModelRouteDecision:
    """A single model-routing decision and its evidence fields."""

    trace_id: str
    tenant_id: str
    agent_id: str
    requested_model: str
    selected_model: str
    provider: str
    model_version: str
    route_policy_id: str
    route_policy_hash: str
    org_id: str = ""
    session_id: str = ""
    deployment_id: str = ""
    model_family: str = ""
    route_reason: str = ""
    eligibility: RouteEligibility = field(default_factory=RouteEligibility)
    fallback_chain: tuple[str, ...] = ()
    fallback_reason: str = ""
    cross_border_transfer_basis: str = ""
    contract_id: str = ""
    jurisdiction: str = ""
    region: str = ""
    data_residency: str = ""
    retention_class: str = ""
    parent_action_id: str = ""
    attestation_hash: str = ""
    route_decision_id: str = ""
    model_id: str = ""
    schema_version: str = MODEL_ROUTE_SCHEMA_VERSION
    advisory: bool = field(default=MODEL_ROUTE_ADVISORY, init=False)
    authority: str = field(default=MODEL_ROUTE_AUTHORITY, init=False)

    def to_payload(self) -> dict[str, Any]:
        """Signed payload.  ``route_decision_id`` is assigned by MAREF."""

        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "org_id": self.org_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "requested_model": self.requested_model,
            "selected_model": self.selected_model,
            "model_id": self.model_id or self.selected_model,
            "provider": self.provider,
            "deployment_id": self.deployment_id,
            "model_version": self.model_version,
            "model_family": self.model_family,
            "route_policy_id": self.route_policy_id,
            "route_policy_hash": self.route_policy_hash,
            "route_reason": self.route_reason,
            "eligibility": self.eligibility.to_dict(),
            "fallback_chain": list(self.fallback_chain),
            "fallback_reason": self.fallback_reason,
            "cross_border_transfer_basis": self.cross_border_transfer_basis,
            "contract_id": self.contract_id,
            "jurisdiction": self.jurisdiction,
            "region": self.region,
            "data_residency": self.data_residency,
            "retention_class": self.retention_class,
            "parent_action_id": self.parent_action_id,
            "attestation_hash": self.attestation_hash,
            "advisory": self.advisory,
            "authority": self.authority,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ModelRouteDecision:
        fallback = payload.get("fallback_chain") or []
        if not isinstance(fallback, list):
            raise RouteEvidenceError("fallback_chain must be a list")
        schema_version = str(payload.get("schema_version", MODEL_ROUTE_SCHEMA_VERSION))
        if schema_version != MODEL_ROUTE_SCHEMA_VERSION:
            raise RouteEvidenceError(f"Unsupported route schema_version: {schema_version}")
        return cls(
            trace_id=_require(payload, "trace_id"),
            tenant_id=_require(payload, "tenant_id"),
            agent_id=_require(payload, "agent_id"),
            requested_model=_require(payload, "requested_model"),
            selected_model=_require(payload, "selected_model"),
            provider=_require(payload, "provider"),
            model_version=_require(payload, "model_version"),
            route_policy_id=_require(payload, "route_policy_id"),
            route_policy_hash=_require(payload, "route_policy_hash"),
            org_id=str(payload.get("org_id", "")),
            session_id=str(payload.get("session_id", "")),
            deployment_id=str(payload.get("deployment_id", "")),
            model_family=str(payload.get("model_family", "")),
            route_reason=str(payload.get("route_reason", "")),
            eligibility=RouteEligibility.from_dict(payload.get("eligibility")),
            fallback_chain=tuple(str(item) for item in fallback),
            fallback_reason=str(payload.get("fallback_reason", "")),
            cross_border_transfer_basis=str(payload.get("cross_border_transfer_basis", "")),
            contract_id=str(payload.get("contract_id", "")),
            jurisdiction=str(payload.get("jurisdiction", "")),
            region=str(payload.get("region", "")),
            data_residency=str(payload.get("data_residency", "")),
            retention_class=str(payload.get("retention_class", "")),
            parent_action_id=str(payload.get("parent_action_id", "")),
            attestation_hash=str(payload.get("attestation_hash", "")),
            model_id=str(payload.get("model_id", "")),
            schema_version=schema_version,
            # payload 中的 advisory/authority 一律忽略：外部路由不能自称权威。
        )


class ModelRouteRecorder:
    """Persist route decisions into the governance audit chain."""

    def __init__(self, audit: AuditLogger) -> None:
        self._audit = audit
        self._routes: dict[str, dict[str, Any]] = {}
        self._attestations: set[str] = set()
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Index historical routes for replay detection (lazy, once)."""
        if self._loaded:
            return
        for entry in self._audit.read_filtered(event_type=MODEL_ROUTE_EVENT, max_entries=None):
            if not self._audit.verify_entry(entry):
                continue
            metadata = dict(entry.metadata or {})
            metadata["route_decision_id"] = entry.id
            self._routes[entry.id] = metadata
            attestation = str(metadata.get("attestation_hash", ""))
            if attestation:
                self._attestations.add(attestation)
        self._loaded = True

    def record(self, decision: ModelRouteDecision) -> ModelRouteDecision:
        payload = decision.to_payload()
        entry = self._audit.log(
            event_type=MODEL_ROUTE_EVENT,
            actor=decision.agent_id,
            action=f"model.route.{decision.selected_model}",
            details=(
                f"{decision.requested_model} -> {decision.selected_model} "
                f"({decision.provider}, policy={decision.route_policy_id})"
            ),
            metadata={**payload, "route_decision_id": ""},
            parent_action_id=decision.parent_action_id,
            tenant_id=decision.tenant_id,
        )
        metadata = {**payload, "route_decision_id": entry.id}
        self._routes[entry.id] = metadata
        if decision.attestation_hash:
            self._attestations.add(decision.attestation_hash)
        return replace(decision, route_decision_id=entry.id)

    def has_attestation(self, attestation_hash: str) -> bool:
        if not attestation_hash:
            return False
        self._ensure_loaded()
        return attestation_hash in self._attestations

    def get(self, route_decision_id: str) -> ModelRouteDecision | None:
        metadata = self._routes.get(route_decision_id)
        if metadata is None:
            entry = self._audit.find_by_id(route_decision_id)
            if entry is None or entry.event_type != MODEL_ROUTE_EVENT:
                return None
            if not self._audit.verify_entry(entry):
                return None
            metadata = {**dict(entry.metadata or {}), "route_decision_id": entry.id}
            self._routes[route_decision_id] = metadata
        try:
            return ModelRouteDecision.from_payload(metadata)
        except (TypeError, ValueError, RouteEvidenceError):
            return None

    def verify(
        self,
        route_decision_id: str,
        *,
        tenant_id: str = "",
        model_version: str = "",
        provider: str = "",
        agent_id: str = "",
    ) -> bool:
        """Verify that route evidence exists and optional bindings match."""

        decision = self.get(route_decision_id)
        if decision is None:
            return False
        if tenant_id and decision.tenant_id != tenant_id:
            return False
        if model_version and decision.model_version != model_version:
            return False
        if agent_id and decision.agent_id != agent_id:
            return False
        return not (provider and decision.provider != provider)


def attest_external_route(
    payload: Mapping[str, Any],
    signature: str | bytes,
    public_key_pem: str,
) -> ModelRouteDecision:
    """Verify an external router attestation and return the parsed decision.

    The signature must cover :func:`canonical_bytes` of the payload exactly as
    received.  Any parse, type or signature error fails closed.
    """

    if isinstance(signature, str):
        try:
            signature_bytes = bytes.fromhex(signature)
        except ValueError as exc:
            raise RouteAttestationError("Route signature is not valid hex") from exc
    else:
        signature_bytes = signature

    try:
        signed_bytes = canonical_bytes(payload)
        decision = ModelRouteDecision.from_payload(payload)
    except (TypeError, ValueError, RouteEvidenceError) as exc:
        raise RouteAttestationError(f"Invalid route attestation payload: {exc}") from exc

    if not Ed25519KeyPair.verify(public_key_pem, signature_bytes, signed_bytes):
        raise RouteAttestationError("Route attestation signature verification failed")

    expected_hash = hashlib.sha256(signed_bytes).hexdigest()
    if decision.attestation_hash and decision.attestation_hash != expected_hash:
        raise RouteAttestationError("Route attestation hash does not match payload")
    return replace(decision, attestation_hash=expected_hash)


class RouteIngestAdapter:
    """Verify and ingest route records emitted by an external router."""

    def __init__(self, recorder: ModelRouteRecorder, public_key_pem: str) -> None:
        if not public_key_pem.strip():
            raise RouteAttestationError("Router public key is required")
        self._recorder = recorder
        self._public_key_pem = public_key_pem

    def ingest(
        self,
        payload: Mapping[str, Any],
        signature: str | bytes,
    ) -> ModelRouteDecision:
        decision = attest_external_route(payload, signature, self._public_key_pem)
        if self._recorder.has_attestation(decision.attestation_hash):
            raise RouteAttestationError("Route attestation replay detected")
        return self._recorder.record(decision)


__all__ = [
    "MODEL_ROUTE_ADVISORY",
    "MODEL_ROUTE_AUTHORITY",
    "MODEL_ROUTE_EVENT",
    "MODEL_ROUTE_SCHEMA_VERSION",
    "ModelRouteDecision",
    "ModelRouteRecorder",
    "RouteAttestationError",
    "RouteEligibility",
    "RouteEvidenceError",
    "RouteIngestAdapter",
    "attest_external_route",
    "canonical_bytes",
]

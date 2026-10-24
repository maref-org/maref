"""LLM interaction evidence (P0-B).

Records the minimum evidence set needed to reproduce one model interaction:
what was sent (hash + optional encrypted/redacted reference), which model and
route handled it, what came back, and which detectors judged both directions.

Raw prompt/response text is never written to the audit chain.  Callers either
provide hashes, or use :func:`record_interaction` which hashes text in memory
and discards it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any

from maref.governance.audit import AuditLogger
from maref.governance.canonical_json import canonical_hash

INTERACTION_EVENT = "llm_interaction"
INTERACTION_SCHEMA_VERSION = "1"

_DETECTOR_KINDS = frozenset({"rule", "model", "human"})
_VERDICTS = frozenset({"allow", "flag", "block", "unevaluated"})


@dataclass(frozen=True)
class MatchedSpan:
    """A detector hit expressed as an offset, never as copied text."""

    start: int
    end: int
    type: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"Invalid matched span offsets: {self.start}..{self.end}")
        if not self.type:
            raise ValueError("Matched span type is required")

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "type": self.type}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchedSpan:
        return cls(
            start=int(data.get("start", 0)),
            end=int(data.get("end", 0)),
            type=str(data.get("type", "")),
        )


@dataclass(frozen=True)
class SafetyFinding:
    """One detector/judge conclusion with its provenance."""

    detector_id: str
    detector_version: str
    detector_kind: str
    verdict: str
    score: float = 0.0
    threshold: float = 0.0
    matched_spans: tuple[MatchedSpan, ...] = ()
    rationale_ref: str = ""
    judge_model: str = ""
    judge_template_hash: str = ""
    judge_confidence: float = 0.0
    human_review_id: str = ""
    override_reason: str = ""

    def __post_init__(self) -> None:
        if not self.detector_id or not self.detector_version:
            raise ValueError("detector_id and detector_version are required")
        if self.detector_kind not in _DETECTOR_KINDS:
            raise ValueError(f"Invalid detector_kind: {self.detector_kind!r}")
        if self.verdict not in _VERDICTS:
            raise ValueError(f"Invalid safety verdict: {self.verdict!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "detector_kind": self.detector_kind,
            "verdict": self.verdict,
            "score": self.score,
            "threshold": self.threshold,
            "matched_spans": [span.to_dict() for span in self.matched_spans],
            "rationale_ref": self.rationale_ref,
            "judge_model": self.judge_model,
            "judge_template_hash": self.judge_template_hash,
            "judge_confidence": self.judge_confidence,
            "human_review_id": self.human_review_id,
            "override_reason": self.override_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SafetyFinding:
        spans = data.get("matched_spans") or []
        return cls(
            detector_id=str(data.get("detector_id", "")),
            detector_version=str(data.get("detector_version", "")),
            detector_kind=str(data.get("detector_kind", "")),
            verdict=str(data.get("verdict", "")),
            score=float(data.get("score", 0.0)),
            threshold=float(data.get("threshold", 0.0)),
            matched_spans=tuple(MatchedSpan.from_dict(span) for span in spans),
            rationale_ref=str(data.get("rationale_ref", "")),
            judge_model=str(data.get("judge_model", "")),
            judge_template_hash=str(data.get("judge_template_hash", "")),
            judge_confidence=float(data.get("judge_confidence", 0.0)),
            human_review_id=str(data.get("human_review_id", "")),
            override_reason=str(data.get("override_reason", "")),
        )


@dataclass(frozen=True)
class InteractionEvidence:
    """Reproducible evidence for one LLM interaction."""

    trace_id: str
    tenant_id: str
    agent_id: str
    prompt_hash: str
    org_id: str = ""
    session_id: str = ""
    user_id_hash: str = ""
    response_hash: str = ""
    prompt_length: int = 0
    prompt_language: str = ""
    prompt_content_ref: str = ""
    prompt_redacted_ref: str = ""
    response_content_ref: str = ""
    response_redacted_ref: str = ""
    finish_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost: float = 0.0
    route_decision_id: str = ""
    decision_evidence_id: str = ""
    system_prompt_hash: str = ""
    tool_schema_hash: str = ""
    sampling_params_hash: str = ""
    rag_snapshot_id: str = ""
    kb_version: str = ""
    memory_snapshot_id: str = ""
    agent_runtime_version: str = ""
    policy_bundle_hash: str = ""
    detector_set_hash: str = ""
    safety: tuple[SafetyFinding, ...] = ()
    interaction_id: str = ""
    schema_version: str = INTERACTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.prompt_hash:
            raise ValueError("prompt_hash is required (raw prompt must never be stored)")

    def to_metadata(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "org_id": self.org_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "user_id_hash": self.user_id_hash,
            "prompt_hash": self.prompt_hash,
            "response_hash": self.response_hash,
            "prompt_length": self.prompt_length,
            "prompt_language": self.prompt_language,
            "prompt_content_ref": self.prompt_content_ref,
            "prompt_redacted_ref": self.prompt_redacted_ref,
            "response_content_ref": self.response_content_ref,
            "response_redacted_ref": self.response_redacted_ref,
            "finish_reason": self.finish_reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "cost": self.cost,
            "route_decision_id": self.route_decision_id,
            "decision_evidence_id": self.decision_evidence_id,
            "system_prompt_hash": self.system_prompt_hash,
            "tool_schema_hash": self.tool_schema_hash,
            "sampling_params_hash": self.sampling_params_hash,
            "rag_snapshot_id": self.rag_snapshot_id,
            "kb_version": self.kb_version,
            "memory_snapshot_id": self.memory_snapshot_id,
            "agent_runtime_version": self.agent_runtime_version,
            "policy_bundle_hash": self.policy_bundle_hash,
            "detector_set_hash": self.detector_set_hash,
            "safety": [finding.to_dict() for finding in self.safety],
            "interaction_id": self.interaction_id,
        }

    @classmethod
    def from_metadata(cls, data: dict[str, Any]) -> InteractionEvidence:
        findings = data.get("safety") or []
        return cls(
            trace_id=str(data.get("trace_id", "")),
            tenant_id=str(data.get("tenant_id", "")),
            agent_id=str(data.get("agent_id", "")),
            prompt_hash=str(data.get("prompt_hash", "")),
            org_id=str(data.get("org_id", "")),
            session_id=str(data.get("session_id", "")),
            user_id_hash=str(data.get("user_id_hash", "")),
            response_hash=str(data.get("response_hash", "")),
            prompt_length=int(data.get("prompt_length", 0)),
            prompt_language=str(data.get("prompt_language", "")),
            prompt_content_ref=str(data.get("prompt_content_ref", "")),
            prompt_redacted_ref=str(data.get("prompt_redacted_ref", "")),
            response_content_ref=str(data.get("response_content_ref", "")),
            response_redacted_ref=str(data.get("response_redacted_ref", "")),
            finish_reason=str(data.get("finish_reason", "")),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            latency_ms=float(data.get("latency_ms", 0.0)),
            cost=float(data.get("cost", 0.0)),
            route_decision_id=str(data.get("route_decision_id", "")),
            decision_evidence_id=str(data.get("decision_evidence_id", "")),
            system_prompt_hash=str(data.get("system_prompt_hash", "")),
            tool_schema_hash=str(data.get("tool_schema_hash", "")),
            sampling_params_hash=str(data.get("sampling_params_hash", "")),
            rag_snapshot_id=str(data.get("rag_snapshot_id", "")),
            kb_version=str(data.get("kb_version", "")),
            memory_snapshot_id=str(data.get("memory_snapshot_id", "")),
            agent_runtime_version=str(data.get("agent_runtime_version", "")),
            policy_bundle_hash=str(data.get("policy_bundle_hash", "")),
            detector_set_hash=str(data.get("detector_set_hash", "")),
            safety=tuple(SafetyFinding.from_dict(item) for item in findings),
            interaction_id=str(data.get("interaction_id", "")),
            schema_version=str(data.get("schema_version", INTERACTION_SCHEMA_VERSION)),
        )


class InteractionRecorder:
    """Write interaction evidence into the governance audit chain."""

    def __init__(self, audit: AuditLogger) -> None:
        self._audit = audit

    def record(self, evidence: InteractionEvidence) -> InteractionEvidence:
        detector_set_hash = compute_detector_set_hash(evidence.safety) or evidence.detector_set_hash
        payload = evidence.to_metadata()
        payload["interaction_id"] = ""
        payload["detector_set_hash"] = detector_set_hash
        entry = self._audit.log(
            event_type=INTERACTION_EVENT,
            actor=evidence.agent_id,
            action="llm.interaction",
            details=(
                f"trace={evidence.trace_id} prompt={evidence.prompt_hash[:12]} "
                f"response={evidence.response_hash[:12] or '-'} "
                f"route={evidence.route_decision_id or '-'}"
            ),
            metadata=payload,
            parent_action_id=evidence.route_decision_id,
            tenant_id=evidence.tenant_id,
        )
        return replace(
            evidence,
            detector_set_hash=detector_set_hash,
            interaction_id=entry.id,
        )

    def get(self, interaction_id: str) -> InteractionEvidence | None:
        entry = self._audit.find_by_id(interaction_id)
        if entry is None or entry.event_type != INTERACTION_EVENT:
            return None
        if not self._audit.verify_entry(entry):
            return None
        metadata = dict(entry.metadata or {})
        metadata["interaction_id"] = entry.id
        try:
            return InteractionEvidence.from_metadata(metadata)
        except (TypeError, ValueError):
            return None


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_json(value: Any) -> str:
    """Strict canonical hash; raises CanonicalJSONError on unsupported types."""

    return canonical_hash(value)


def compute_detector_set_hash(findings: tuple[SafetyFinding, ...] | list[SafetyFinding]) -> str:
    """Deterministic hash over sorted detector id/version pairs."""

    pairs = sorted(f"{finding.detector_id}@{finding.detector_version}" for finding in findings)
    if not pairs:
        return ""
    return hashlib.sha256("\n".join(pairs).encode("utf-8")).hexdigest()


def record_interaction(
    audit: AuditLogger,
    *,
    prompt: str,
    response: str = "",
    trace_id: str,
    tenant_id: str,
    agent_id: str,
    **kwargs: Any,
) -> InteractionEvidence:
    """Hash raw text in memory and record evidence; raw text is discarded.

    ``kwargs`` are forwarded to :class:`InteractionEvidence` (for example
    ``route_decision_id``, ``safety``, ``prompt_redacted_ref``).
    """

    kwargs["prompt_length"] = len(prompt)
    if response:
        kwargs["response_hash"] = hash_text(response)
    evidence = InteractionEvidence(
        trace_id=trace_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        prompt_hash=hash_text(prompt),
        **kwargs,
    )
    return InteractionRecorder(audit).record(evidence)


__all__ = [
    "INTERACTION_EVENT",
    "INTERACTION_SCHEMA_VERSION",
    "InteractionEvidence",
    "InteractionRecorder",
    "MatchedSpan",
    "SafetyFinding",
    "compute_detector_set_hash",
    "hash_json",
    "hash_text",
    "record_interaction",
]

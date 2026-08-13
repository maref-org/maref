from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class AuditSummary(BaseModel, frozen=True):  # type: ignore[call-arg]
    total_events: int = 0
    time_range_start: float | None = None
    time_range_end: float | None = None
    event_types: dict[str, int] = Field(default_factory=dict)
    actor_counts: dict[str, int] = Field(default_factory=dict)


class SystemStateSnapshot(BaseModel, frozen=True):  # type: ignore[call-arg]
    governance_state: str = ""
    active_agents_count: int = 0
    merkle_tree_size: int = 0
    version: str = ""


class GovernanceReport(BaseModel, frozen=True, extra="forbid"):  # type: ignore[call-arg]
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    report_version: str = "1.0"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    generated_by: str = "maref v0.39.0"
    signer_fingerprint: str = ""
    merkle_root: str = ""
    audit_summary: AuditSummary = Field(default_factory=AuditSummary)
    system_state: SystemStateSnapshot = Field(default_factory=SystemStateSnapshot)
    previous_report_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    signature: str = ""

    def to_json(self, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, data: str) -> GovernanceReport:
        return cls.model_validate_json(data)

    def payload_bytes(self) -> bytes:
        payload_dict = self.model_dump(exclude={"signature"})
        canonical = json.dumps(payload_dict, separators=(",", ":"), sort_keys=True)
        return canonical.encode("utf-8")

    def verify_signature(self, public_key_pem: str) -> bool:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        if not self.signature:
            return False
        sig = base64.b64decode(self.signature)
        return Ed25519KeyPair.verify(public_key_pem, sig, self.payload_bytes())

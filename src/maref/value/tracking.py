"""ValueTrackingEngine: business value capture and aggregation (v0.51 W2-S2 / B2).

Captures per-task business value (ValueMetric set), aggregates by agent / team /
org scope, and HMAC-signs each record so value claims are tamper-evident and
linkable to the governance audit chain.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from maref.value.metrics import ValueMetric

_HMAC_KEY_ENV = "MAREF_VALUE_HMAC_KEY"


@dataclass(frozen=True)
class ValueRecord:
    """A captured business-value claim for one completed task."""

    task_id: str
    agent_id: str
    team_id: str
    org_id: str
    metrics: tuple[ValueMetric, ...] = ()
    recorded_at: float = field(default_factory=time.time)
    signature: str = ""

    def _canonical_payload(self) -> bytes:
        payload = {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "team_id": self.team_id,
            "org_id": self.org_id,
            "recorded_at": self.recorded_at,
            "metrics": [
                {
                    "metric_id": m.metric_id,
                    "metric_type": m.metric_type.value,
                    "baseline": m.baseline,
                    "current": m.current,
                    "unit": m.unit,
                    "label": m.label,
                }
                for m in self.metrics
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "team_id": self.team_id,
            "org_id": self.org_id,
            "metrics": [m.to_dict() for m in self.metrics],
            "recorded_at": self.recorded_at,
            "signature": self.signature,
        }


class ValueTrackingEngine:
    """Captures and aggregates business-value records with HMAC signing."""

    def __init__(self, hmac_key: bytes | str | None = None) -> None:
        if hmac_key is None:
            env_key = os.environ.get(_HMAC_KEY_ENV)
            hmac_key = env_key.encode("utf-8") if env_key else None
        self._hmac_key: bytes | None = (
            hmac_key.encode("utf-8") if isinstance(hmac_key, str) else hmac_key
        )
        self._records: list[ValueRecord] = []

    def _sign(self, payload: bytes) -> str:
        if self._hmac_key is None:
            raise ValueError(
                f"{_HMAC_KEY_ENV} not set — refusing to record unsigned value claim (fail-closed)"
            )
        return hmac.new(self._hmac_key, payload, hashlib.sha256).hexdigest()

    def capture(self, record: ValueRecord) -> ValueRecord:
        signed = ValueRecord(
            task_id=record.task_id,
            agent_id=record.agent_id,
            team_id=record.team_id,
            org_id=record.org_id,
            metrics=record.metrics,
            recorded_at=record.recorded_at,
            signature=self._sign(record._canonical_payload()),
        )
        self._records.append(signed)
        return signed

    def verify(self, record: ValueRecord) -> bool:
        """Verify the record's HMAC signature against its payload (I3 fix).

        Returns False when the signature is missing or does not match the
        current payload — i.e. the record was tampered with or was signed
        under a different key.
        """
        if not record.signature:
            return False
        expected = self._sign(record._canonical_payload())
        return hmac.compare_digest(expected, record.signature)

    def records(self) -> list[ValueRecord]:
        return list(self._records)

    def count(self) -> int:
        return len(self._records)

    def aggregate(self, scope: str, scope_id: str) -> dict[str, Any]:
        """Aggregate value totals for the given scope (agent|team|org).

        Refuses to aggregate when any matching record fails signature
        verification (tamper-evident, I3 fix).
        """
        field_name = {
            "agent": "agent_id",
            "team": "team_id",
            "org": "org_id",
        }.get(scope)
        if field_name is None:
            raise ValueError(f"invalid scope {scope!r}; expected agent|team|org")

        filtered = [r for r in self._records if getattr(r, field_name) == scope_id]
        if any(not self.verify(r) for r in filtered):
            raise ValueError("refusing to aggregate records with invalid signatures")
        totals: dict[str, dict[str, float]] = {}
        for record in filtered:
            for metric in record.metrics:
                bucket = totals.setdefault(metric.metric_type.value, {"delta": 0.0, "count": 0.0})
                bucket["delta"] += metric.delta
                bucket["count"] += 1.0
        return {
            "scope": scope,
            "scope_id": scope_id,
            "record_count": len(filtered),
            "totals": totals,
        }

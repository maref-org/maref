from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TELEMETRY_VERSION = "1.0"
_DEFAULT_ENDPOINT = "https://maref.org/api/v1/telemetry/batch"


@dataclass
class TelemetryEntry:
    id: str
    timestamp: float
    event_type: str
    actor_hash: str
    action: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chain_hash: str = ""


@dataclass
class AggregateReport:
    deployment_id: str
    telemetry_version: str = TELEMETRY_VERSION
    exported_at: float = field(default_factory=time.time)
    total_entries: int = 0
    window_hours: float = 0.0
    fnr: float = 0.0
    fpr: float = 0.0
    avg_entropy: float = 0.0
    state_transition_count: int = 0
    cb_trip_count: int = 0
    anomaly_count: int = 0
    event_type_dist: dict[str, int] = field(default_factory=dict)
    action_dist: dict[str, int] = field(default_factory=dict)
    signed_ratio: float = 0.0


class TelemetryExporter:
    def __init__(
        self,
        audit_paths: list[Path] | None = None,
        deployment_id: str | None = None,
        hmac_secret: str | None = None,
        endpoint: str = _DEFAULT_ENDPOINT,
    ):
        self._audit_paths = audit_paths or [
            Path("governance_audit.jsonl"),
            Path("governance_audit_state_machine.jsonl"),
            Path(".governance/governance_audit.jsonl"),
            Path(".governance/governance_audit_state_machine.jsonl"),
        ]
        self._deployment_id = deployment_id or self._resolve_deployment_id()
        secret = hmac_secret or os.environ.get("MAREF_TELEMETRY_SECRET") or ""
        self._hmac_key = secret.encode("utf-8") if secret else b""
        self._endpoint = endpoint

    @staticmethod
    def _resolve_deployment_id() -> str:
        try:
            result = __import__("subprocess").run(
                ["git", "config", "--get", "remote.origin.url"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return hashlib.sha256(result.stdout.strip().encode()).hexdigest()[:16]
        except Exception:
            pass
        return "unknown-deployment"

    def _hash_actor(self, name: str) -> str:
        if not self._hmac_key:
            return hashlib.sha256(name.encode()).hexdigest()[:16]
        return hmac.new(self._hmac_key, name.encode(), hashlib.sha256).hexdigest()[:16]

    def _read_entries(self, max_entries: int = 5000) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for p in self._audit_paths:
            if not p.exists():
                continue
            try:
                with open(p) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                        if len(entries) >= max_entries:
                            break
            except OSError:
                continue
            if len(entries) >= max_entries:
                break
        return entries

    def _anonymize_entry(self, raw: dict[str, Any]) -> TelemetryEntry:
        meta = raw.get("metadata", {}) or {}
        safe_meta = {
            k: v for k, v in meta.items()
            if k not in ("file_path", "data_classification", "details")
        }
        return TelemetryEntry(
            id=raw.get("id", ""),
            timestamp=raw.get("timestamp", 0.0),
            event_type=raw.get("event_type", ""),
            actor_hash=self._hash_actor(raw.get("actor", "")),
            action=raw.get("action", ""),
            metadata=safe_meta,
            chain_hash=raw.get("chain_hash", ""),
        )

    def build_batch(self, max_entries: int = 5000) -> dict[str, Any]:
        raw_entries = self._read_entries(max_entries=max_entries)
        anonymized = [self._anonymize_entry(e) for e in raw_entries]

        report = self._compute_aggregate(raw_entries)

        batch = {
            "deployment_id": self._deployment_id,
            "telemetry_version": TELEMETRY_VERSION,
            "batch_id": f"batch_{int(time.time())}_{len(anonymized)}",
            "entries": [e.__dict__ for e in anonymized],
            "aggregate": report.__dict__,
        }

        if self._hmac_key:
            payload = json.dumps(batch, sort_keys=True, ensure_ascii=False, default=str)
            batch["hmac_signature"] = hmac.new(
                self._hmac_key, payload.encode(), hashlib.sha256
            ).hexdigest()

        return batch

    def _compute_aggregate(self, entries: list[dict[str, Any]]) -> AggregateReport:
        if not entries:
            return AggregateReport(deployment_id=self._deployment_id)

        event_type_dist = dict(Counter(e.get("event_type", "") for e in entries))
        action_dist = dict(Counter(e.get("action", "") for e in entries))

        time_span = entries[-1].get("timestamp", 0) - entries[0].get("timestamp", 0)
        window_hours = time_span / 3600.0 if time_span > 0 else 0.0

        block_count = sum(1 for e in entries if e.get("action") in ("BLOCK", "DENY"))
        recovery_count = sum(
            1 for e in entries
            if e.get("event_type") == "circuit_breaker"
            or "recovery" in e.get("details", "").lower()
        )
        fnr = recovery_count / max(block_count + recovery_count, 1)

        allow_count = sum(1 for e in entries if e.get("action") in ("ALLOW", "APPROVE"))
        anomaly_after_allow = sum(
            1 for e in entries
            if e.get("event_type") == "anomaly_detected"
            and e.get("action") == "ALLOW"
        )
        fpr = anomaly_after_allow / max(allow_count, 1)

        entropy_values = []
        for e in entries:
            meta = e.get("metadata", {}) or {}
            if "entropy_before" in meta:
                entropy_values.append(float(meta["entropy_before"]))
            if "entropy_after" in meta:
                entropy_values.append(float(meta["entropy_after"]))
        avg_entropy = sum(entropy_values) / max(len(entropy_values), 1)

        signed_count = sum(1 for e in entries if e.get("hmac_signature"))

        return AggregateReport(
            deployment_id=self._deployment_id,
            total_entries=len(entries),
            window_hours=round(window_hours, 2),
            fnr=round(fnr, 4),
            fpr=round(fpr, 4),
            avg_entropy=round(avg_entropy, 4),
            state_transition_count=sum(
                1 for e in entries if e.get("event_type") == "state_transition"
            ),
            cb_trip_count=sum(
                1 for e in entries
                if e.get("event_type") == "circuit_breaker"
                or "trip" in e.get("event_type", "")
            ),
            anomaly_count=sum(1 for e in entries if e.get("event_type") == "anomaly_detected"),
            event_type_dist=event_type_dist,
            action_dist=action_dist,
            signed_ratio=round(signed_count / max(len(entries), 1), 4),
        )

    def export_json(self, max_entries: int = 5000, pretty: bool = False) -> str:
        batch = self.build_batch(max_entries=max_entries)
        return json.dumps(batch, ensure_ascii=False, default=str, indent=2 if pretty else None)

    def send(self, max_entries: int = 5000) -> dict[str, Any]:
        batch = self.build_batch(max_entries=max_entries)
        try:
            import httpx
            resp = httpx.post(
                self._endpoint,
                json=batch,
                timeout=30.0,
                headers={"User-Agent": f"maref-telemetry/{TELEMETRY_VERSION}"},
            )
            if resp.is_success:
                logger.info("Telemetry batch sent: %s entries → %s", len(batch["entries"]), self._endpoint)
                return {"status": "ok", "response": resp.json()}
            else:
                logger.warning("Telemetry send failed: HTTP %s", resp.status_code)
                return {"status": "error", "http_status": resp.status_code}
        except ImportError:
            logger.warning("httpx not installed, falling back to urllib")
            return self._send_urllib(batch)
        except Exception as exc:
            logger.warning("Telemetry send failed: %s", exc)
            return {"status": "error", "error": str(exc)}

    def _send_urllib(self, batch: dict[str, Any]) -> dict[str, Any]:
        try:
            import urllib.request
            data = json.dumps(batch).encode("utf-8")
            req = urllib.request.Request(
                self._endpoint,
                data=data,
                headers={"Content-Type": "application/json", "User-Agent": f"maref-telemetry/{TELEMETRY_VERSION}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return {"status": "ok", "response": json.loads(resp.read())}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.evaluation.saeb.metrics import SAEBMetrics


@dataclass
class GovernanceAuditEntry:
    id: str
    timestamp: float
    event_type: str
    actor: str
    action: str
    details: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    chain_hash: str = ""
    hmac_signature: str = ""


@dataclass
class GovernanceReport:
    total_entries: int
    event_type_dist: dict[str, int]
    action_dist: dict[str, int]
    fnr: float
    fpr: float
    avg_entropy: float
    state_transition_count: int
    cb_trip_count: int
    anomaly_count: int
    time_window_hours: float
    signed_ratio: float


class OpenClawAuditAdapter:
    def __init__(self, audit_paths: list[Path] | None = None):
        self._paths: list[Path] = audit_paths or []
        self._report_cache: GovernanceReport | None = None

    def add_path(self, path: Path) -> None:
        self._paths.append(path)
        self._report_cache = None

    def read_entries(
        self, window: int = 5000, path: Path | None = None
    ) -> list[GovernanceAuditEntry]:
        targets = [path] if path else self._paths
        entries: list[GovernanceAuditEntry] = []
        for p in targets:
            if not p.exists():
                continue
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(
                            GovernanceAuditEntry(
                                id=data.get("id", ""),
                                timestamp=data.get("timestamp", 0.0),
                                event_type=data.get("event_type", ""),
                                actor=data.get("actor", ""),
                                action=data.get("action", ""),
                                details=data.get("details", ""),
                                metadata=data.get("metadata", {}),
                                previous_hash=data.get("previous_hash", ""),
                                chain_hash=data.get("chain_hash", ""),
                                hmac_signature=data.get("hmac_signature", ""),
                            )
                        )
                    except (json.JSONDecodeError, KeyError):
                        continue
                    if len(entries) >= window:
                        break
            if len(entries) >= window:
                break
        return entries

    def compute_governance_report(
        self, entries: list[GovernanceAuditEntry] | None = None, window: int = 5000
    ) -> GovernanceReport:
        if entries is None:
            entries = self.read_entries(window=window)

        if not entries:
            return GovernanceReport(
                total_entries=0,
                event_type_dist={},
                action_dist={},
                fnr=0.0,
                fpr=0.0,
                avg_entropy=0.0,
                state_transition_count=0,
                cb_trip_count=0,
                anomaly_count=0,
                time_window_hours=0.0,
                signed_ratio=0.0,
            )

        event_type_dist = Counter(e.event_type for e in entries)
        action_dist = Counter(e.action for e in entries)

        time_span = entries[-1].timestamp - entries[0].timestamp if len(entries) > 1 else 0.0
        time_window_hours = time_span / 3600.0

        # FNR = BLOCK events that needed recovery
        block_count = sum(1 for e in entries if e.action == "BLOCK" or e.action == "DENY")
        recovery_count = sum(
            1
            for e in entries
            if e.event_type == "circuit_breaker" or "recovery" in e.details.lower()
        )
        fnr = recovery_count / max(block_count + recovery_count, 1)

        # FPR = ALLOW events that later triggered anomaly
        allow_count = sum(1 for e in entries if e.action == "ALLOW" or e.action == "APPROVE")
        anomaly_after_allow = sum(
            1 for e in entries if e.event_type == "anomaly_detected" and e.action == "ALLOW"
        )
        fpr = anomaly_after_allow / max(allow_count, 1)

        # Entropy from state_transition events
        entropy_values = []
        for e in entries:
            meta = e.metadata or {}
            if "entropy_before" in meta:
                entropy_values.append(float(meta.get("entropy_before", 0)))
            if "entropy_after" in meta:
                entropy_values.append(float(meta.get("entropy_after", 0)))
        avg_entropy = sum(entropy_values) / max(len(entropy_values), 1)

        state_transition_count = sum(1 for e in entries if e.event_type == "state_transition")
        cb_trip_count = sum(
            1 for e in entries if e.event_type == "circuit_breaker" or "trip" in e.event_type
        )
        anomaly_count = sum(1 for e in entries if e.event_type == "anomaly_detected")
        signed_count = sum(1 for e in entries if e.hmac_signature)
        signed_ratio = signed_count / max(len(entries), 1)

        report = GovernanceReport(
            total_entries=len(entries),
            event_type_dist=dict(event_type_dist),
            action_dist=dict(action_dist),
            fnr=round(fnr, 4),
            fpr=round(fpr, 4),
            avg_entropy=round(avg_entropy, 4),
            state_transition_count=state_transition_count,
            cb_trip_count=cb_trip_count,
            anomaly_count=anomaly_count,
            time_window_hours=round(time_window_hours, 2),
            signed_ratio=round(signed_ratio, 4),
        )
        self._report_cache = report
        return report

    def to_saeb_metrics(self, window: int = 5000) -> SAEBMetrics:
        entries = self.read_entries(window=window)
        report = self.compute_governance_report(entries, window=window)

        m = SAEBMetrics(
            round=0,
            label="openclaw-governance",
            timestamp=time.time(),
            fnr=report.fnr,
            aggregate_fnr=report.fnr,
            test_pass_rate=1.0 - report.fpr,
        )
        m.passed = report.total_entries - report.cb_trip_count - report.anomaly_count
        m.failed = report.cb_trip_count + report.anomaly_count
        m.total_collected = report.total_entries
        return m

    def fnr_fpr_from_audit(self, path: Path, window: int = 1000) -> tuple[float, float]:
        entries = self.read_entries(window=window, path=path)
        report = self.compute_governance_report(entries, window=window)
        return report.fnr, report.fpr

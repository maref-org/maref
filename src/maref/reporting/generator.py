from __future__ import annotations

from maref.eivl.merkle_auditor import AuditChainIntegrator
from maref.governance.audit import AuditLogger
from maref.reporting.models import (
    AuditSummary,
    GovernanceReport,
    SystemStateSnapshot,
)
from maref.signing.signing_key import ReportSigningKey


class ReportGenerator:
    def __init__(
        self,
        signing_key: ReportSigningKey,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._signing_key = signing_key
        self._audit_logger = audit_logger

    def from_audit_log(
        self,
        audit_logger: AuditLogger | None = None,
        since_timestamp: float | None = None,
        previous_report_id: str = "",
        system_state_override: SystemStateSnapshot | None = None,
    ) -> GovernanceReport:
        logger = audit_logger or self._audit_logger
        if logger is None:
            raise ValueError("AuditLogger required — pass via constructor or argument")

        entries = logger.read_all(max_entries=None)
        if since_timestamp is not None:
            entries = [e for e in entries if e.timestamp > since_timestamp]

        integrator = AuditChainIntegrator()
        for entry in entries:
            integrator.record_audit_entry(entry)

        merkle_root = integrator.merkle.get_root_hash() or ""

        event_types: dict[str, int] = {}
        actor_counts: dict[str, int] = {}
        time_start: float | None = None
        time_end: float | None = None
        for e in entries:
            event_types[e.event_type] = event_types.get(e.event_type, 0) + 1
            actor_counts[e.actor] = actor_counts.get(e.actor, 0) + 1
            if time_start is None or e.timestamp < time_start:
                time_start = e.timestamp
            if time_end is None or e.timestamp > time_end:
                time_end = e.timestamp

        audit_summary = AuditSummary(
            total_events=len(entries),
            time_range_start=time_start,
            time_range_end=time_end,
            event_types=event_types,
            actor_counts=actor_counts,
        )

        if system_state_override is not None:
            system_state = system_state_override
        else:
            system_state = SystemStateSnapshot(
                merkle_tree_size=len(entries),
            )

        report = GovernanceReport(
            signer_fingerprint=self._signing_key.fingerprint,
            merkle_root=merkle_root,
            audit_summary=audit_summary,
            system_state=system_state,
            previous_report_id=previous_report_id,
        )

        sig = self._signing_key.sign_report(report.payload_bytes())
        report = report.model_copy(update={"signature": sig})
        return report

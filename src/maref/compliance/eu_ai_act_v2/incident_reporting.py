"""
EU AI Act Incident Reporting and Corrective Actions — Article 20 + Article 73

Implements:
- Art.20: Corrective actions and duty of information
- Art.73: Serious incident reporting
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class IncidentSeverity(str, Enum):
    """Severity levels for AI system incidents (Art.73(3)-(4))."""

    SERIOUS_BREACH = "serious_breach"
    DEATH_OR_SERIOUS_HEALTH = "death_health"
    SYSTEMIC_RISK_ESCALATION = "systemic_risk"
    MINOR = "minor"


class IncidentStatus(str, Enum):
    """Lifecycle states for incident management."""

    DETECTED = "detected"
    CLASSIFYING = "classifying"
    REPORTING = "reporting"
    INVESTIGATING = "investigating"
    REMEDIATING = "remediating"
    CLOSED = "closed"


_REPORTING_DEADLINES: dict[IncidentSeverity, timedelta] = {
    IncidentSeverity.SERIOUS_BREACH: timedelta(days=15),
    IncidentSeverity.DEATH_OR_SERIOUS_HEALTH: timedelta(days=10),
    IncidentSeverity.SYSTEMIC_RISK_ESCALATION: timedelta(hours=72),
    IncidentSeverity.MINOR: timedelta(days=0),
}

_REQUIRES_REPORTING: set[IncidentSeverity] = {
    IncidentSeverity.SERIOUS_BREACH,
    IncidentSeverity.DEATH_OR_SERIOUS_HEALTH,
    IncidentSeverity.SYSTEMIC_RISK_ESCALATION,
}


@dataclass
class IncidentRecord:
    """A record of an AI system incident (Art.73)."""

    incident_id: str
    system_name: str
    system_version: str
    detected_at: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus
    root_cause: str = ""
    corrective_actions: list[str] = field(default_factory=list)
    authority_notified: bool = False
    notified_at: str = ""
    notification_ref: str = ""
    closed_at: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class CorrectiveAction:
    """A corrective action taken in response to an incident (Art.20)."""

    action_id: str
    incident_id: str
    description: str
    deadline: str
    assigned_to: str
    status: str = "open"


class IncidentManager:
    """Manages incident reporting (Art.73) and corrective actions (Art.20)."""

    def __init__(self) -> None:
        self._incidents: dict[str, IncidentRecord] = {}
        self._actions: dict[str, CorrectiveAction] = {}

    def report_incident(
        self,
        system_name: str,
        description: str,
        severity: IncidentSeverity,
    ) -> IncidentRecord:
        """Report a new incident (Art.73(1)).

        Creates an incident record in DETECTED status.

        Args:
            system_name: Name of the AI system.
            description: Description of the incident.
            severity: Severity classification.

        Returns:
            The newly created IncidentRecord.
        """
        incident_id = f"INC-{uuid4().hex[:8].upper()}"
        record = IncidentRecord(
            incident_id=incident_id,
            system_name=system_name,
            system_version="1.0.0",
            detected_at=datetime.now(timezone.utc).isoformat(),
            description=description,
            severity=severity,
            status=IncidentStatus.DETECTED,
        )
        self._incidents[incident_id] = record
        return record

    def classify_incident(
        self,
        incident_id: str,
        severity: IncidentSeverity,
    ) -> IncidentRecord:
        """Re-classify an incident's severity (Art.73(2)).

        Args:
            incident_id: The ID of the incident.
            severity: The new severity classification.

        Returns:
            The updated IncidentRecord.

        Raises:
            KeyError: If incident_id is not found.
        """
        if incident_id not in self._incidents:
            raise KeyError(f"Incident not found: {incident_id}")
        record = self._incidents[incident_id]
        record.severity = severity
        record.status = IncidentStatus.CLASSIFYING
        return record

    def notify_authority(
        self,
        incident_id: str,
        notification_ref: str,
    ) -> IncidentRecord:
        """Record that a competent authority has been notified (Art.73(3)).

        Args:
            incident_id: The ID of the incident.
            notification_ref: Reference number from the authority.

        Returns:
            The updated IncidentRecord.

        Raises:
            KeyError: If incident_id is not found.
        """
        if incident_id not in self._incidents:
            raise KeyError(f"Incident not found: {incident_id}")
        record = self._incidents[incident_id]
        record.authority_notified = True
        record.notification_ref = notification_ref
        record.notified_at = datetime.now(timezone.utc).isoformat()
        record.status = IncidentStatus.REPORTING
        return record

    def add_corrective_action(
        self,
        incident_id: str,
        description: str,
        deadline: str,
        assigned_to: str,
    ) -> CorrectiveAction:
        """Add a corrective action for an incident (Art.20(1)).

        Args:
            incident_id: The ID of the incident.
            description: What the corrective action entails.
            deadline: ISO date string for completion.
            assigned_to: Person or team responsible.

        Returns:
            The newly created CorrectiveAction.

        Raises:
            KeyError: If incident_id is not found.
        """
        if incident_id not in self._incidents:
            raise KeyError(f"Incident not found: {incident_id}")
        action_id = f"CA-{uuid4().hex[:8].upper()}"
        action = CorrectiveAction(
            action_id=action_id,
            incident_id=incident_id,
            description=description,
            deadline=deadline,
            assigned_to=assigned_to,
        )
        self._actions[action_id] = action
        self._incidents[incident_id].corrective_actions.append(action_id)
        return action

    def close_corrective_action(self, action_id: str) -> CorrectiveAction:
        """Mark a corrective action as closed (Art.20(2)).

        Args:
            action_id: The ID of the corrective action.

        Returns:
            The updated CorrectiveAction.

        Raises:
            KeyError: If action_id is not found.
        """
        if action_id not in self._actions:
            raise KeyError(f"Corrective action not found: {action_id}")
        action = self._actions[action_id]
        action.status = "closed"
        return action

    def close_incident(self, incident_id: str) -> IncidentRecord:
        """Close an incident after resolution (Art.73(5)).

        Args:
            incident_id: The ID of the incident.

        Returns:
            The updated IncidentRecord.

        Raises:
            KeyError: If incident_id is not found.
        """
        if incident_id not in self._incidents:
            raise KeyError(f"Incident not found: {incident_id}")
        record = self._incidents[incident_id]
        record.status = IncidentStatus.CLOSED
        record.closed_at = datetime.now(timezone.utc).isoformat()
        return record

    def get_open_incidents(self) -> list[IncidentRecord]:
        """Get all incidents that are not yet closed.

        Returns:
            List of open IncidentRecord objects.
        """
        return [r for r in self._incidents.values() if r.status != IncidentStatus.CLOSED]

    def get_incident_summary(self) -> dict[str, Any]:
        """Get summary statistics for all incidents.

        Returns:
            Dict with total, open/closed counts, severity breakdown,
            status breakdown, and corrective action counts.
        """
        total = len(self._incidents)
        closed = sum(1 for r in self._incidents.values() if r.status == IncidentStatus.CLOSED)
        open_count = total - closed

        by_severity: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for r in self._incidents.values():
            sev = r.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
            st = r.status.value
            by_status[st] = by_status.get(st, 0) + 1

        all_actions = list(self._actions.values())
        total_ca = len(all_actions)
        open_ca = sum(1 for a in all_actions if a.status != "closed")
        notified = sum(1 for r in self._incidents.values() if r.authority_notified)

        return {
            "total": total,
            "open_count": open_count,
            "closed_count": closed,
            "by_severity": by_severity,
            "by_status": by_status,
            "total_corrective_actions": total_ca,
            "open_corrective_actions": open_ca,
            "notified_count": notified,
        }

    def check_reporting_deadline(self, incident_id: str) -> dict[str, Any]:
        """Check if an incident's reporting deadline is being met (Art.73(3)-(4)).

        Args:
            incident_id: The ID of the incident.

        Returns:
            Dict with deadline info: detected_at, severity, deadline_days,
            deadline (ISO), is_overdue, requires_reporting.

        Raises:
            KeyError: If incident_id is not found.
        """
        if incident_id not in self._incidents:
            raise KeyError(f"Incident not found: {incident_id}")

        record = self._incidents[incident_id]
        detected = datetime.fromisoformat(record.detected_at)
        deadline_delta = _REPORTING_DEADLINES.get(record.severity, timedelta(days=0))
        deadline = detected + deadline_delta
        now = datetime.now(timezone.utc)
        requires = record.severity in _REQUIRES_REPORTING

        return {
            "incident_id": incident_id,
            "severity": record.severity.value,
            "detected_at": record.detected_at,
            "reporting_deadline_days": deadline_delta.total_seconds() / 86400,
            "deadline": deadline.isoformat(),
            "is_overdue": now > deadline if requires else False,
            "requires_reporting": requires,
            "notified": record.authority_notified,
        }

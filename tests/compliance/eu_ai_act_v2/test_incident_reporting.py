"""Tests for EU AI Act incident reporting and corrective actions (Art.20+73)."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.incident_reporting import (
    CorrectiveAction,
    IncidentManager,
    IncidentRecord,
    IncidentSeverity,
    IncidentStatus,
)


class TestIncidentSeverity:
    def test_values(self) -> None:
        assert IncidentSeverity.SERIOUS_BREACH.value == "serious_breach"
        assert IncidentSeverity.DEATH_OR_SERIOUS_HEALTH.value == "death_health"
        assert IncidentSeverity.SYSTEMIC_RISK_ESCALATION.value == "systemic_risk"
        assert IncidentSeverity.MINOR.value == "minor"

    def test_four_severities(self) -> None:
        assert len(list(IncidentSeverity)) == 4


class TestIncidentStatus:
    def test_all_statuses(self) -> None:
        statuses = list(IncidentStatus)
        assert len(statuses) == 6

    def test_lifecycle_order(self) -> None:
        assert IncidentStatus.DETECTED.value == "detected"
        assert IncidentStatus.CLASSIFYING.value == "classifying"
        assert IncidentStatus.REPORTING.value == "reporting"
        assert IncidentStatus.INVESTIGATING.value == "investigating"
        assert IncidentStatus.REMEDIATING.value == "remediating"
        assert IncidentStatus.CLOSED.value == "closed"


class TestIncidentRecord:
    def test_defaults(self) -> None:
        record = IncidentRecord(
            incident_id="INC-001",
            system_name="test-system",
            system_version="1.0.0",
            detected_at="2026-07-11T10:00:00Z",
            description="Test incident",
            severity=IncidentSeverity.MINOR,
            status=IncidentStatus.DETECTED,
        )
        assert record.root_cause == ""
        assert record.corrective_actions == []
        assert not record.authority_notified
        assert record.notified_at == ""
        assert record.notification_ref == ""
        assert record.closed_at == ""
        assert record.evidence == []

    def test_fully_populated(self) -> None:
        record = IncidentRecord(
            incident_id="INC-002",
            system_name="test-system",
            system_version="2.0.0",
            detected_at="2026-07-11T10:00:00Z",
            description="Serious breach",
            severity=IncidentSeverity.SERIOUS_BREACH,
            status=IncidentStatus.INVESTIGATING,
            root_cause="Configuration error",
            corrective_actions=["Patch config"],
            authority_notified=True,
            notified_at="2026-07-11T12:00:00Z",
            notification_ref="REF-001",
            closed_at="",
            evidence=["logs.txt", "config.yaml"],
        )
        assert record.root_cause == "Configuration error"
        assert record.corrective_actions == ["Patch config"]
        assert record.authority_notified
        assert record.notification_ref == "REF-001"


class TestCorrectiveAction:
    def test_default_status(self) -> None:
        action = CorrectiveAction(
            action_id="CA-001",
            incident_id="INC-001",
            description="Fix the issue",
            deadline="2026-07-18",
            assigned_to="engineer-1",
        )
        assert action.status == "open"

    def test_custom_status(self) -> None:
        action = CorrectiveAction(
            action_id="CA-002",
            incident_id="INC-001",
            description="Verify fix",
            deadline="2026-07-20",
            assigned_to="auditor-1",
            status="verified",
        )
        assert action.status == "verified"


class TestIncidentManager:
    def test_initial_state(self) -> None:
        manager = IncidentManager()
        assert manager.get_open_incidents() == []
        summary = manager.get_incident_summary()
        assert summary["total"] == 0
        assert summary["open_count"] == 0
        assert summary["closed_count"] == 0

    def test_report_incident_creates_record(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Unexpected output",
            severity=IncidentSeverity.MINOR,
        )
        assert isinstance(record, IncidentRecord)
        assert record.system_name == "test-system"
        assert record.description == "Unexpected output"
        assert record.severity == IncidentSeverity.MINOR
        assert record.status == IncidentStatus.DETECTED
        assert record.incident_id.startswith("INC-")

    def test_report_incident_sets_detected_at(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Test",
            severity=IncidentSeverity.SERIOUS_BREACH,
        )
        assert record.detected_at != ""

    def test_report_incident_adds_to_open_list(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Test",
            severity=IncidentSeverity.MINOR,
        )
        assert record in manager.get_open_incidents()

    def test_classify_incident_changes_severity(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Test",
            severity=IncidentSeverity.MINOR,
        )
        updated = manager.classify_incident(record.incident_id, IncidentSeverity.SERIOUS_BREACH)
        assert updated.severity == IncidentSeverity.SERIOUS_BREACH
        assert updated.status == IncidentStatus.CLASSIFYING

    def test_classify_incident_raises_on_nonexistent(self) -> None:
        manager = IncidentManager()
        try:
            manager.classify_incident("INC-NONEXISTENT", IncidentSeverity.SERIOUS_BREACH)
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass

    def test_notify_authority_sets_notification(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Test",
            severity=IncidentSeverity.SERIOUS_BREACH,
        )
        manager.classify_incident(record.incident_id, IncidentSeverity.SERIOUS_BREACH)
        updated = manager.notify_authority(record.incident_id, "REF-ABC-123")
        assert updated.authority_notified
        assert updated.notification_ref == "REF-ABC-123"
        assert updated.notified_at != ""
        assert updated.status == IncidentStatus.REPORTING

    def test_notify_authority_raises_on_nonexistent(self) -> None:
        manager = IncidentManager()
        try:
            manager.notify_authority("INC-NONEXISTENT", "REF-001")
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass

    def test_add_corrective_action(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Test",
            severity=IncidentSeverity.MINOR,
        )
        action = manager.add_corrective_action(
            incident_id=record.incident_id,
            description="Apply hotfix",
            deadline="2026-07-18",
            assigned_to="dev-team",
        )
        assert isinstance(action, CorrectiveAction)
        assert action.incident_id == record.incident_id
        assert action.description == "Apply hotfix"
        assert action.deadline == "2026-07-18"
        assert action.assigned_to == "dev-team"
        assert action.status == "open"

    def test_add_corrective_action_updates_record(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Test",
            severity=IncidentSeverity.MINOR,
        )
        manager.add_corrective_action(
            incident_id=record.incident_id,
            description="Hotfix",
            deadline="2026-07-18",
            assigned_to="dev-team",
        )
        updated = manager.get_incident_summary()
        assert updated["total_corrective_actions"] == 1
        assert updated["open_corrective_actions"] == 1

    def test_add_corrective_action_raises_on_nonexistent(self) -> None:
        manager = IncidentManager()
        try:
            manager.add_corrective_action(
                incident_id="INC-NONEXISTENT",
                description="Fix",
                deadline="2026-07-18",
                assigned_to="dev-team",
            )
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass

    def test_close_corrective_action(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Test",
            severity=IncidentSeverity.MINOR,
        )
        action = manager.add_corrective_action(
            incident_id=record.incident_id,
            description="Hotfix",
            deadline="2026-07-18",
            assigned_to="dev-team",
        )
        closed = manager.close_corrective_action(action.action_id)
        assert closed.status == "closed"

    def test_close_corrective_action_raises_on_nonexistent(self) -> None:
        manager = IncidentManager()
        try:
            manager.close_corrective_action("CA-NONEXISTENT")
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass

    def test_close_incident_sets_status_and_timestamp(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Test",
            severity=IncidentSeverity.MINOR,
        )
        closed = manager.close_incident(record.incident_id)
        assert closed.status == IncidentStatus.CLOSED
        assert closed.closed_at != ""
        assert closed.root_cause == ""

    def test_close_incident_removes_from_open(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Test",
            severity=IncidentSeverity.MINOR,
        )
        manager.close_incident(record.incident_id)
        assert record not in manager.get_open_incidents()

    def test_close_incident_raises_on_nonexistent(self) -> None:
        manager = IncidentManager()
        try:
            manager.close_incident("INC-NONEXISTENT")
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass

    def test_get_open_incidents_filters_closed(self) -> None:
        manager = IncidentManager()
        r1 = manager.report_incident("sys-a", "Issue 1", IncidentSeverity.MINOR)
        r2 = manager.report_incident("sys-a", "Issue 2", IncidentSeverity.MINOR)
        manager.close_incident(r1.incident_id)
        open_incidents = manager.get_open_incidents()
        assert r1 not in open_incidents
        assert r2 in open_incidents

    def test_get_incident_summary_counts(self) -> None:
        manager = IncidentManager()
        r1 = manager.report_incident("sys-a", "Issue 1", IncidentSeverity.MINOR)
        manager.report_incident("sys-a", "Issue 2", IncidentSeverity.SERIOUS_BREACH)
        manager.close_incident(r1.incident_id)
        summary = manager.get_incident_summary()
        assert summary["total"] == 2
        assert summary["open_count"] == 1
        assert summary["closed_count"] == 1

    def test_get_incident_summary_by_severity(self) -> None:
        manager = IncidentManager()
        manager.report_incident("sys-a", "Minor", IncidentSeverity.MINOR)
        manager.report_incident("sys-b", "Serious", IncidentSeverity.SERIOUS_BREACH)
        manager.report_incident("sys-c", "Death", IncidentSeverity.DEATH_OR_SERIOUS_HEALTH)
        manager.report_incident("sys-d", "Systemic", IncidentSeverity.SYSTEMIC_RISK_ESCALATION)
        summary = manager.get_incident_summary()
        assert summary["by_severity"]["serious_breach"] == 1
        assert summary["by_severity"]["death_health"] == 1
        assert summary["by_severity"]["systemic_risk"] == 1
        assert summary["by_severity"]["minor"] == 1

    def test_get_incident_summary_by_status(self) -> None:
        manager = IncidentManager()
        manager.report_incident("sys-a", "Test", IncidentSeverity.MINOR)
        summary = manager.get_incident_summary()
        assert summary["by_status"]["detected"] == 1

    def test_check_reporting_deadline_serious_breach(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Breach",
            severity=IncidentSeverity.SERIOUS_BREACH,
        )
        result = manager.check_reporting_deadline(record.incident_id)
        assert result["reporting_deadline_days"] == 15
        assert "detected_at" in result
        assert "deadline" in result
        assert "is_overdue" in result

    def test_check_reporting_deadline_death_health(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Death",
            severity=IncidentSeverity.DEATH_OR_SERIOUS_HEALTH,
        )
        result = manager.check_reporting_deadline(record.incident_id)
        assert result["reporting_deadline_days"] == 10

    def test_check_reporting_deadline_systemic_risk(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Systemic",
            severity=IncidentSeverity.SYSTEMIC_RISK_ESCALATION,
        )
        result = manager.check_reporting_deadline(record.incident_id)
        assert result["reporting_deadline_days"] == 3.0  # 72 hours = 3 days

    def test_check_reporting_deadline_minor(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            system_name="test-system",
            description="Minor",
            severity=IncidentSeverity.MINOR,
        )
        result = manager.check_reporting_deadline(record.incident_id)
        assert result["reporting_deadline_days"] == 0
        assert result["requires_reporting"] is False

    def test_check_reporting_deadline_raises_on_nonexistent(self) -> None:
        manager = IncidentManager()
        try:
            manager.check_reporting_deadline("INC-NONEXISTENT")
            raise AssertionError("Expected KeyError")
        except KeyError:
            pass


class TestIncidentLifecycle:
    def test_full_lifecycle(self) -> None:
        manager = IncidentManager()
        # Step 1: Detect
        record = manager.report_incident(
            system_name="ai-trading-system",
            description="Algorithmic bias detected in loan decisions",
            severity=IncidentSeverity.MINOR,
        )
        assert record.status == IncidentStatus.DETECTED
        # Step 2: Classify
        record = manager.classify_incident(record.incident_id, IncidentSeverity.SERIOUS_BREACH)
        assert record.status == IncidentStatus.CLASSIFYING
        assert record.severity == IncidentSeverity.SERIOUS_BREACH
        # Step 3: Report to authority
        record = manager.notify_authority(record.incident_id, "EU-AI-REF-2026-001")
        assert record.status == IncidentStatus.REPORTING
        assert record.authority_notified
        # Step 4: Add corrective actions
        action1 = manager.add_corrective_action(
            incident_id=record.incident_id,
            description="Retrain model with balanced dataset",
            deadline="2026-08-01",
            assigned_to="ml-team",
        )
        action2 = manager.add_corrective_action(
            incident_id=record.incident_id,
            description="Audit historical decisions",
            deadline="2026-07-25",
            assigned_to="audit-team",
        )
        # Step 5: Close corrective actions
        manager.close_corrective_action(action1.action_id)
        manager.close_corrective_action(action2.action_id)
        # Step 6: Close incident
        record = manager.close_incident(record.incident_id)
        assert record.status == IncidentStatus.CLOSED
        assert record.closed_at != ""
        # Step 7: Verify summary
        summary = manager.get_incident_summary()
        assert summary["closed_count"] == 1


class TestEdgeCases:
    def test_missing_root_cause_on_close(self) -> None:
        """Incident can be closed without root cause."""
        manager = IncidentManager()
        record = manager.report_incident("sys-a", "Test", IncidentSeverity.MINOR)
        closed = manager.close_incident(record.incident_id)
        assert closed.root_cause == ""

    def test_empty_corrective_actions(self) -> None:
        """Incident can be closed without corrective actions."""
        manager = IncidentManager()
        record = manager.report_incident("sys-a", "Test", IncidentSeverity.MINOR)
        closed = manager.close_incident(record.incident_id)
        assert closed.corrective_actions == []

    def test_reopen_closed_incident(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident("sys-a", "Test", IncidentSeverity.MINOR)
        manager.close_incident(record.incident_id)
        # Reopen by re-classifying
        reopened = manager.classify_incident(record.incident_id, IncidentSeverity.MINOR)
        assert reopened.status == IncidentStatus.CLASSIFYING
        assert reopened.severity == IncidentSeverity.MINOR
        assert reopened in manager.get_open_incidents()  # Now open again

    def test_multiple_incidents_filtering(self) -> None:
        manager = IncidentManager()
        for i in range(5):
            manager.report_incident(f"sys-{i}", f"Issue {i}", IncidentSeverity.MINOR)
        assert len(manager.get_open_incidents()) == 5

    def test_close_incident_with_open_corrective_actions(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident("sys-a", "Test", IncidentSeverity.MINOR)
        manager.add_corrective_action(
            record.incident_id,
            "Open action",
            "2026-07-18",
            "dev-team",
        )
        # Can still close the incident even with open corrective actions
        closed = manager.close_incident(record.incident_id)
        assert closed.status == IncidentStatus.CLOSED

    def test_authority_notification_tracking(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident("sys-a", "Test", IncidentSeverity.SERIOUS_BREACH)
        manager.classify_incident(record.incident_id, IncidentSeverity.SERIOUS_BREACH)
        manager.notify_authority(record.incident_id, "REF-001")
        summary = manager.get_incident_summary()
        assert summary["notified_count"] == 1

    def test_deadline_compliance_minor_not_required(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident("sys-a", "Test", IncidentSeverity.MINOR)
        result = manager.check_reporting_deadline(record.incident_id)
        assert not result["requires_reporting"]

    def test_deadline_compliance_requires_reporting(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident(
            "sys-a",
            "Serious breach",
            IncidentSeverity.SERIOUS_BREACH,
        )
        result = manager.check_reporting_deadline(record.incident_id)
        assert result["requires_reporting"]

    def test_deadline_compliance_notified_not_overdue(self) -> None:
        manager = IncidentManager()
        record = manager.report_incident("sys-a", "Test", IncidentSeverity.SERIOUS_BREACH)
        manager.classify_incident(record.incident_id, IncidentSeverity.SERIOUS_BREACH)
        manager.notify_authority(record.incident_id, "REF-001")
        result = manager.check_reporting_deadline(record.incident_id)
        assert not result["is_overdue"]

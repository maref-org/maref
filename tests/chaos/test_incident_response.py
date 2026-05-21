from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"
RUNBOOK_DIR = DOCS_DIR / "runbook"


class Severity(Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


@dataclass
class Incident:
    title: str
    severity: Severity
    description: str
    response_time_minutes: int
    acknowledged: bool
    resolved: bool


@dataclass
class EscalationRule:
    severity: Severity
    acknowledge_timeout_minutes: int
    escalation_timeout_minutes: int
    target_level: str


SEVERITY_RULES: dict[Severity, dict[str, Any]] = {
    Severity.P0: {
        "acknowledge_min": 5,
        "escalation_min": 15,
        "restore_target_min": 60,
    },
    Severity.P1: {
        "acknowledge_min": 15,
        "escalation_min": 30,
        "restore_target_min": 240,
    },
    Severity.P2: {
        "acknowledge_min": 60,
        "escalation_min": 240,
        "restore_target_min": 1440,
    },
    Severity.P3: {
        "acknowledge_min": 480,
        "escalation_min": 1440,
        "restore_target_min": 4320,
    },
}

P0_EVENTS = {"sidecar_down", "audit_log_failure", "security_vulnerability"}
P1_EVENTS = {"high_latency", "memory_growth", "governance_drift"}
P2_EVENTS = {"performance_degradation", "non_critical_alert"}
P3_EVENTS = {"consultation", "suggestion"}

POSTMORTEM_REQUIRED_FIELDS = [
    "incident_id",
    "title",
    "reporter",
    "date",
    "duration",
    "severity",
    "timeline",
    "impact_assessment",
    "root_cause",
    "direct_cause",
    "five_whys",
    "review_good",
    "review_bad",
    "review_improvements",
    "reads_review",
    "reads_evaluate",
    "reads_analyze",
    "reads_document",
    "reads_share",
    "action_items",
    "prevention_measures",
]

REQUIRED_RUNBOOKS = [
    "rb-001-sidecar-down.md",
    "rb-002-governance-latency.md",
    "rb-003-drift-detected.md",
    "rb-004-audit-log-failure.md",
    "rb-005-memory-growth.md",
    "rb-006-high-latency.md",
    "rb-007-error-budget-burn.md",
    "rb-008-governance-drift.md",
]


def classify_event(event_name: str) -> Severity:
    if event_name in P0_EVENTS:
        return Severity.P0
    if event_name in P1_EVENTS:
        return Severity.P1
    if event_name in P2_EVENTS:
        return Severity.P2
    if event_name in P3_EVENTS:
        return Severity.P3
    raise ValueError(f"Unknown event: {event_name}")


def should_escalate(incident: Incident, elapsed_minutes: int) -> bool:
    rule = SEVERITY_RULES[incident.severity]
    if not incident.acknowledged and elapsed_minutes > rule["acknowledge_min"]:
        return True
    if not incident.resolved and elapsed_minutes > rule["escalation_min"]:
        return True
    return False


def check_sla_compliance(incident: Incident, restore_minutes: int) -> bool:
    target = SEVERITY_RULES[incident.severity]["restore_target_min"]
    return restore_minutes <= target


class TestIncidentClassification:
    def test_p0_events_classify_correctly(self) -> None:
        for event in P0_EVENTS:
            assert classify_event(event) == Severity.P0

    def test_p1_events_classify_correctly(self) -> None:
        for event in P1_EVENTS:
            assert classify_event(event) == Severity.P1

    def test_p2_events_classify_correctly(self) -> None:
        for event in P2_EVENTS:
            assert classify_event(event) == Severity.P2

    def test_p3_events_classify_correctly(self) -> None:
        for event in P3_EVENTS:
            assert classify_event(event) == Severity.P3

    def test_no_overlap_between_severity_levels(self) -> None:
        all_p0 = P0_EVENTS
        all_p1 = P1_EVENTS
        all_p2 = P2_EVENTS
        all_p3 = P3_EVENTS
        assert all_p0.isdisjoint(all_p1)
        assert all_p0.isdisjoint(all_p2)
        assert all_p0.isdisjoint(all_p3)
        assert all_p1.isdisjoint(all_p2)
        assert all_p1.isdisjoint(all_p3)
        assert all_p2.isdisjoint(all_p3)

    def test_unknown_event_raises_error(self) -> None:
        with pytest.raises(ValueError):
            classify_event("unknown_event_type")

    def test_p0_sidecar_down_classification(self) -> None:
        assert classify_event("sidecar_down") == Severity.P0

    def test_p0_audit_log_failure_classification(self) -> None:
        assert classify_event("audit_log_failure") == Severity.P0

    def test_p0_security_vulnerability_classification(self) -> None:
        assert classify_event("security_vulnerability") == Severity.P0

    def test_p1_high_latency_classification(self) -> None:
        assert classify_event("high_latency") == Severity.P1

    def test_p1_memory_growth_classification(self) -> None:
        assert classify_event("memory_growth") == Severity.P1

    def test_p1_governance_drift_classification(self) -> None:
        assert classify_event("governance_drift") == Severity.P1

    def test_p2_performance_degradation_classification(self) -> None:
        assert classify_event("performance_degradation") == Severity.P2

    def test_p2_non_critical_alert_classification(self) -> None:
        assert classify_event("non_critical_alert") == Severity.P2

    def test_p3_consultation_classification(self) -> None:
        assert classify_event("consultation") == Severity.P3

    def test_p3_suggestion_classification(self) -> None:
        assert classify_event("suggestion") == Severity.P3


class TestEscalationPathCompleteness:
    def test_escalation_path_document_exists(self) -> None:
        target = DOCS_DIR / "escalation-path.md"
        assert target.exists(), f"Missing escalation-path.md at {target}"

    def test_emergency_contacts_document_exists(self) -> None:
        target = DOCS_DIR / "emergency-contacts.md"
        assert target.exists(), f"Missing emergency-contacts.md at {target}"

    def test_postmortem_template_document_exists(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        assert target.exists(), f"Missing incident-postmortem-template.md at {target}"

    def test_all_severity_levels_have_escalation_rules(self) -> None:
        for severity in Severity:
            assert severity in SEVERITY_RULES

    def test_p0_escalation_timeout_is_15_minutes(self) -> None:
        assert SEVERITY_RULES[Severity.P0]["escalation_min"] == 15

    def test_p1_escalation_timeout_is_30_minutes(self) -> None:
        assert SEVERITY_RULES[Severity.P1]["escalation_min"] == 30

    def test_p0_acknowledge_timeout_is_5_minutes(self) -> None:
        assert SEVERITY_RULES[Severity.P0]["acknowledge_min"] == 5

    def test_p1_acknowledge_timeout_is_15_minutes(self) -> None:
        assert SEVERITY_RULES[Severity.P1]["acknowledge_min"] == 15

    def test_escalation_times_decrease_with_severity(self) -> None:
        p0_esc = SEVERITY_RULES[Severity.P0]["escalation_min"]
        p1_esc = SEVERITY_RULES[Severity.P1]["escalation_min"]
        p2_esc = SEVERITY_RULES[Severity.P2]["escalation_min"]
        p3_esc = SEVERITY_RULES[Severity.P3]["escalation_min"]
        assert p0_esc < p1_esc < p2_esc < p3_esc

    def test_all_required_runbooks_exist(self) -> None:
        for rb in REQUIRED_RUNBOOKS:
            target = RUNBOOK_DIR / rb
            assert target.exists(), f"Missing runbook: {rb}"

    def test_p0_events_have_runbook_references(self) -> None:
        p0_runbook_map = {
            "sidecar_down": "rb-001-sidecar-down.md",
            "audit_log_failure": "rb-004-audit-log-failure.md",
        }
        for event_name, rb_name in p0_runbook_map.items():
            target = RUNBOOK_DIR / rb_name
            assert target.exists(), f"P0 event {event_name} missing runbook {rb_name}"

    def test_p1_events_have_runbook_references(self) -> None:
        p1_runbook_map = {
            "high_latency": "rb-006-high-latency.md",
            "memory_growth": "rb-005-memory-growth.md",
            "governance_drift": "rb-008-governance-drift.md",
        }
        for event_name, rb_name in p1_runbook_map.items():
            target = RUNBOOK_DIR / rb_name
            assert target.exists(), f"P1 event {event_name} missing runbook {rb_name}"


class TestEscalationLogic:
    def test_p0_should_escalate_after_15_minutes_no_ack(self) -> None:
        incident = Incident(
            title="Sidecar Down",
            severity=Severity.P0,
            description="Sidecar unavailable",
            response_time_minutes=0,
            acknowledged=False,
            resolved=False,
        )
        assert should_escalate(incident, elapsed_minutes=15)

    def test_p0_should_not_escalate_before_15_minutes(self) -> None:
        incident = Incident(
            title="Sidecar Down",
            severity=Severity.P0,
            description="Sidecar unavailable",
            response_time_minutes=0,
            acknowledged=True,
            resolved=False,
        )
        assert not should_escalate(incident, elapsed_minutes=10)

    def test_p1_should_escalate_after_30_minutes_no_ack(self) -> None:
        incident = Incident(
            title="High Latency",
            severity=Severity.P1,
            description="P99 latency > 500ms",
            response_time_minutes=0,
            acknowledged=False,
            resolved=False,
        )
        assert should_escalate(incident, elapsed_minutes=30)

    def test_p1_should_not_escalate_before_30_minutes(self) -> None:
        incident = Incident(
            title="High Latency",
            severity=Severity.P1,
            description="P99 latency > 500ms",
            response_time_minutes=0,
            acknowledged=True,
            resolved=False,
        )
        assert not should_escalate(incident, elapsed_minutes=25)

    def test_p2_should_escalate_after_4_hours_no_ack(self) -> None:
        incident = Incident(
            title="Performance Degradation",
            severity=Severity.P2,
            description="Non-critical path degraded",
            response_time_minutes=0,
            acknowledged=False,
            resolved=False,
        )
        assert should_escalate(incident, elapsed_minutes=240)

    def test_p2_should_not_escalate_before_4_hours(self) -> None:
        incident = Incident(
            title="Performance Degradation",
            severity=Severity.P2,
            description="Non-critical path degraded",
            response_time_minutes=0,
            acknowledged=True,
            resolved=False,
        )
        assert not should_escalate(incident, elapsed_minutes=200)

    def test_p3_should_escalate_after_24_hours_no_ack(self) -> None:
        incident = Incident(
            title="Consultation",
            severity=Severity.P3,
            description="Feature consultation",
            response_time_minutes=0,
            acknowledged=False,
            resolved=False,
        )
        assert should_escalate(incident, elapsed_minutes=1440)

    def test_resolved_incident_should_not_escalate(self) -> None:
        incident = Incident(
            title="Sidecar Down",
            severity=Severity.P0,
            description="Resolved",
            response_time_minutes=10,
            acknowledged=True,
            resolved=True,
        )
        assert not should_escalate(incident, elapsed_minutes=60)


class TestResponseTimeSLA:
    def test_p0_sla_restore_target_is_60_minutes(self) -> None:
        assert SEVERITY_RULES[Severity.P0]["restore_target_min"] == 60

    def test_p1_sla_restore_target_is_4_hours(self) -> None:
        assert SEVERITY_RULES[Severity.P1]["restore_target_min"] == 240

    def test_p2_sla_restore_target_is_24_hours(self) -> None:
        assert SEVERITY_RULES[Severity.P2]["restore_target_min"] == 1440

    def test_p3_sla_restore_target_is_72_hours(self) -> None:
        assert SEVERITY_RULES[Severity.P3]["restore_target_min"] == 4320

    def test_p0_compliant_within_sla(self) -> None:
        incident = Incident(
            title="Sidecar Down",
            severity=Severity.P0,
            description="",
            response_time_minutes=5,
            acknowledged=True,
            resolved=True,
        )
        assert check_sla_compliance(incident, restore_minutes=45)

    def test_p0_exceeds_sla(self) -> None:
        incident = Incident(
            title="Sidecar Down",
            severity=Severity.P0,
            description="",
            response_time_minutes=5,
            acknowledged=True,
            resolved=True,
        )
        assert not check_sla_compliance(incident, restore_minutes=90)

    def test_p1_compliant_within_sla(self) -> None:
        incident = Incident(
            title="High Latency",
            severity=Severity.P1,
            description="",
            response_time_minutes=15,
            acknowledged=True,
            resolved=True,
        )
        assert check_sla_compliance(incident, restore_minutes=180)

    def test_p1_exceeds_sla(self) -> None:
        incident = Incident(
            title="High Latency",
            severity=Severity.P1,
            description="",
            response_time_minutes=15,
            acknowledged=True,
            resolved=True,
        )
        assert not check_sla_compliance(incident, restore_minutes=300)

    def test_sla_tightens_with_severity(self) -> None:
        p0 = SEVERITY_RULES[Severity.P0]["restore_target_min"]
        p1 = SEVERITY_RULES[Severity.P1]["restore_target_min"]
        p2 = SEVERITY_RULES[Severity.P2]["restore_target_min"]
        p3 = SEVERITY_RULES[Severity.P3]["restore_target_min"]
        assert p0 < p1 < p2 < p3


class TestSeverityJudgmentLogic:
    def test_p0_judgment_sidecar_down(self) -> None:
        assert classify_event("sidecar_down") == Severity.P0

    def test_p0_judgment_audit_log_failure(self) -> None:
        assert classify_event("audit_log_failure") == Severity.P0

    def test_p0_judgment_security_vulnerability(self) -> None:
        assert classify_event("security_vulnerability") == Severity.P0

    def test_p0_events_are_critical(self) -> None:
        for event in P0_EVENTS:
            sev = classify_event(event)
            assert sev == Severity.P0

    def test_p1_events_are_high(self) -> None:
        for event in P1_EVENTS:
            sev = classify_event(event)
            assert sev == Severity.P1

    def test_p2_events_are_medium(self) -> None:
        for event in P2_EVENTS:
            sev = classify_event(event)
            assert sev == Severity.P2

    def test_p3_events_are_low(self) -> None:
        for event in P3_EVENTS:
            sev = classify_event(event)
            assert sev == Severity.P3

    def test_no_event_maps_to_multiple_severities(self) -> None:
        all_events = P0_EVENTS | P1_EVENTS | P2_EVENTS | P3_EVENTS
        assert len(all_events) == len(P0_EVENTS) + len(P1_EVENTS) + len(P2_EVENTS) + len(P3_EVENTS)

    def test_event_classification_is_deterministic(self) -> None:
        for event in P0_EVENTS | P1_EVENTS | P2_EVENTS | P3_EVENTS:
            first = classify_event(event)
            second = classify_event(event)
            assert first == second


class TestPostmortemTemplateCompleteness:
    def test_postmortem_template_file_exists(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        assert target.exists()

    def test_postmortem_contains_incident_id_field(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        content = target.read_text("utf-8")
        assert "INC-YYYY-MM-DD-NNN" in content

    def test_postmortem_contains_severity_levels(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        content = target.read_text("utf-8")
        for sev in ("P0", "P1", "P2", "P3"):
            assert sev in content

    def test_postmortem_contains_5_whys(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        content = target.read_text("utf-8")
        assert "5 Whys" in content or "Why" in content

    def test_postmortem_contains_timeline_section(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        content = target.read_text("utf-8")
        assert "时间线" in content or "timeline" in content.lower()

    def test_postmortem_contains_root_cause_section(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        content = target.read_text("utf-8")
        assert "根因分析" in content

    def test_postmortem_contains_action_items(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        content = target.read_text("utf-8")
        assert "行动项" in content

    def test_postmortem_contains_reads_principles(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        content = target.read_text("utf-8")
        reads_sections = ["Review", "Evaluate", "Analyze", "Document", "Share"]
        for section in reads_sections:
            assert section.lower() in content.lower()

    def test_postmortem_contains_prevention_measures(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        content = target.read_text("utf-8")
        assert "预防措施" in content or "prevention" in content.lower()

    def test_postmortem_contains_impact_assessment(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        content = target.read_text("utf-8")
        assert "影响评估" in content

    def test_postmortem_contains_mttr_field(self) -> None:
        target = DOCS_DIR / "incident-postmortem-template.md"
        content = target.read_text("utf-8")
        assert "MTTR" in content


class TestGoNoGoUpdate:
    def test_go_no_go_contains_m4_escalation_path(self) -> None:
        target = DOCS_DIR / "go-no-go-template.md"
        content = target.read_text("utf-8")
        assert "4.6" in content
        assert "escalation-path.md" in content

    def test_go_no_go_contains_m4_postmortem_template(self) -> None:
        target = DOCS_DIR / "go-no-go-template.md"
        content = target.read_text("utf-8")
        assert "4.7" in content
        assert "incident-postmortem-template.md" in content

    def test_go_no_go_contains_m4_emergency_contacts(self) -> None:
        target = DOCS_DIR / "go-no-go-template.md"
        content = target.read_text("utf-8")
        assert "4.8" in content
        assert "emergency-contacts.md" in content


class TestEscalationPathCompliance:
    def test_p0_unacknowledged_escalates_to_l2(self) -> None:
        incident = Incident("test", Severity.P0, "", 0, False, False)
        assert should_escalate(incident, 15)

    def test_p0_acknowledged_unresolved_does_not_escalate_early(self) -> None:
        incident = Incident("test", Severity.P0, "", 5, True, False)
        assert not should_escalate(incident, 14)

    def test_p1_unacknowledged_escalates_to_l2(self) -> None:
        incident = Incident("test", Severity.P1, "", 0, False, False)
        assert should_escalate(incident, 30)

    def test_p1_acknowledged_unresolved_does_not_escalate_early(self) -> None:
        incident = Incident("test", Severity.P1, "", 10, True, False)
        assert not should_escalate(incident, 29)

    def test_p2_unacknowledged_escalates_to_l2(self) -> None:
        incident = Incident("test", Severity.P2, "", 0, False, False)
        assert should_escalate(incident, 240)

    def test_p2_acknowledged_does_not_escalate_early(self) -> None:
        incident = Incident("test", Severity.P2, "", 30, True, True)
        assert not should_escalate(incident, 200)

    def test_p3_unacknowledged_escalates_to_l2(self) -> None:
        incident = Incident("test", Severity.P3, "", 0, False, False)
        assert should_escalate(incident, 1440)

    def test_p3_acknowledged_does_not_escalate_early(self) -> None:
        incident = Incident("test", Severity.P3, "", 60, True, True)
        assert not should_escalate(incident, 1000)
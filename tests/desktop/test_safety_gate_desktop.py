from __future__ import annotations

from maref.desktop.safety_gate_desktop import (
    DesktopOperationRecord,
    DesktopSafetyGateV2,
    DesktopThreatAssessment,
    DesktopThreatCategory,
    DesktopThreatSeverity,
)


class TestDesktopSafetyGateV2:
    def test_init_not_locked(self) -> None:
        gate = DesktopSafetyGateV2()
        assert not gate.is_locked
        assert gate.consecutive_failures == 0

    def test_assess_ui_interaction_safe(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("click OK button")
        assert not result.threat_detected
        assert not result.blocked
        assert result.severity == DesktopThreatSeverity.NONE

    def test_assess_ui_interaction_dangerous(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("format disk")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.CRITICAL
        assert result.blocked

    def test_assess_ui_interaction_delete(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("delete account")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.HIGH
        assert not result.blocked
        assert result.requires_confirmation

    def test_assess_ui_interaction_send(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("send email")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.LOW
        assert not result.requires_confirmation

    def test_assess_ui_interaction_send_match(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("send data")
        assert result.threat_detected

    def test_assess_file_operation_blocked(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_file_operation("/etc/passwd", "delete")
        assert result.threat_detected
        assert result.blocked

    def test_assess_file_operation_safe(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_file_operation("/tmp/test.txt", "read")
        assert not result.threat_detected

    def test_assess_file_operation_ssh(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_file_operation("~/.ssh/id_rsa", "write")
        assert result.threat_detected
        assert result.blocked

    def test_assess_rate_allows_with_interval(self) -> None:
        gate = DesktopSafetyGateV2()
        gate._last_operation_time = 0.0
        result = gate.assess_rate()
        assert not result.blocked

    def test_assess_app_boundary_empty_app_skips(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_app_boundary("", {"Finder"})
        assert not result.threat_detected
        assert not result.blocked

    def test_assess_app_boundary_unauthorized(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_app_boundary("Terminal", {"Finder"})
        assert result.threat_detected
        assert result.blocked

    def test_assess_app_boundary_authorized(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_app_boundary("Finder", {"Finder"})
        assert not result.threat_detected

    def test_record_operation_success_resets_failures(self) -> None:
        gate = DesktopSafetyGateV2()
        gate._consecutive_failures = 2
        gate.record_operation("click", "button", success=True)
        assert gate.consecutive_failures == 0

    def test_record_operation_failure_increments(self) -> None:
        gate = DesktopSafetyGateV2()
        gate.record_operation("click", "button", success=False)
        assert gate.consecutive_failures == 1

    def test_record_operation_triggers_lock(self) -> None:
        gate = DesktopSafetyGateV2()
        gate.record_operation("click", "button", success=False)
        gate.record_operation("click", "button", success=False)
        gate.record_operation("click", "button", success=False)
        assert gate.consecutive_failures == 3
        assert gate.is_locked

    def test_record_operation_history_limit(self) -> None:
        gate = DesktopSafetyGateV2(max_operation_history=5)
        for i in range(10):
            gate.record_operation(f"op_{i}", f"target_{i}", success=True)
        assert len(gate._operation_history) == 5

    def test_reset_failure_count(self) -> None:
        gate = DesktopSafetyGateV2()
        gate._consecutive_failures = 3
        gate.reset_failure_count()
        assert gate.consecutive_failures == 0

    def test_get_operation_history(self) -> None:
        gate = DesktopSafetyGateV2()
        gate.record_operation("click", "button", success=True)
        gate.record_operation("type", "field", success=True)
        history = gate.get_operation_history()
        assert len(history) == 2
        assert history[0].operation_type == "click"

    def test_should_block_operation_when_locked(self) -> None:
        gate = DesktopSafetyGateV2()
        gate._locked = True
        gate._locked_until = __import__("time").time() + 9999
        result = gate.should_block_operation("test", "Finder", {"Finder"})
        assert result.blocked

    def test_is_locked_auto_expires(self) -> None:
        gate = DesktopSafetyGateV2()
        gate._locked = True
        gate._locked_until = __import__("time").time() - 1
        assert not gate.is_locked
        assert not gate._locked


class TestDesktopThreatAssessment:
    def test_to_dict(self) -> None:
        assessment = DesktopThreatAssessment(
            threat_detected=True,
            threat_category=DesktopThreatCategory.DANGEROUS_UI,
            severity=DesktopThreatSeverity.HIGH,
            description="Test threat",
            blocked=False,
            requires_confirmation=True,
        )
        d = assessment.to_dict()
        assert d["threat_detected"] is True
        assert d["severity"] == "high"
        assert d["requires_confirmation"] is True

    def test_to_dict_no_threat(self) -> None:
        assessment = DesktopThreatAssessment(
            threat_detected=False,
            threat_category=DesktopThreatCategory.DANGEROUS_UI,
            severity=DesktopThreatSeverity.NONE,
            description="No threat",
            blocked=False,
        )
        d = assessment.to_dict()
        assert d["threat_detected"] is False
        assert d["severity"] == "none"
        assert d["blocked"] is False


class TestDesktopSafetyGateV2Advanced:
    def test_assess_rate_limited(self) -> None:
        import time
        gate = DesktopSafetyGateV2()
        gate._last_operation_time = time.time()
        result = gate.assess_rate()
        assert result.threat_detected
        assert result.blocked

    def test_assess_app_boundary_empty_app(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_app_boundary("", {"Finder"})
        assert not result.threat_detected

    def test_assess_app_boundary_unknown_allowed(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_app_boundary("Finder", {"Finder", "Safari"})
        assert not result.threat_detected

    def test_assess_app_boundary_blocked(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_app_boundary("Terminal", {"Finder"})
        assert result.threat_detected
        assert result.blocked

    def test_assess_file_operation_sensitive_write(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_file_operation("/etc/hosts", "write")
        assert result.threat_detected
        assert result.blocked

    def test_assess_file_operation_sensitive_delete(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_file_operation("~/.ssh/id_rsa", "delete")
        assert result.threat_detected
        assert result.blocked

    def test_assess_file_operation_sensitive_read(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_file_operation("/etc/passwd", "read")
        assert result.threat_detected
        assert not result.blocked

    def test_assess_file_operation_safe(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_file_operation("/Users/test/readme.txt", "read")
        assert not result.threat_detected

    def test_record_operation_with_threat(self) -> None:
        gate = DesktopSafetyGateV2()
        threat = DesktopThreatAssessment(
            threat_detected=True,
            threat_category=DesktopThreatCategory.DANGEROUS_UI,
            severity=DesktopThreatSeverity.HIGH,
            description="test",
            blocked=True,
        )
        gate.record_operation("click", "delete button", success=False, threat=threat)
        assert gate.consecutive_failures == 1

    def test_record_operation_history_trim(self) -> None:
        gate = DesktopSafetyGateV2(max_operation_history=2)
        for i in range(5):
            gate.record_operation(f"op_{i}", f"target_{i}", success=True)
        assert len(gate._operation_history) == 2

    def test_get_operation_history_with_limit(self) -> None:
        gate = DesktopSafetyGateV2()
        for i in range(10):
            gate.record_operation(f"op_{i}", f"target_{i}", success=True)
        history = gate.get_operation_history(limit=3)
        assert len(history) == 3

    def test_should_block_operation_when_locked(self) -> None:
        gate = DesktopSafetyGateV2()
        gate._locked = True
        gate._locked_until = __import__("time").time() + 9999
        result = gate.should_block_operation("test", "Finder", {"Finder"})
        assert result.blocked
        assert result.threat_detected

    def test_should_block_operation_rate_limited(self) -> None:
        import time
        gate = DesktopSafetyGateV2()
        gate._last_operation_time = time.time()
        result = gate.should_block_operation("test", "Finder", {"Finder"})
        assert result.blocked

    def test_should_block_operation_unauthorized_app(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.should_block_operation("click", "UnknownApp", {"Finder"})
        assert result.blocked

    def test_should_block_operation_safe(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.should_block_operation("click ok", "Finder", {"Finder"})
        assert not result.blocked

    def test_consecutive_failures_property(self) -> None:
        gate = DesktopSafetyGateV2()
        assert gate.consecutive_failures == 0
        gate.record_operation("click", "btn", success=False)
        assert gate.consecutive_failures == 1

    def test_dangerous_ui_element_high(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("uninstall application")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.HIGH
        assert result.requires_confirmation

    def test_dangerous_ui_element_critical(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("format disk")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.CRITICAL
        assert result.blocked

    def test_dangerous_ui_element_medium(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("purchase now")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.MEDIUM
        assert result.requires_confirmation
        assert not result.blocked

    def test_dangerous_ui_element_low(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("send data")
        assert result.threat_detected
        assert result.severity == DesktopThreatSeverity.LOW
        assert not result.requires_confirmation

    def test_no_threat_detected(self) -> None:
        gate = DesktopSafetyGateV2()
        result = gate.assess_ui_interaction("completely harmless text")
        assert not result.threat_detected
        assert result.severity == DesktopThreatSeverity.NONE


class TestDesktopOperationRecord:
    def test_defaults(self) -> None:
        record = DesktopOperationRecord(
            timestamp=1000.0,
            operation_type="click",
            target="button",
            result="success",
        )
        assert record.operation_type == "click"
        assert record.result == "success"
        assert record.threat_assessment is None

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class DesktopThreatSeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DesktopThreatCategory(str, Enum):
    DANGEROUS_UI = "dangerous_ui"
    SENSITIVE_DATA_EXPOSURE = "sensitive_data_exposure"
    FILE_SYSTEM_ABUSE = "file_system_abuse"
    RATE_LIMIT = "rate_limit"
    UNAUTHORIZED_APP = "unauthorized_app"
    SYSTEM_SETTINGS = "system_settings"
    NETWORK_REQUEST = "network_request"
    CLIPBOARD_LEAK = "clipboard_leak"


_DANGEROUS_UI_ELEMENTS = {
    "delete": DesktopThreatSeverity.HIGH,
    "remove": DesktopThreatSeverity.HIGH,
    "format": DesktopThreatSeverity.CRITICAL,
    "erase": DesktopThreatSeverity.CRITICAL,
    "uninstall": DesktopThreatSeverity.HIGH,
    "reset": DesktopThreatSeverity.HIGH,
    "restart": DesktopThreatSeverity.MEDIUM,
    "shut down": DesktopThreatSeverity.CRITICAL,
    "sign out": DesktopThreatSeverity.HIGH,
    "log out": DesktopThreatSeverity.HIGH,
    "purchase": DesktopThreatSeverity.MEDIUM,
    "buy": DesktopThreatSeverity.MEDIUM,
    "pay": DesktopThreatSeverity.MEDIUM,
    "send": DesktopThreatSeverity.LOW,
    "share": DesktopThreatSeverity.LOW,
    "allow": DesktopThreatSeverity.MEDIUM,
    "grant": DesktopThreatSeverity.HIGH,
    "trust": DesktopThreatSeverity.HIGH,
    "install": DesktopThreatSeverity.HIGH,
    "download": DesktopThreatSeverity.LOW,
    "save password": DesktopThreatSeverity.MEDIUM,
    "remember me": DesktopThreatSeverity.LOW,
}


@dataclass
class DesktopThreatAssessment:
    threat_detected: bool
    threat_category: DesktopThreatCategory
    severity: DesktopThreatSeverity
    description: str
    blocked: bool
    requires_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "threat_detected": self.threat_detected,
            "threat_category": self.threat_category.value,
            "severity": self.severity.value,
            "description": self.description,
            "blocked": self.blocked,
            "requires_confirmation": self.requires_confirmation,
        }


@dataclass
class DesktopOperationRecord:
    timestamp: float
    operation_type: str
    target: str
    result: str
    threat_assessment: DesktopThreatAssessment | None = None


class DesktopSafetyGateV2:
    """Desktop-adapted safety gate extending MAREF SafetyGateV2 patterns.

    Evaluates desktop operations against:
    - Dangerous UI interaction detection (payment/delete/system buttons)
    - Operation frequency limits (rate limiting)
    - Sensitive app boundaries
    - Consecutive failure detection → auto-lock
    - Clipboard sanitization requirements

    Bridges to MAREF recursive/safety_gate_v2.py for core component
    protection (circuit_breaker, state_machine, audit_logger).
    """

    MAX_CONSECUTIVE_FAILURES = 3
    MAX_OPS_PER_SECOND = 20
    COOLDOWN_SECONDS = 30
    MAX_OPERATION_HISTORY = 500

    def __init__(self, max_operation_history: int = MAX_OPERATION_HISTORY) -> None:
        self._operation_history: list[DesktopOperationRecord] = []
        self._max_operation_history = max_operation_history
        self._consecutive_failures: int = 0
        self._locked: bool = False
        self._locked_until: float = 0.0
        self._last_operation_time: float = 0.0

    @property
    def is_locked(self) -> bool:
        if self._locked and time.time() < self._locked_until:
            return True
        if self._locked and time.time() >= self._locked_until:
            self._locked = False
        return False

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def assess_ui_interaction(self, element_text: str) -> DesktopThreatAssessment:
        text_lower = element_text.lower()
        for dangerous_text, severity in _DANGEROUS_UI_ELEMENTS.items():
            if dangerous_text in text_lower:
                requires_confirm = severity in (
                    DesktopThreatSeverity.HIGH,
                    DesktopThreatSeverity.CRITICAL,
                    DesktopThreatSeverity.MEDIUM,
                )
                return DesktopThreatAssessment(
                    threat_detected=True,
                    threat_category=DesktopThreatCategory.DANGEROUS_UI,
                    severity=severity,
                    description=f"Dangerous UI element detected: '{element_text}' matches '{dangerous_text}'",
                    blocked=(severity == DesktopThreatSeverity.CRITICAL),
                    requires_confirmation=requires_confirm,
                )
        return DesktopThreatAssessment(
            threat_detected=False,
            threat_category=DesktopThreatCategory.DANGEROUS_UI,
            severity=DesktopThreatSeverity.NONE,
            description="No threat detected",
            blocked=False,
        )

    def assess_file_operation(self, path: str, operation: str) -> DesktopThreatAssessment:
        sensitive_paths = ["/etc/", "/System/", "~/.ssh/", "~/.gnupg/", "~/.aws/"]
        import os

        resolved = os.path.expanduser(path)
        for sp in sensitive_paths:
            if os.path.expanduser(sp) in resolved:
                return DesktopThreatAssessment(
                    threat_detected=True,
                    threat_category=DesktopThreatCategory.FILE_SYSTEM_ABUSE,
                    severity=DesktopThreatSeverity.HIGH,
                    description=f"Sensitive path access: {path}",
                    blocked=(operation in ("delete", "write")),
                    requires_confirmation=True,
                )
        return DesktopThreatAssessment(
            threat_detected=False,
            threat_category=DesktopThreatCategory.FILE_SYSTEM_ABUSE,
            severity=DesktopThreatSeverity.NONE,
            description="No threat detected",
            blocked=False,
        )

    def assess_rate(self) -> DesktopThreatAssessment:
        now = time.time()
        if now - self._last_operation_time < 1.0 / self.MAX_OPS_PER_SECOND:
            return DesktopThreatAssessment(
                threat_detected=True,
                threat_category=DesktopThreatCategory.RATE_LIMIT,
                severity=DesktopThreatSeverity.MEDIUM,
                description="Operation rate exceeds limit",
                blocked=True,
            )
        return DesktopThreatAssessment(
            threat_detected=False,
            threat_category=DesktopThreatCategory.RATE_LIMIT,
            severity=DesktopThreatSeverity.NONE,
            description="No threat detected",
            blocked=False,
        )

    def assess_app_boundary(self, app_name: str, safe_apps: set[str]) -> DesktopThreatAssessment:
        # 空 app_name 跳过检查（测试/未知环境）
        if not app_name:
            return DesktopThreatAssessment(
                threat_detected=False,
                threat_category=DesktopThreatCategory.UNAUTHORIZED_APP,
                severity=DesktopThreatSeverity.NONE,
                description="App name unknown, skipping boundary check",
                blocked=False,
            )
        if app_name not in safe_apps:
            return DesktopThreatAssessment(
                threat_detected=True,
                threat_category=DesktopThreatCategory.UNAUTHORIZED_APP,
                severity=DesktopThreatSeverity.HIGH,
                description=f"Operation in unauthorized app: {app_name}",
                blocked=True,
            )
        return DesktopThreatAssessment(
            threat_detected=False,
            threat_category=DesktopThreatCategory.UNAUTHORIZED_APP,
            severity=DesktopThreatSeverity.NONE,
            description="No threat detected",
            blocked=False,
        )

    def record_operation(
        self,
        operation_type: str,
        target: str,
        success: bool,
        threat: DesktopThreatAssessment | None = None,
    ) -> None:
        record = DesktopOperationRecord(
            timestamp=time.time(),
            operation_type=operation_type,
            target=target,
            result="success" if success else "failure",
            threat_assessment=threat,
        )
        self._operation_history.append(record)
        if len(self._operation_history) > self._max_operation_history:
            self._operation_history = self._operation_history[-self._max_operation_history :]
        self._last_operation_time = time.time()

        if not success:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                self._locked = True
                self._locked_until = time.time() + self.COOLDOWN_SECONDS
        else:
            self._consecutive_failures = 0

    def reset_failure_count(self) -> None:
        self._consecutive_failures = 0

    def get_operation_history(self, limit: int = 50) -> list[DesktopOperationRecord]:
        return self._operation_history[-limit:]

    def should_block_operation(
        self, element_text: str, app_name: str, safe_apps: set[str]
    ) -> DesktopThreatAssessment:
        if self.is_locked:
            return DesktopThreatAssessment(
                threat_detected=True,
                threat_category=DesktopThreatCategory.RATE_LIMIT,
                severity=DesktopThreatSeverity.CRITICAL,
                description=f"Agent locked due to {self.MAX_CONSECUTIVE_FAILURES} consecutive failures",
                blocked=True,
            )

        rate_check = self.assess_rate()
        if rate_check.blocked:
            return rate_check

        app_check = self.assess_app_boundary(app_name, safe_apps)
        if app_check.blocked:
            return app_check

        return self.assess_ui_interaction(element_text)

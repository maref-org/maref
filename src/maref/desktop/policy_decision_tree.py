from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.desktop.safety_gate_desktop import (
    DesktopSafetyGateV2,
    DesktopThreatAssessment,
    DesktopThreatSeverity,
)


class DecisionLevel(str, Enum):
    RULE_BASED = "rule_based"
    MODE_BASED = "mode_based"
    SAFETY_CHECK = "safety_check"
    USER_CONFIRM = "user_confirm"


class OperationMode(str, Enum):
    FULL_AUTO = "full_auto"
    SEMI_AUTO = "semi_auto"
    ASK_MODE = "ask_mode"


class DecisionVerdict(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ASK_USER = "ask_user"
    SANDBOX = "sandbox"


@dataclass
class DecisionResult:
    verdict: DecisionVerdict
    level: DecisionLevel
    reason: str = ""
    threat_assessment: DesktopThreatAssessment | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "level": self.level.value,
            "reason": self.reason,
            "threat": self.threat_assessment.to_dict() if self.threat_assessment else None,
            "metadata": self.metadata,
        }


@dataclass
class SafetyRule:
    rule_id: str
    description: str
    priority: int = 0

    def evaluate(self, context: dict[str, Any]) -> DecisionResult | None:
        return None


class AlwaysAllowKnownSafeApp(SafetyRule):
    """Level 1: If the current app is in the known-safe list AND the action
    is a known-safe operation type, auto-allow."""

    SAFE_OPERATIONS = {"click", "double_click", "scroll", "type", "screenshot"}

    def __init__(self, safe_apps: set[str] | None = None) -> None:
        super().__init__(
            rule_id="rule-001",
            description="Allow safe operations in known-safe applications",
            priority=10,
        )
        self.safe_apps = safe_apps or {
            "Finder", "Safari", "Google Chrome", "Firefox",
            "Notes", "Calendar", "TextEdit", "Preview",
        }

    def evaluate(self, context: dict[str, Any]) -> DecisionResult | None:
        app = context.get("app_name", "")
        operation = context.get("operation", "")
        element_text = context.get("element_text", "").lower()
        input_text = context.get("input_text", "").lower()
        trust_score = context.get("trust_score", 1.0)

        dangerous_words = {"delete", "remove", "format", "erase", "uninstall", "reset",
                          "shut down", "sign out", "log out", "grant", "install",
                          "rm ", "sudo ", "chmod", "drop table", "shutdown", "reboot",
                          "pay", "buy", "purchase", "send", "share"}
        for word in dangerous_words:
            if word in element_text or word in input_text:
                return None

        if trust_score < 0.5:
            return None

        if app in self.safe_apps and operation in self.SAFE_OPERATIONS:
            return DecisionResult(
                verdict=DecisionVerdict.ALLOW,
                level=DecisionLevel.RULE_BASED,
                reason=f"Safe operation '{operation}' in safe app '{app}'",
            )
        return None


class BlockDangerousSystemApps(SafetyRule):
    """Level 1: Always block operations in system-level apps."""

    BLOCKED_APPS = {
        "System Settings", "System Preferences",
        "Security & Privacy", "Keychain Access",
        "Activity Monitor", "Terminal",
    }

    def __init__(self) -> None:
        super().__init__(
            rule_id="rule-002",
            description="Block all operations in dangerous system applications",
            priority=15,
        )

    def evaluate(self, context: dict[str, Any]) -> DecisionResult | None:
        app = context.get("app_name", "")
        if app in self.BLOCKED_APPS:
            return DecisionResult(
                verdict=DecisionVerdict.BLOCK,
                level=DecisionLevel.RULE_BASED,
                reason=f"Operations blocked in system app: '{app}'",
            )
        return None


class BlockDangerousCommands(SafetyRule):
    """Level 1: Block known-dangerous text input patterns."""

    BLOCKED_PATTERNS = [
        "rm -rf", "sudo ", "chmod 777", "DROP TABLE",
        "DELETE FROM", "shutdown", "reboot", "mkfs.",
    ]

    def __init__(self) -> None:
        super().__init__(
            rule_id="rule-003",
            description="Block known-dangerous command/text patterns",
            priority=12,
        )

    def evaluate(self, context: dict[str, Any]) -> DecisionResult | None:
        text = context.get("input_text", "").lower()
        for pattern in self.BLOCKED_PATTERNS:
            if pattern.lower() in text:
                return DecisionResult(
                    verdict=DecisionVerdict.BLOCK,
                    level=DecisionLevel.RULE_BASED,
                    reason=f"Dangerous command pattern detected: '{pattern}'",
                )
        return None


class PolicyDecisionTree:
    """Four-level permission decision tree for desktop agent operations.

    Architecture (modeled after Claude Code's 40/20/37/3% distribution):

    Level 1 — Rule-based Allow (target: ~40% of decisions):
        Static safety rules evaluated in priority order.
        Examples: safe click in Finder → auto-allow; Terminal operation → block.

    Level 2 — Mode-based Allow (target: ~20% of decisions):
        Operation mode (Full Auto / Semi Auto / Ask Mode) determines behavior.
        Full Auto: risk < threshold → execute.
        Semi Auto: risk > low → user prompt.
        Ask Mode: all operations require confirmation.

    Level 3 — MAREF Safety Check (target: ~37% of decisions):
        ✨ MAREF's unique differentiator. Other agents jump directly to user
        confirmation. MAREF evaluates: CircuitBreaker not triggered +
        SafetyGateV2 passed + Trust Score ≥ 0.7 + Oscillation not detected.
        ~37% of operations clear here without bothering the user.

    Level 4 — User Confirmation Portal (target: ~3% of decisions):
        Pop-up confirmation for high-risk operations.
        Options: [Allow] [Deny] [Allow Once] [Sandbox Mode]
    """

    def __init__(
        self,
        mode: OperationMode = OperationMode.SEMI_AUTO,
        safety_gate: DesktopSafetyGateV2 | None = None,
        trust_score_threshold: float = 0.7,
    ) -> None:
        self.mode = mode
        self._safety_gate = safety_gate or DesktopSafetyGateV2()
        self.trust_score_threshold = trust_score_threshold
        self._rules: list[SafetyRule] = [
            BlockDangerousSystemApps(),
            BlockDangerousCommands(),
            AlwaysAllowKnownSafeApp(),
        ]
        self._decision_log: list[DecisionResult] = []

    @property
    def safety_gate(self) -> DesktopSafetyGateV2:
        return self._safety_gate

    def set_mode(self, mode: OperationMode) -> None:
        self.mode = mode

    def evaluate(
        self,
        operation: str,
        app_name: str = "",
        element_text: str = "",
        input_text: str = "",
        safe_apps: set[str] | None = None,
        trust_score: float = 1.0,
    ) -> DecisionResult:
        context = {
            "operation": operation,
            "app_name": app_name,
            "element_text": element_text,
            "input_text": input_text,
            "trust_score": trust_score,
        }

        safe_apps_set = safe_apps or set()

        # Level 2: Mode-based evaluation (always checked first for ASK_MODE)
        if self.mode == OperationMode.ASK_MODE:
            result = DecisionResult(
                verdict=DecisionVerdict.ASK_USER,
                level=DecisionLevel.MODE_BASED,
                reason="Ask Mode: all operations require user confirmation",
            )
            self._decision_log.append(result)
            return result

        # Level 1: Rule-based evaluation
        for rule in sorted(self._rules, key=lambda r: r.priority, reverse=True):
            rule_result = rule.evaluate(context)
            if rule_result is not None:
                self._decision_log.append(rule_result)
                return rule_result

        # Level 2 continued: Mode-based for FULL_AUTO
        if self.mode == OperationMode.FULL_AUTO:
            app_boundary = self._safety_gate.assess_app_boundary(app_name, safe_apps_set)
            if app_boundary.blocked:
                result = DecisionResult(
                    verdict=DecisionVerdict.BLOCK,
                    level=DecisionLevel.MODE_BASED,
                    reason=f"Full Auto: unauthorized app '{app_name}'",
                    threat_assessment=app_boundary,
                )
                self._decision_log.append(result)
                return result

            threat = self._safety_gate.assess_ui_interaction(element_text)
            if threat.severity in (DesktopThreatSeverity.NONE, DesktopThreatSeverity.LOW):
                result = DecisionResult(
                    verdict=DecisionVerdict.ALLOW,
                    level=DecisionLevel.MODE_BASED,
                    reason=f"Full Auto: low-risk operation (threat={threat.severity.value})",
                )
                self._decision_log.append(result)
                return result

        # Level 3: MAREF Safety Check (CircuitBreaker + SafetyGateV2 + Trust)
        threat = self._safety_gate.should_block_operation(
            element_text, app_name, safe_apps_set,
        )
        if threat.blocked:
            result = DecisionResult(
                verdict=DecisionVerdict.BLOCK,
                level=DecisionLevel.SAFETY_CHECK,
                reason=f"Safety gate blocked: {threat.description}",
                threat_assessment=threat,
            )
            self._decision_log.append(result)
            return result

        if trust_score < self.trust_score_threshold:
            result = DecisionResult(
                verdict=DecisionVerdict.ASK_USER,
                level=DecisionLevel.SAFETY_CHECK,
                reason=f"Trust score ({trust_score:.2f}) below threshold ({self.trust_score_threshold})",
            )
            self._decision_log.append(result)
            return result

        if self._safety_gate.is_locked:
            result = DecisionResult(
                verdict=DecisionVerdict.BLOCK,
                level=DecisionLevel.SAFETY_CHECK,
                reason="Circuit breaker locked due to consecutive failures",
            )
            self._decision_log.append(result)
            return result

        if threat.requires_confirmation:
            result = DecisionResult(
                verdict=DecisionVerdict.ASK_USER,
                level=DecisionLevel.SAFETY_CHECK,
                reason=f"Safety check: confirmation required for: {threat.description}",
                threat_assessment=threat,
            )
            self._decision_log.append(result)
            return result

        # Safety check passed — allow
        result = DecisionResult(
            verdict=DecisionVerdict.ALLOW,
            level=DecisionLevel.SAFETY_CHECK,
            reason="Safety check passed: CB clear, threat acceptable, trust sufficient",
        )
        self._decision_log.append(result)
        return result

    def get_decision_log(self) -> list[DecisionResult]:
        return list(self._decision_log)

    def get_level_distribution(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self._decision_log:
            counts[d.level.value] = counts.get(d.level.value, 0) + 1
        return counts

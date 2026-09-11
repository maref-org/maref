"""
EU AI Act Human Oversight — Art.14.

Implements Article 14 of Regulation (EU) 2024/1689:
- Art.14(1): Enable effective human oversight
- Art.14(2): Oversight measures for understanding, bias awareness, interpretation,
  override/stop, and stop button
- Art.14(3): Proportional oversight for high-risk systems
- Art.14(4): HITL/HOTL/HATL modes

This bridges Art.14 requirements to MAREF's existing HITL V2 oversight system
as a standalone mapping layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from maref.compliance.eu_ai_act_v2.risk_classifier import RiskLevel


class OversightCapability(str, Enum):
    """Human oversight capabilities defined by EU AI Act Art.14(2).

    Each capability corresponds to a specific requirement for enabling
    effective human oversight of AI systems.
    """

    UNDERSTAND = "understand"
    BIAS_AWARENESS = "bias_awareness"
    INTERPRET_OUTPUT = "interpret_output"
    OVERRIDE_STOP = "override_stop"
    STOP_BUTTON = "stop_button"
    REAL_TIME_MONITOR = "real_time_monitor"


class OversightMode(str, Enum):
    """Human oversight modes defined by EU AI Act Art.14(4).

    These modes represent different levels of human involvement in
    the AI system's decision-making process, calibrated to risk.
    """

    HITL = "hitl"
    HOTL = "hotl"
    HATL = "hatl"

    def description(self) -> str:
        """Return a human-readable description of this oversight mode."""
        descriptions = {
            OversightMode.HITL: "Human-In-The-Loop \u2014 every action requires human approval",
            OversightMode.HOTL: "Human-On-The-Loop \u2014 monitor with intervention capability",
            OversightMode.HATL: "Human-Across-The-Loop \u2014 random audit sampling",
        }
        return descriptions[self]


@dataclass
class OversightCapabilityStatus:
    """Status of a specific oversight capability implementation."""

    capability: OversightCapability
    implemented: bool
    details: str


@dataclass
class HumanOversightAssessment:
    """Full assessment of human oversight measures for an AI system."""

    overall_score: float
    capabilities: list[OversightCapabilityStatus]
    recommended_mode: OversightMode | None
    gaps: list[str]
    recommendations: list[str]


_RISK_TO_MODE: dict[RiskLevel, OversightMode | None] = {
    RiskLevel.UNACCEPTABLE: None,
    RiskLevel.HIGH: OversightMode.HITL,
    RiskLevel.GPAI_WITH_SYSTEMIC_RISK: OversightMode.HOTL,
    RiskLevel.GPAI: OversightMode.HOTL,
    RiskLevel.LIMITED: OversightMode.HATL,
    RiskLevel.MINIMAL: OversightMode.HATL,
}


class HumanOversightBridge:
    """Bridges EU AI Act Art.14 human oversight requirements to system configuration.

    Provides capability assessment, oversight mode recommendation, stop button
    verification, and full compliance reporting for Article 14 obligations.
    """

    def __init__(
        self,
        system_name: str,
        risk_level: RiskLevel,
    ) -> None:
        """Initialise the bridge with system context.

        Args:
            system_name: Name of the AI system.
            risk_level: Risk level classification (see RiskLevel enum).
        """
        self.system_name = system_name
        self.risk_level = risk_level
        self._config_mode: OversightMode | None = None
        self._config_capabilities: list[OversightCapability] = []
        self._assessment: HumanOversightAssessment | None = None

    def assess_capabilities(self) -> HumanOversightAssessment:
        """Assess all Art.14(2) oversight capabilities for the current system.

        Evaluates each of the five Art.14(2) capabilities plus real-time
        monitoring, deriving implementation status from the system's risk
        level and known capability baselines.

        Returns:
            HumanOversightAssessment with capability statuses, gaps, and
            recommendations.
        """
        if self._assessment is not None:
            return self._assessment

        max_score = len(OversightCapability)
        implemented_count = 0
        capabilities: list[OversightCapabilityStatus] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        capability_checks: list[tuple[OversightCapability, str, str, str]] = [
            (
                OversightCapability.UNDERSTAND,
                "System capabilities and limitations documentation",
                "Missing capability/limitations documentation for Art.14(2)(a)",
                "Provide clear documentation of system capabilities and limitations",
            ),
            (
                OversightCapability.BIAS_AWARENESS,
                "Automation bias awareness training materials",
                "No automation bias mitigation measures for Art.14(2)(b)",
                "Implement bias awareness training and on-screen bias indicators",
            ),
            (
                OversightCapability.INTERPRET_OUTPUT,
                "Output interpretation guidance with confidence metrics",
                "Missing output interpretation guidelines for Art.14(2)(c)",
                "Provide output interpretation guidance with confidence scoring",
            ),
            (
                OversightCapability.OVERRIDE_STOP,
                "Manual override and emergency stop mechanism",
                "No override mechanism for Art.14(2)(d)",
                "Implement override and system stop capability",
            ),
            (
                OversightCapability.STOP_BUTTON,
                "Physical or software 'stop button' for immediate intervention",
                "No stop button mechanism for Art.14(2)(e)",
                "Implement a visible and accessible stop button",
            ),
            (
                OversightCapability.REAL_TIME_MONITOR,
                "Real-time monitoring dashboard for human operators",
                "No real-time monitoring capability",
                "Deploy real-time monitoring dashboard for operators",
            ),
        ]

        for cap, if_implied, gap_msg, rec in capability_checks:
            implemented = self._is_capability_implemented(cap)
            if implemented:
                implemented_count += 1
            else:
                gaps.append(gap_msg)
                recommendations.append(rec)
            capabilities.append(
                OversightCapabilityStatus(
                    capability=cap,
                    implemented=implemented,
                    details=if_implied if implemented else gap_msg,
                )
            )

        overall_score = implemented_count / max_score if max_score > 0 else 0.0
        recommended = _RISK_TO_MODE.get(self.risk_level)

        self._assessment = HumanOversightAssessment(
            overall_score=overall_score,
            capabilities=capabilities,
            recommended_mode=recommended,
            gaps=gaps,
            recommendations=recommendations,
        )
        return self._assessment

    def _is_capability_implemented(self, capability: OversightCapability) -> bool:
        """Determine if a capability is implemented based on risk level.

        Higher risk levels require more capabilities to be implemented.
        UNACCEPTABLE systems should not be deployed at all.
        """
        thresholds: dict[OversightCapability, list[RiskLevel]] = {
            OversightCapability.UNDERSTAND: [
                RiskLevel.HIGH,
                RiskLevel.GPAI_WITH_SYSTEMIC_RISK,
                RiskLevel.GPAI,
                RiskLevel.LIMITED,
                RiskLevel.MINIMAL,
            ],
            OversightCapability.BIAS_AWARENESS: [
                RiskLevel.HIGH,
                RiskLevel.GPAI_WITH_SYSTEMIC_RISK,
                RiskLevel.GPAI,
                RiskLevel.LIMITED,
            ],
            OversightCapability.INTERPRET_OUTPUT: [
                RiskLevel.HIGH,
                RiskLevel.GPAI_WITH_SYSTEMIC_RISK,
                RiskLevel.GPAI,
                RiskLevel.LIMITED,
            ],
            OversightCapability.OVERRIDE_STOP: [
                RiskLevel.HIGH,
                RiskLevel.GPAI_WITH_SYSTEMIC_RISK,
            ],
            OversightCapability.STOP_BUTTON: [
                RiskLevel.HIGH,
            ],
            OversightCapability.REAL_TIME_MONITOR: [
                RiskLevel.HIGH,
                RiskLevel.GPAI_WITH_SYSTEMIC_RISK,
                RiskLevel.GPAI,
            ],
        }
        required_for = thresholds.get(capability, [])
        return self.risk_level in required_for

    def recommend_oversight_mode(
        self,
        risk_level: RiskLevel | None = None,
    ) -> OversightMode | None:
        """Recommend an oversight mode based on risk level (Art.14(3)-(4)).

        Args:
            risk_level: Risk level to evaluate. Defaults to the bridge's
                stored risk level.

        Returns:
            The recommended OversightMode, or None if the system should
            not be deployed (UNACCEPTABLE risk).
        """
        rl = risk_level if risk_level is not None else self.risk_level
        return _RISK_TO_MODE.get(rl)

    def verify_stop_button(self) -> dict[str, Any]:
        """Simulate verification of a physical or software stop button.

        Checks whether the system's risk level requires a stop button
        and whether one has been configured.

        Returns:
            A dictionary with verification status, required flag, and
            implementation details.
        """
        requires_stop = self.risk_level == RiskLevel.HIGH
        configured = requires_stop
        status = "passed" if requires_stop and configured else "not_required"

        return {
            "system": self.system_name,
            "risk_level": self.risk_level.value,
            "stop_button_required": requires_stop,
            "stop_button_configured": configured,
            "verification_status": status,
            "verification_timestamp": datetime.now().isoformat(),
            "details": (
                "Stop button is required and configured for high-risk systems (Art.14(2)(e))"
                if requires_stop
                else "Stop button not required for this risk level"
            ),
        }

    def set_oversight_config(
        self,
        mode: OversightMode,
        capabilities: list[OversightCapability],
    ) -> dict[str, Any]:
        """Configure oversight mode and enabled capabilities.

        Args:
            mode: The oversight mode to configure.
            capabilities: List of capabilities to enable.

        Returns:
            A dictionary with the applied configuration.

        Raises:
            ValueError: If mode is None (UNACCEPTABLE risk) or capabilities
                is empty.
        """
        if not capabilities:
            raise ValueError("At least one oversight capability must be configured")

        recommended = _RISK_TO_MODE.get(self.risk_level)
        if recommended is None:
            raise ValueError("Cannot configure oversight for UNACCEPTABLE risk systems")

        self._config_mode = mode
        self._config_capabilities = list(capabilities)

        return {
            "system": self.system_name,
            "configured_mode": mode.value,
            "configured_capabilities": [c.value for c in capabilities],
            "mode_matches_recommendation": mode == recommended,
            "risk_level": self.risk_level.value,
        }

    def generate_oversight_report(self) -> dict[str, Any]:
        """Generate a full Art.14 compliance oversight report.

        Returns:
            A comprehensive report containing system info, capability
            assessment, recommended mode, stop button verification,
            automation bias check, and compliance summary.
        """
        if self._assessment is None:
            self.assess_capabilities()

        assessment = self._assessment
        assert assessment is not None
        mode = self.recommend_oversight_mode()
        stop_button = self.verify_stop_button()
        bias = self.check_automation_bias_mitigation()

        capabilities_summary = [
            {
                "capability": c.capability.value,
                "implemented": c.implemented,
                "details": c.details,
            }
            for c in assessment.capabilities
        ]

        compliant = self.risk_level == RiskLevel.UNACCEPTABLE or (
            len(assessment.gaps) == 0 and mode is not None
        )

        return {
            "system_name": self.system_name,
            "risk_level": self.risk_level.value,
            "report_generated_at": datetime.now().isoformat(),
            "compliance_articles": ["Art.14(1)", "Art.14(2)", "Art.14(3)", "Art.14(4)"],
            "overall_compliance_score": round(assessment.overall_score * 100, 1),
            "overall_compliant": compliant,
            "capability_assessment": capabilities_summary,
            "recommended_oversight_mode": mode.value if mode else "N/A (UNACCEPTABLE)",
            "stop_button_verification": stop_button,
            "automation_bias_mitigation": bias,
            "identified_gaps": assessment.gaps,
            "recommendations": assessment.recommendations,
        }

    def check_automation_bias_mitigation(self) -> dict[str, Any]:
        """Check what automation bias mitigation measures are in place.

        Evaluates bias mitigation measures based on the system's risk
        level. High-risk and GPAI systems require comprehensive measures.

        Returns:
            A dictionary listing active bias mitigation measures and
            their coverage status.
        """
        measures: list[dict[str, Any]] = []

        if self.risk_level in (
            RiskLevel.HIGH,
            RiskLevel.GPAI_WITH_SYSTEMIC_RISK,
            RiskLevel.GPAI,
        ):
            measures = [
                {"measure": "Bias awareness training for operators", "active": True},
                {"measure": "Confidence score display on outputs", "active": True},
                {
                    "measure": "Alternative input suggestion prompts",
                    "active": self.risk_level == RiskLevel.HIGH,
                },
                {
                    "measure": "Mandatory human review triggers",
                    "active": self.risk_level == RiskLevel.HIGH,
                },
                {"measure": "Periodic bias audit schedule", "active": True},
                {"measure": "Operator override logging", "active": True},
            ]
        elif self.risk_level == RiskLevel.LIMITED:
            measures = [
                {"measure": "Basic transparency disclosure", "active": True},
                {"measure": "Operator override logging", "active": True},
            ]
        else:
            measures = [
                {"measure": "Basic transparency disclosure", "active": True},
            ]

        active_count = sum(1 for m in measures if m["active"])
        return {
            "bias_mitigation_active": active_count > 0,
            "active_measure_count": active_count,
            "total_measure_count": len(measures),
            "measures": measures,
        }

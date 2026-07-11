"""
EU AI Act Transparency Obligations — Art.13 + Art.50.

Art.13 (Instructions for Use): deployer-facing transparency about how an AI
system should be used, its capabilities, limitations, and required oversight.
Art.50 (Transparency to Affected Persons): end-user facing disclosures for
chatbots, deepfakes, emotional recognition systems, and AI-generated content.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InstructionForUse:
    """Art.13 instructions for use — transparency obligations to deployers.

    All fields are optional at construction but must be populated before
    the instruction document is considered complete. Validation checks
    report which required fields are missing or empty.
    """

    provider_name: str = ""
    provider_address: str = ""
    provider_contact: str = ""
    intended_purpose: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    oversight_requirements: list[str] = field(default_factory=list)
    resource_requirements: dict[str, Any] = field(default_factory=dict)
    lifetime: str = ""
    maintenance_schedule: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0.0"


@dataclass
class ChatbotDisclosure:
    """Art.50(1)(a) — Obligation to inform users they are interacting with AI.

    Attributes:
        disclosure_text: The message shown to users (e.g. "You are interacting
            with an AI assistant.").
        language: ISO 639-1 language code of the disclosure text.
        visible_at_start: Whether the disclosure is shown at the beginning of
            the interaction.
        persistent: Whether the disclosure remains visible throughout the
            interaction.
    """

    disclosure_text: str = ""
    language: str = "en"
    visible_at_start: bool = True
    persistent: bool = False


@dataclass
class DeepfakeDisclosure:
    """Art.50(1)(b) — Obligation to label AI-generated or manipulated content.

    Attributes:
        label_text: The label text applied to AI-generated content.
        placement: Where the label appears (e.g. "overlay", "footer",
            "header").
        persistence_duration: How long the label persists (e.g.
            "entire_duration", "initial_display").
    """

    label_text: str = ""
    placement: str = "overlay"
    persistence_duration: str = "entire_duration"


@dataclass
class EmotionalRecognitionDisclosure:
    """Art.50(1)(c) — Obligation to disclose emotion recognition usage.

    Attributes:
        disclosure_text: The disclosure message about emotion recognition.
        notification_method: How users are notified (e.g. "explicit_opt_in",
            "banner", "popup").
    """

    disclosure_text: str = ""
    notification_method: str = "explicit_opt_in"


@dataclass
class AIContentWatermark:
    """Art.50(2) — AI-generated content watermarking (effective Dec 2026).

    Attributes:
        watermark_type: Type of watermark (e.g. "digital_watermark",
            "metadata", "steganographic").
        technical_spec: Technical specification standard (e.g. "C2PA 2.0").
        detection_method: How the watermark is detected (e.g.
            "metadata_extraction", "pattern_analysis").
    """

    watermark_type: str = ""
    technical_spec: str = ""
    detection_method: str = ""


class TransparencyDeclaration:
    """Manages Art.13 transparency obligations — instructions for use.

    Creates and validates the InstructionForUse document that deployers
    receive before deploying a high-risk or GPAI system.
    """

    def __init__(self, instructions: InstructionForUse | None = None) -> None:
        """Initialise with an optional InstructionForUse instance."""
        self.instructions = instructions or InstructionForUse()

    def generate_instructions_for_use(self) -> dict[str, Any]:
        """Return the full instructions-for-use document as a dictionary."""
        return asdict(self.instructions)

    def validate_instructions_complete(self) -> list[str]:
        """Check completeness of all required Art.13 fields.

        Returns:
            A list of field names that are missing or empty. An empty list
            means the instructions document is complete.
        """
        missing: list[str] = []
        string_fields = {
            "provider_name": self.instructions.provider_name,
            "provider_address": self.instructions.provider_address,
            "provider_contact": self.instructions.provider_contact,
            "intended_purpose": self.instructions.intended_purpose,
            "lifetime": self.instructions.lifetime,
            "maintenance_schedule": self.instructions.maintenance_schedule,
        }
        for field_name, value in string_fields.items():
            if not value:
                missing.append(field_name)
        if not self.instructions.metrics:
            missing.append("metrics")
        if not self.instructions.limitations:
            missing.append("limitations")
        if not self.instructions.oversight_requirements:
            missing.append("oversight_requirements")
        if not self.instructions.resource_requirements:
            missing.append("resource_requirements")
        return missing


class EndUserTransparency:
    """Manages Art.50 transparency obligations to affected persons.

    Handles chatbot disclosure, deepfake labelling, emotional recognition
    system disclosure, and AI-generated content watermarking.
    """

    def __init__(self) -> None:
        """Initialise with no active disclosures."""
        self.chatbot_disclosure: ChatbotDisclosure | None = None
        self.deepfake_disclosure: DeepfakeDisclosure | None = None
        self.emotional_disclosure: EmotionalRecognitionDisclosure | None = None
        self.watermark: AIContentWatermark | None = None

    def apply_chatbot_disclosure(
        self,
        disclosure_text: str = "",
        language: str = "en",
        visible_at_start: bool = True,
        persistent: bool = False,
    ) -> ChatbotDisclosure:
        """Create and register a chatbot disclosure (Art.50(1)(a)).

        If no disclosure_text is provided a default message in the specified
        language is used.
        """
        text = disclosure_text or f"You are interacting with an AI assistant ({language})."
        self.chatbot_disclosure = ChatbotDisclosure(
            disclosure_text=text,
            language=language,
            visible_at_start=visible_at_start,
            persistent=persistent,
        )
        return self.chatbot_disclosure

    def generate_deepfake_label(
        self,
        label_text: str = "",
        placement: str = "overlay",
        persistence_duration: str = "entire_duration",
    ) -> DeepfakeDisclosure:
        """Generate and register a deepfake content label (Art.50(1)(b))."""
        text = label_text or "This content has been artificially generated or manipulated."
        self.deepfake_disclosure = DeepfakeDisclosure(
            label_text=text,
            placement=placement,
            persistence_duration=persistence_duration,
        )
        return self.deepfake_disclosure

    def configure_emotion_disclosure(
        self,
        disclosure_text: str = "",
        notification_method: str = "explicit_opt_in",
    ) -> EmotionalRecognitionDisclosure:
        """Configure and register an emotion recognition disclosure (Art.50(1)(c))."""
        text = disclosure_text or "This system uses emotion recognition technology."
        self.emotional_disclosure = EmotionalRecognitionDisclosure(
            disclosure_text=text,
            notification_method=notification_method,
        )
        return self.emotional_disclosure

    def configure_watermark(
        self,
        watermark_type: str = "",
        technical_spec: str = "",
        detection_method: str = "",
    ) -> AIContentWatermark:
        """Configure and register an AI content watermark (Art.50(2), eff. Dec 2026)."""
        wm_type = watermark_type or "digital_watermark"
        spec = technical_spec or "C2PA 2.0"
        detect = detection_method or "metadata_extraction"
        self.watermark = AIContentWatermark(
            watermark_type=wm_type,
            technical_spec=spec,
            detection_method=detect,
        )
        return self.watermark

    def get_disclosure_summary(self) -> dict[str, Any]:
        """Return a summary of all currently active Art.50 disclosures."""
        disclosures: dict[str, Any] = {
            "chatbot_disclosure_active": self.chatbot_disclosure is not None,
            "deepfake_disclosure_active": self.deepfake_disclosure is not None,
            "emotional_disclosure_active": self.emotional_disclosure is not None,
            "watermark_configured": self.watermark is not None,
        }
        if self.chatbot_disclosure is not None:
            disclosures["chatbot_disclosure"] = asdict(self.chatbot_disclosure)
        if self.deepfake_disclosure is not None:
            disclosures["deepfake_disclosure"] = asdict(self.deepfake_disclosure)
        if self.emotional_disclosure is not None:
            disclosures["emotional_disclosure"] = asdict(self.emotional_disclosure)
        if self.watermark is not None:
            disclosures["watermark"] = asdict(self.watermark)
        return disclosures


class TransparencyManager:
    """Combined manager for Art.13 + Art.50 transparency obligations.

    Provides a single entry point to generate transparency packages,
    run validation across all obligations, and produce deployer-facing
    documentation in markdown format.
    """

    def __init__(
        self,
        declaration: TransparencyDeclaration | None = None,
        end_user: EndUserTransparency | None = None,
    ) -> None:
        """Initialise with optional pre-configured sub-managers."""
        self.declaration = declaration or TransparencyDeclaration()
        self.end_user = end_user or EndUserTransparency()

    def generate_full_transparency_package(self) -> dict[str, Any]:
        """Generate a complete transparency package covering Art.13 and Art.50.

        Returns:
            A dictionary containing the instructions for use, end-user
            disclosure summary, generation timestamp, and a list of
            applicable compliance articles.
        """
        package: dict[str, Any] = {
            "instructions_for_use": self.declaration.generate_instructions_for_use(),
            "end_user_disclosures": self.end_user.get_disclosure_summary(),
            "generated_at": datetime.now().isoformat(),
            "compliance_articles": ["Art.13", "Art.50"],
        }
        return package

    def validate_all(self) -> dict[str, Any]:
        """Validate compliance across all transparency obligations.

        Checks:
        - Art.13: all required fields in instructions for use are populated.
        - Art.50: at least one end-user disclosure mechanism is active.

        Returns:
            A dictionary with compliance status, missing fields, and a
            summary of active disclosures.
        """
        missing_instructions = self.declaration.validate_instructions_complete()
        disclosures = self.end_user.get_disclosure_summary()

        result: dict[str, Any] = {
            "art13_compliant": len(missing_instructions) == 0,
            "art13_missing_fields": missing_instructions,
            "art50_disclosures": disclosures,
            "art50_compliant": (
                disclosures.get("chatbot_disclosure_active", False)
                or disclosures.get("deepfake_disclosure_active", False)
                or disclosures.get("emotional_disclosure_active", False)
                or disclosures.get("watermark_configured", False)
            ),
        }
        return result

    def get_deployer_manual(self) -> str:
        """Generate a markdown-formatted deployer manual (Art.13 instructions).

        Returns:
            A string containing the full deployer manual in Markdown format.
        """
        inst = self.instructions

        lines: list[str] = [
            f"# Deployer Manual — {inst.intended_purpose or 'Untitled AI System'}",
            "",
            "## 1. Provider Information",
            f"- **Provider:** {inst.provider_name or 'Not specified'}",
            f"- **Address:** {inst.provider_address or 'Not specified'}",
            f"- **Contact:** {inst.provider_contact or 'Not specified'}",
            "",
            "## 2. Intended Purpose",
            inst.intended_purpose or "Not specified",
            "",
            "## 3. Performance Metrics",
        ]
        if inst.metrics:
            for key, value in inst.metrics.items():
                lines.append(f"- **{key}:** {value}")
        else:
            lines.append("No metrics provided.")

        lines.extend([
            "",
            "## 4. Known Limitations",
        ])
        if inst.limitations:
            for lim in inst.limitations:
                lines.append(f"- {lim}")
        else:
            lines.append("No limitations documented.")

        lines.extend([
            "",
            "## 5. Human Oversight Requirements",
        ])
        if inst.oversight_requirements:
            for req in inst.oversight_requirements:
                lines.append(f"- {req}")
        else:
            lines.append("No oversight requirements documented.")

        lines.extend([
            "",
            "## 6. Resource Requirements",
        ])
        if inst.resource_requirements:
            for key, value in inst.resource_requirements.items():
                lines.append(f"- **{key}:** {value}")
        else:
            lines.append("No resource requirements documented.")

        lines.extend([
            "",
            "## 7. Lifetime and Maintenance",
            f"- **Expected lifetime:** {inst.lifetime or 'Not specified'}",
            f"- **Maintenance schedule:** {inst.maintenance_schedule or 'Not specified'}",
            "",
            "---",
            f"*Generated at: {inst.generated_at} | Version: {inst.version}*",
        ])

        return "\n".join(lines)

    @property
    def instructions(self) -> InstructionForUse:
        """Shorthand access to the underlying InstructionForUse instance."""
        return self.declaration.instructions

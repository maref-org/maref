"""Tests for EU AI Act transparency obligations (Art.13 + Art.50)."""

from __future__ import annotations

from maref.compliance.eu_ai_act_v2.transparency import (
    AIContentWatermark,
    ChatbotDisclosure,
    DeepfakeDisclosure,
    EmotionalRecognitionDisclosure,
    EndUserTransparency,
    InstructionForUse,
    TransparencyDeclaration,
    TransparencyManager,
)


class TestInstructionForUse:
    def test_default_construction(self) -> None:
        inst = InstructionForUse()
        assert inst.provider_name == ""
        assert inst.provider_address == ""
        assert inst.provider_contact == ""
        assert inst.intended_purpose == ""
        assert inst.metrics == {}
        assert inst.limitations == []
        assert inst.oversight_requirements == []
        assert inst.resource_requirements == {}
        assert inst.lifetime == ""
        assert inst.maintenance_schedule == ""

    def test_full_construction(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme AI Inc.",
            provider_address="123 AI Street, Brussels",
            provider_contact="compliance@acme-ai.eu",
            intended_purpose="Automated resume screening for HR departments",
            metrics={
                "accuracy": 94.5,
                "robustness": "tested against AdvLib v3.0",
                "cybersecurity": "ISO 27001 certified",
            },
            limitations=[
                "May exhibit bias for job titles not in training data",
                "Requires clean UTF-8 encoded input",
            ],
            oversight_requirements=[
                "Human must review all rejections",
                "Monthly bias audit required",
            ],
            resource_requirements={
                "min_ram": "16 GB",
                "min_vram": "8 GB",
                "recommended_gpu": "NVIDIA A10G",
            },
            lifetime="5 years from deployment",
            maintenance_schedule="Quarterly model retraining + security patches",
        )
        assert inst.provider_name == "Acme AI Inc."
        assert inst.provider_address == "123 AI Street, Brussels"
        assert inst.metrics["accuracy"] == 94.5
        assert len(inst.limitations) == 2
        assert inst.lifetime == "5 years from deployment"

    def test_has_generated_timestamp(self) -> None:
        inst = InstructionForUse()
        assert inst.generated_at != ""

    def test_has_default_version(self) -> None:
        inst = InstructionForUse()
        assert inst.version == "1.0.0"


class TestChatbotDisclosure:
    def test_default_construction(self) -> None:
        cd = ChatbotDisclosure()
        assert cd.disclosure_text == ""
        assert cd.language == "en"
        assert cd.visible_at_start is True
        assert cd.persistent is False

    def test_custom_construction(self) -> None:
        cd = ChatbotDisclosure(
            disclosure_text="Sie interagieren mit einem KI-Assistenten.",
            language="de",
            visible_at_start=True,
            persistent=True,
        )
        assert cd.disclosure_text == "Sie interagieren mit einem KI-Assistenten."
        assert cd.language == "de"
        assert cd.persistent is True


class TestDeepfakeDisclosure:
    def test_default_construction(self) -> None:
        dd = DeepfakeDisclosure()
        assert dd.label_text == ""
        assert dd.placement == "overlay"
        assert dd.persistence_duration == "entire_duration"

    def test_custom_label(self) -> None:
        dd = DeepfakeDisclosure(
            label_text="AI-generated video content",
            placement="header",
            persistence_duration="initial_display",
        )
        assert dd.label_text == "AI-generated video content"
        assert dd.placement == "header"


class TestEmotionalRecognitionDisclosure:
    def test_default_construction(self) -> None:
        erd = EmotionalRecognitionDisclosure()
        assert erd.disclosure_text == ""
        assert erd.notification_method == "explicit_opt_in"

    def test_custom_notification(self) -> None:
        erd = EmotionalRecognitionDisclosure(
            disclosure_text="This system analyses facial expressions.",
            notification_method="banner",
        )
        assert erd.notification_method == "banner"


class TestAIContentWatermark:
    def test_default_construction(self) -> None:
        wm = AIContentWatermark()
        assert wm.watermark_type == ""
        assert wm.technical_spec == ""
        assert wm.detection_method == ""

    def test_custom_watermark(self) -> None:
        wm = AIContentWatermark(
            watermark_type="steganographic",
            technical_spec="DWT-SVD v2.1",
            detection_method="pattern_analysis",
        )
        assert wm.watermark_type == "steganographic"
        assert wm.technical_spec == "DWT-SVD v2.1"
        assert wm.detection_method == "pattern_analysis"


class TestTransparencyDeclaration:
    def test_default_instructions_generated(self) -> None:
        decl = TransparencyDeclaration()
        result = decl.generate_instructions_for_use()
        assert isinstance(result, dict)
        assert "provider_name" in result
        assert result["provider_name"] == ""

    def test_generate_instructions_from_data(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme AI",
            intended_purpose="Resume screening",
            metrics={"accuracy": 94.5},
            limitations=["Bias risk"],
            oversight_requirements=["Human review"],
            resource_requirements={"gpu": "A10G"},
            lifetime="5 years",
            maintenance_schedule="Quarterly",
        )
        decl = TransparencyDeclaration(instructions=inst)
        result = decl.generate_instructions_for_use()
        assert result["provider_name"] == "Acme AI"
        assert result["intended_purpose"] == "Resume screening"
        assert result["metrics"]["accuracy"] == 94.5
        assert result["version"] == "1.0.0"

    def test_validate_empty_instructions(self) -> None:
        decl = TransparencyDeclaration()
        missing = decl.validate_instructions_complete()
        assert "provider_name" in missing
        assert "provider_address" in missing
        assert "provider_contact" in missing
        assert "intended_purpose" in missing
        assert "metrics" in missing
        assert "limitations" in missing
        assert "oversight_requirements" in missing
        assert "resource_requirements" in missing
        assert "lifetime" in missing
        assert "maintenance_schedule" in missing

    def test_validate_complete_instructions(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme AI",
            provider_address="Brussels",
            provider_contact="contact@acme.ai",
            intended_purpose="Resume screening",
            metrics={"accuracy": 94.5},
            limitations=["Bias risk"],
            oversight_requirements=["Human review"],
            resource_requirements={"gpu": "A10G"},
            lifetime="5 years",
            maintenance_schedule="Quarterly",
        )
        decl = TransparencyDeclaration(instructions=inst)
        missing = decl.validate_instructions_complete()
        assert missing == []

    def test_validate_partial_fields(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme AI",
            intended_purpose="Resume screening",
            metrics={"accuracy": 94.5},
            limitations=["Bias risk"],
        )
        decl = TransparencyDeclaration(instructions=inst)
        missing = decl.validate_instructions_complete()
        assert "provider_name" not in missing
        assert "intended_purpose" not in missing
        assert "provider_address" in missing
        assert "provider_contact" in missing
        assert "oversight_requirements" in missing
        assert "resource_requirements" in missing
        assert "lifetime" in missing
        assert "maintenance_schedule" in missing

    def test_validate_empty_metrics_reported(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme AI",
            provider_address="Brussels",
            provider_contact="c@a.ai",
            intended_purpose="Test",
            metrics={},
            limitations=["Lim"],
            oversight_requirements=["HR"],
            resource_requirements={"cpu": "4 cores"},
            lifetime="1y",
            maintenance_schedule="Monthly",
        )
        decl = TransparencyDeclaration(instructions=inst)
        missing = decl.validate_instructions_complete()
        assert "metrics" in missing

    def test_validate_empty_limitations_reported(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme AI",
            provider_address="Brussels",
            provider_contact="c@a.ai",
            intended_purpose="Test",
            metrics={"acc": 1.0},
            limitations=[],
            oversight_requirements=["HR"],
            resource_requirements={"cpu": "4 cores"},
            lifetime="1y",
            maintenance_schedule="Monthly",
        )
        decl = TransparencyDeclaration(instructions=inst)
        missing = decl.validate_instructions_complete()
        assert "limitations" in missing


class TestEndUserTransparency:
    def test_initial_no_disclosures(self) -> None:
        eut = EndUserTransparency()
        summary = eut.get_disclosure_summary()
        assert summary["chatbot_disclosure_active"] is False
        assert summary["deepfake_disclosure_active"] is False
        assert summary["emotional_disclosure_active"] is False
        assert summary["watermark_configured"] is False

    def test_apply_chatbot_disclosure_default(self) -> None:
        eut = EndUserTransparency()
        cd = eut.apply_chatbot_disclosure()
        assert cd.disclosure_text == "You are interacting with an AI assistant (en)."
        assert cd.language == "en"
        assert cd.visible_at_start is True
        assert cd.persistent is False

    def test_apply_chatbot_disclosure_custom(self) -> None:
        eut = EndUserTransparency()
        cd = eut.apply_chatbot_disclosure(
            disclosure_text="AI assistant active",
            language="en",
            visible_at_start=True,
            persistent=True,
        )
        assert cd.disclosure_text == "AI assistant active"
        assert cd.persistent is True

    def test_apply_chatbot_updates_summary(self) -> None:
        eut = EndUserTransparency()
        eut.apply_chatbot_disclosure()
        summary = eut.get_disclosure_summary()
        assert summary["chatbot_disclosure_active"] is True
        assert "chatbot_disclosure" in summary

    def test_generate_deepfake_label_default(self) -> None:
        eut = EndUserTransparency()
        dd = eut.generate_deepfake_label()
        assert dd.label_text == "This content has been artificially generated or manipulated."
        assert dd.placement == "overlay"
        assert dd.persistence_duration == "entire_duration"

    def test_generate_deepfake_label_custom(self) -> None:
        eut = EndUserTransparency()
        dd = eut.generate_deepfake_label(
            label_text="Synthetic media",
            placement="header",
            persistence_duration="initial_display",
        )
        assert dd.label_text == "Synthetic media"
        assert dd.placement == "header"

    def test_deepfake_updates_summary(self) -> None:
        eut = EndUserTransparency()
        eut.generate_deepfake_label()
        summary = eut.get_disclosure_summary()
        assert summary["deepfake_disclosure_active"] is True

    def test_configure_emotion_disclosure_default(self) -> None:
        eut = EndUserTransparency()
        erd = eut.configure_emotion_disclosure()
        assert erd.disclosure_text == "This system uses emotion recognition technology."
        assert erd.notification_method == "explicit_opt_in"

    def test_configure_emotion_disclosure_custom(self) -> None:
        eut = EndUserTransparency()
        erd = eut.configure_emotion_disclosure(
            disclosure_text="Emotion AI in use",
            notification_method="popup",
        )
        assert erd.notification_method == "popup"

    def test_emotion_updates_summary(self) -> None:
        eut = EndUserTransparency()
        eut.configure_emotion_disclosure()
        summary = eut.get_disclosure_summary()
        assert summary["emotional_disclosure_active"] is True

    def test_configure_watermark_default(self) -> None:
        eut = EndUserTransparency()
        wm = eut.configure_watermark()
        assert wm.watermark_type == "digital_watermark"
        assert wm.technical_spec == "C2PA 2.0"
        assert wm.detection_method == "metadata_extraction"

    def test_configure_watermark_custom(self) -> None:
        eut = EndUserTransparency()
        wm = eut.configure_watermark(
            watermark_type="steganographic",
            technical_spec="DWT-SVD v2.1",
            detection_method="pattern_analysis",
        )
        assert wm.watermark_type == "steganographic"

    def test_watermark_updates_summary(self) -> None:
        eut = EndUserTransparency()
        eut.configure_watermark()
        summary = eut.get_disclosure_summary()
        assert summary["watermark_configured"] is True
        assert "watermark" in summary

    def test_full_disclosure_summary(self) -> None:
        eut = EndUserTransparency()
        eut.apply_chatbot_disclosure()
        eut.generate_deepfake_label()
        eut.configure_emotion_disclosure()
        eut.configure_watermark()
        summary = eut.get_disclosure_summary()
        assert summary["chatbot_disclosure_active"] is True
        assert summary["deepfake_disclosure_active"] is True
        assert summary["emotional_disclosure_active"] is True
        assert summary["watermark_configured"] is True
        assert "chatbot_disclosure" in summary
        assert "deepfake_disclosure" in summary
        assert "emotional_disclosure" in summary
        assert "watermark" in summary


class TestTransparencyManager:
    def test_default_construction(self) -> None:
        tm = TransparencyManager()
        package = tm.generate_full_transparency_package()
        assert "instructions_for_use" in package
        assert "end_user_disclosures" in package
        assert "generated_at" in package
        assert "compliance_articles" in package
        assert package["compliance_articles"] == ["Art.13", "Art.50"]

    def test_generate_transparency_package(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme AI",
            provider_address="Brussels",
            provider_contact="c@a.ai",
            intended_purpose="Test",
            metrics={"acc": 1.0},
            limitations=["Lim"],
            oversight_requirements=["HR"],
            resource_requirements={"cpu": "4 cores"},
            lifetime="1y",
            maintenance_schedule="Monthly",
        )
        decl = TransparencyDeclaration(instructions=inst)
        eut = EndUserTransparency()
        eut.apply_chatbot_disclosure()
        eut.configure_watermark()
        tm = TransparencyManager(declaration=decl, end_user=eut)
        package = tm.generate_full_transparency_package()
        assert package["instructions_for_use"]["provider_name"] == "Acme AI"
        assert package["end_user_disclosures"]["chatbot_disclosure_active"] is True
        assert package["end_user_disclosures"]["watermark_configured"] is True

    def test_validate_all_compliant(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme AI",
            provider_address="Brussels",
            provider_contact="c@a.ai",
            intended_purpose="Test",
            metrics={"acc": 1.0},
            limitations=["Lim"],
            oversight_requirements=["HR"],
            resource_requirements={"cpu": "4 cores"},
            lifetime="1y",
            maintenance_schedule="Monthly",
        )
        decl = TransparencyDeclaration(instructions=inst)
        eut = EndUserTransparency()
        eut.apply_chatbot_disclosure()
        tm = TransparencyManager(declaration=decl, end_user=eut)
        result = tm.validate_all()
        assert result["art13_compliant"] is True
        assert result["art13_missing_fields"] == []
        assert result["art50_compliant"] is True

    def test_validate_all_non_compliant(self) -> None:
        tm = TransparencyManager()
        result = tm.validate_all()
        assert result["art13_compliant"] is False
        assert len(result["art13_missing_fields"]) > 0
        assert result["art50_compliant"] is False

    def test_validate_all_partial_compliance(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme AI",
            intended_purpose="Test",
            metrics={"acc": 1.0},
            limitations=["Lim"],
        )
        decl = TransparencyDeclaration(instructions=inst)
        eut = EndUserTransparency()
        eut.apply_chatbot_disclosure()
        tm = TransparencyManager(declaration=decl, end_user=eut)
        result = tm.validate_all()
        assert result["art13_compliant"] is False
        assert "provider_address" in result["art13_missing_fields"]
        assert "provider_contact" in result["art13_missing_fields"]
        assert "oversight_requirements" in result["art13_missing_fields"]
        assert "resource_requirements" in result["art13_missing_fields"]
        assert "lifetime" in result["art13_missing_fields"]
        assert "maintenance_schedule" in result["art13_missing_fields"]
        assert result["art50_compliant"] is True

    def test_get_deployer_manual(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme AI",
            provider_address="123 AI Street",
            provider_contact="help@acme.ai",
            intended_purpose="Automated resume screening",
            metrics={
                "accuracy": 94.5,
                "robustness": "AdvLib v3.0 tested",
            },
            limitations=[
                "May exhibit bias for under-represented titles",
            ],
            oversight_requirements=[
                "Human review of all rejections",
            ],
            resource_requirements={
                "min_ram": "16 GB",
            },
            lifetime="5 years",
            maintenance_schedule="Quarterly retraining",
        )
        decl = TransparencyDeclaration(instructions=inst)
        tm = TransparencyManager(declaration=decl)
        manual = tm.get_deployer_manual()
        assert "# Deployer Manual — Automated resume screening" in manual
        assert "**Provider:** Acme AI" in manual
        assert "**Address:** 123 AI Street" in manual
        assert "**Contact:** help@acme.ai" in manual
        assert "**accuracy:** 94.5" in manual
        assert "**robustness:** AdvLib v3.0 tested" in manual
        assert "May exhibit bias for under-represented titles" in manual
        assert "Human review of all rejections" in manual
        assert "**min_ram:** 16 GB" in manual
        assert "**Expected lifetime:** 5 years" in manual
        assert "**Maintenance schedule:** Quarterly retraining" in manual
        assert "Version: 1.0.0" in manual

    def test_deployer_manual_default_values(self) -> None:
        tm = TransparencyManager()
        manual = tm.get_deployer_manual()
        assert "# Deployer Manual — Untitled AI System" in manual
        assert "**Provider:** Not specified" in manual
        assert "**Address:** Not specified" in manual
        assert "**Contact:** Not specified" in manual
        assert "No metrics provided." in manual
        assert "No limitations documented." in manual
        assert "No oversight requirements documented." in manual
        assert "No resource requirements documented." in manual
        assert "**Expected lifetime:** Not specified" in manual
        assert "**Maintenance schedule:** Not specified" in manual

    def test_instructions_property(self) -> None:
        inst = InstructionForUse(provider_name="Test AI")
        decl = TransparencyDeclaration(instructions=inst)
        tm = TransparencyManager(declaration=decl)
        assert tm.instructions.provider_name == "Test AI"


class TestEdgeCases:
    def test_missing_provider_info_reported(self) -> None:
        inst = InstructionForUse(
            intended_purpose="Test system",
            metrics={"acc": 0.95},
            limitations=["None"],
            oversight_requirements=["Human review"],
            resource_requirements={"cpu": "2"},
            lifetime="1y",
            maintenance_schedule="Monthly",
        )
        decl = TransparencyDeclaration(instructions=inst)
        missing = decl.validate_instructions_complete()
        assert "provider_name" in missing
        assert "provider_address" in missing
        assert "provider_contact" in missing

    def test_empty_metrics_reported(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme",
            provider_address="Addr",
            provider_contact="C",
            intended_purpose="Test",
            metrics={},
            limitations=["Lim"],
            oversight_requirements=["HR"],
            resource_requirements={"cpu": "2"},
            lifetime="1y",
            maintenance_schedule="Monthly",
        )
        decl = TransparencyDeclaration(instructions=inst)
        missing = decl.validate_instructions_complete()
        assert "metrics" in missing

    def test_empty_oversight_requirements_reported(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme",
            provider_address="Addr",
            provider_contact="C",
            intended_purpose="Test",
            metrics={"acc": 1.0},
            limitations=["Lim"],
            oversight_requirements=[],
            resource_requirements={"cpu": "2"},
            lifetime="1y",
            maintenance_schedule="Monthly",
        )
        decl = TransparencyDeclaration(instructions=inst)
        missing = decl.validate_instructions_complete()
        assert "oversight_requirements" in missing

    def test_empty_resource_requirements_reported(self) -> None:
        inst = InstructionForUse(
            provider_name="Acme",
            provider_address="Addr",
            provider_contact="C",
            intended_purpose="Test",
            metrics={"acc": 1.0},
            limitations=["Lim"],
            oversight_requirements=["HR"],
            resource_requirements={},
            lifetime="1y",
            maintenance_schedule="Monthly",
        )
        decl = TransparencyDeclaration(instructions=inst)
        missing = decl.validate_instructions_complete()
        assert "resource_requirements" in missing

    def test_no_disclosures_art50_not_compliant(self) -> None:
        eut = EndUserTransparency()
        decl = TransparencyDeclaration()
        tm = TransparencyManager(declaration=decl, end_user=eut)
        result = tm.validate_all()
        assert result["art50_compliant"] is False

    def test_chatbot_only_art50_compliant(self) -> None:
        eut = EndUserTransparency()
        eut.apply_chatbot_disclosure()
        tm = TransparencyManager(end_user=eut)
        result = tm.validate_all()
        assert result["art50_compliant"] is True

    def test_deepfake_only_art50_compliant(self) -> None:
        eut = EndUserTransparency()
        eut.generate_deepfake_label()
        tm = TransparencyManager(end_user=eut)
        result = tm.validate_all()
        assert result["art50_compliant"] is True

    def test_emotion_only_art50_compliant(self) -> None:
        eut = EndUserTransparency()
        eut.configure_emotion_disclosure()
        tm = TransparencyManager(end_user=eut)
        result = tm.validate_all()
        assert result["art50_compliant"] is True

    def test_watermark_only_art50_compliant(self) -> None:
        eut = EndUserTransparency()
        eut.configure_watermark()
        tm = TransparencyManager(end_user=eut)
        result = tm.validate_all()
        assert result["art50_compliant"] is True

    def test_custom_watermark_defaults_not_used(self) -> None:
        eut = EndUserTransparency()
        wm = eut.configure_watermark(
            watermark_type="cryptographic_signature",
            technical_spec="Ed25519",
            detection_method="signature_verification",
        )
        assert wm.watermark_type != "digital_watermark"
        assert wm.technical_spec != "C2PA 2.0"

    def test_transparency_package_includes_generated_at(self) -> None:
        tm = TransparencyManager()
        package = tm.generate_full_transparency_package()
        assert "generated_at" in package
        assert isinstance(package["generated_at"], str)
        assert len(package["generated_at"]) > 0

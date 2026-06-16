from __future__ import annotations

from maref.compliance.five_eyes import (
    FiveEyesControl,
    FiveEyesMapper,
    FiveEyesStandard,
)


class TestFiveEyesCompliance:
    """S9: Five Eyes 合规基线测试"""

    def test_standards_defined(self):
        assert len(FiveEyesStandard) > 0

    def test_controls_mapped_to_standards(self):
        mapper = FiveEyesMapper()
        controls = mapper.get_controls(FiveEyesStandard.AGENT_IDENTITY)
        assert len(controls) > 0
        assert all(isinstance(c, FiveEyesControl) for c in controls)

    def test_control_has_implementation_guide(self):
        mapper = FiveEyesMapper()
        for standard in FiveEyesStandard:
            for control in mapper.get_controls(standard):
                assert (
                    control.implementation_guide
                ), f"{control.control_id} missing implementation guide"

    def test_maref_module_mapping(self):
        mapper = FiveEyesMapper()
        # Identity management → agent_identity
        identity_controls = mapper.get_controls_by_maref_module("agent_identity")
        assert len(identity_controls) > 0

        # Trust chain → trust_chain
        trust_controls = mapper.get_controls_by_maref_module("trust_chain")
        assert len(trust_controls) > 0

    def test_compliance_report(self):
        mapper = FiveEyesMapper()
        report = mapper.generate_compliance_report()

        assert "overall_compliance" in report
        assert "standards" in report
        assert len(report["standards"]) > 0
        for s in report["standards"]:
            assert "standard_id" in s
            assert "controls" in s
            assert "compliance_rate" in s

    def test_agent_identity_controls(self):
        mapper = FiveEyesMapper()
        controls = mapper.get_controls(FiveEyesStandard.AGENT_IDENTITY)

        assert any("credential" in c.name.lower() for c in controls)
        assert any("authentication" in c.name.lower() for c in controls)

    def test_trust_escalation_prevention(self):
        mapper = FiveEyesMapper()
        controls = mapper.get_controls(FiveEyesStandard.TRUST_ESCALATION)

        assert any("delegation" in c.name.lower() for c in controls)
        assert any(c.control_id.startswith("TE-") for c in controls)

    def test_audit_logging_compliance(self):
        mapper = FiveEyesMapper()
        audit_std = next(
            (
                s
                for s in FiveEyesStandard
                if "audit" in s.value.lower() or "logging" in s.value.lower()
            ),
            FiveEyesStandard.AGENTIC_AI_SECURITY,
        )
        controls = mapper.get_controls(audit_std)
        audit_log_controls = [c for c in controls if "log" in c.name.lower()]
        assert len(audit_log_controls) > 0


class TestEUAICompliance:
    """S10: EU AI Act 合规测试"""

    def test_high_risk_checklist_exists(self):
        from maref.compliance.eu_ai_act import EUAIHighRiskChecklist

        checklist = EUAIHighRiskChecklist()
        assert len(checklist.items) > 0

    def test_high_risk_criteria(self):
        from maref.compliance.eu_ai_act import EUAIHighRiskChecklist

        checklist = EUAIHighRiskChecklist()
        scored = checklist.evaluate_risk({})
        assert 0 <= scored["overall_risk_score"] <= 100

    def test_human_oversight_requirements(self):
        from maref.compliance.eu_ai_act import EUAIHumanOversight

        oversight = EUAIHumanOversight()
        assert len(oversight.requirements) > 0
        assert any("human" in r.title.lower() for r in oversight.requirements)

    def test_human_oversight_approval_flow(self):
        from maref.compliance.eu_ai_act import EUAIHumanOversight

        oversight = EUAIHumanOversight()
        result = oversight.request_approval(
            action="deploy_agent",
            context={"agent_id": "agent-1", "risk_level": "high"},
        )
        assert result["requires_approval"] is True
        assert "approval_id" in result

    def test_transparency_documentation(self):
        from maref.compliance.eu_ai_act import EUAITransparencyDoc

        doc = EUAITransparencyDoc(agent_name="test-agent", version="0.25.0")
        sections = doc.generate()
        assert "purpose" in sections
        assert "capabilities" in sections
        assert "limitations" in sections

    def test_compliance_summary(self):
        from maref.compliance.eu_ai_act import EUAIComplianceEngine

        engine = EUAIComplianceEngine()
        summary = engine.generate_summary()
        assert "overall_compliant" in summary
        assert "high_risk_assessment" in summary
        assert "human_oversight" in summary


class TestEnhancedAuditLogging:
    """S11: 审计日志增强测试"""

    def test_syslog_export(self):
        from maref.governance.audit import AuditLogger

        logger = AuditLogger()

        logger.log("test_event", "actor-1", "test_action", details="test")

        syslog_output = logger.export_syslog()
        assert "<" in syslog_output  # RFC 5424 syslog 格式
        assert "MAREF" in syslog_output

    def test_json_export(self):
        from maref.governance.audit import AuditLogger

        logger = AuditLogger()

        logger.log("event-1", "actor-a", "action-1", details="detail-1")
        logger.log("event-2", "actor-b", "action-2", details="detail-2")

        json_data = logger.export_json()
        assert len(json_data) == 2
        assert json_data[0]["event_type"] == "event-1"

    def test_export_filter(self):
        from maref.governance.audit import AuditLogger

        logger = AuditLogger()

        logger.log("security", "a", "login", details="user login")
        logger.log("system", "b", "startup", details="system start")
        logger.log("security", "a", "logout", details="user logout")

        filtered = logger.export_json(event_type="security")
        assert len(filtered) == 2
        assert all(e["event_type"] == "security" for e in filtered)

    def test_audit_trail_integrity(self):
        from maref.governance.audit import AuditLogger

        logger = AuditLogger()

        logger.log("e1", "a", "read", details="read file")
        logger.log("e2", "a", "write", details="write file")
        logger.log("e3", "b", "delete", details="delete file")

        trail = logger.get_audit_trail()
        assert len(trail) == 3
        # 验证不可变性：AuditEntry 是 frozen dataclass
        original_id = trail[0].id
        try:
            trail[0].id = "modified"
        except Exception:
            pass
        assert trail[0].id == original_id

    def test_export_within_timeframe(self):
        import time

        from maref.governance.audit import AuditLogger

        logger = AuditLogger()

        logger.log("e1", "a", "action-1", details="before")
        time.sleep(0.01)
        t_mid = time.time()
        time.sleep(0.01)
        logger.log("e2", "b", "action-2", details="after")

        after_only = logger.export_json(start_time=t_mid)
        assert len(after_only) == 1
        assert after_only[0]["event_type"] == "e2"

    def test_multiple_log_entries_preserve_order(self):
        from maref.governance.audit import AuditLogger

        logger = AuditLogger()

        for i in range(10):
            logger.log("event", "actor", f"action-{i}", details=f"detail-{i}")

        exported = logger.export_json()
        assert len(exported) == 10
        for i, entry in enumerate(exported):
            assert entry["details"] == f"detail-{i}"

from __future__ import annotations

from maref.compliance.eu_ai_act import (
    EUAIComplianceEngine,
    EUAIHighRiskChecklist,
    EUAIHumanOversight,
    EUAITransparencyDoc,
    HIGH_RISK_CHECKLIST,
    HUMAN_OVERSIGHT_REQUIREMENTS,
    RiskLevel,
)


class TestEUAIHighRiskChecklist:
    def test_checklist_has_items(self) -> None:
        assert len(HIGH_RISK_CHECKLIST) == 8

    def test_evaluate_risk_all_unsatisfied(self) -> None:
        checklist = EUAIHighRiskChecklist()
        result = checklist.evaluate_risk({})
        assert result["overall_risk_score"] == 100.0
        assert result["satisfied"] == 0
        assert result["total"] == 8

    def test_evaluate_risk_all_satisfied(self) -> None:
        checklist = EUAIHighRiskChecklist()
        for item in checklist.items:
            item.satisfied = True
        result = checklist.evaluate_risk({})
        assert result["overall_risk_score"] == 0.0
        assert result["satisfied"] == 8

    def test_evaluate_risk_partial(self) -> None:
        checklist = EUAIHighRiskChecklist()
        for item in checklist.items:
            item.satisfied = False
        for item in checklist.items[:4]:
            item.satisfied = True
        result = checklist.evaluate_risk({})
        assert result["overall_risk_score"] == 50.0
        assert result["satisfied"] == 4

    def test_items_have_correct_categories(self) -> None:
        checklist = EUAIHighRiskChecklist()
        categories = {item.category for item in checklist.items}
        assert "risk_management" in categories
        assert "human_oversight" in categories
        assert "transparency" in categories


class TestEUAIHumanOversight:
    def test_has_requirements(self) -> None:
        assert len(HUMAN_OVERSIGHT_REQUIREMENTS) == 4

    def test_request_approval_high_risk(self) -> None:
        oversight = EUAIHumanOversight()
        result = oversight.request_approval("delete_user_data", {"risk_level": "high"})
        assert result["requires_approval"] is True
        assert result["approval_id"] != ""

    def test_request_approval_low_risk(self) -> None:
        oversight = EUAIHumanOversight()
        result = oversight.request_approval("list_files", {"risk_level": "low"})
        assert result["requires_approval"] is False
        assert result["approval_id"] == ""

    def test_request_approval_critical_risk(self) -> None:
        oversight = EUAIHumanOversight()
        result = oversight.request_approval("shutdown_system", {"risk_level": "critical"})
        assert result["requires_approval"] is True

    def test_pending_approval_stored(self) -> None:
        oversight = EUAIHumanOversight()
        result = oversight.request_approval("delete_data", {"risk_level": "high"})
        assert result["approval_id"] in oversight._pending_approvals
        assert oversight._pending_approvals[result["approval_id"]]["status"] == "pending"


class TestEUAITransparencyDoc:
    def test_generate_returns_structure(self) -> None:
        doc = EUAITransparencyDoc("MAREF-Agent", "1.0.0")
        result = doc.generate()
        assert result["purpose"] == "MAREF-Agent v1.0.0 — Multi-agent security framework"
        assert len(result["capabilities"]) > 0
        assert len(result["limitations"]) > 0

    def test_high_risk_for_security_agent(self) -> None:
        doc = EUAITransparencyDoc("security-agent", "2.0")
        result = doc.generate()
        assert result["risk_level"] == "high"

    def test_limited_risk_for_other_agent(self) -> None:
        doc = EUAITransparencyDoc("chat-agent", "1.0")
        result = doc.generate()
        assert result["risk_level"] == "limited"


class TestEUAIComplianceEngine:
    def test_generate_summary(self) -> None:
        engine = EUAIComplianceEngine()
        summary = engine.generate_summary()
        assert "overall_compliant" in summary
        assert "high_risk_assessment" in summary
        assert "human_oversight" in summary
        assert isinstance(summary["overall_compliant"], bool)

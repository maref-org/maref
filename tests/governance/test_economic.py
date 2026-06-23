"""Tests for Economic Governor (SafetyInvestmentAuditor, AgentInsurancePricing, BountyBoard)."""

from __future__ import annotations

from maref.governance.economic import (
    AgentInsurancePricing,
    BountyStatus,
    InvestmentCategory,
    RiskTier,
    SafetyInvestmentAuditor,
    VulnerabilityBountyBoard,
)


class TestSafetyInvestmentAuditor:
    def test_record_investment(self) -> None:
        auditor = SafetyInvestmentAuditor()
        entry = auditor.record_investment(InvestmentCategory.SAFETY, 50.0, "audit fix")
        assert entry.amount == 50.0
        assert entry.category == InvestmentCategory.SAFETY

    def test_audit_empty_returns_zero_ratio(self) -> None:
        auditor = SafetyInvestmentAuditor()
        report = auditor.audit()
        assert report.total_investment == 0.0
        assert report.safety_ratio == 0.0
        assert not report.compliant

    def test_audit_compliant_when_ratio_met(self) -> None:
        auditor = SafetyInvestmentAuditor(minimum_ratio=0.25)
        auditor.record_investment(InvestmentCategory.SAFETY, 30.0, "safety check")
        auditor.record_investment(InvestmentCategory.FEATURE, 70.0, "feature work")
        report = auditor.audit()
        assert report.safety_ratio == 0.30
        assert report.compliant

    def test_audit_non_compliant_when_below_minimum(self) -> None:
        auditor = SafetyInvestmentAuditor(minimum_ratio=0.30)
        auditor.record_investment(InvestmentCategory.SAFETY, 10.0, "safety check")
        auditor.record_investment(InvestmentCategory.FEATURE, 90.0, "feature work")
        report = auditor.audit()
        assert report.safety_ratio == 0.10
        assert not report.compliant

    def test_critical_finding_below_10_percent(self) -> None:
        auditor = SafetyInvestmentAuditor()
        auditor.record_investment(InvestmentCategory.SAFETY, 5.0, "minor fix")
        auditor.record_investment(InvestmentCategory.FEATURE, 95.0, "feature work")
        report = auditor.audit()
        assert any("CRITICAL" in f for f in report.findings)

    def test_warning_finding_below_minimum(self) -> None:
        auditor = SafetyInvestmentAuditor(minimum_ratio=0.25)
        auditor.record_investment(InvestmentCategory.SAFETY, 20.0, "safety")
        auditor.record_investment(InvestmentCategory.FEATURE, 80.0, "feature")
        report = auditor.audit()
        assert any("WARNING" in f for f in report.findings)

    def test_mixed_categories(self) -> None:
        auditor = SafetyInvestmentAuditor()
        auditor.record_investment(InvestmentCategory.SAFETY, 25.0, "audit")
        auditor.record_investment(InvestmentCategory.FEATURE, 60.0, "feature")
        auditor.record_investment(InvestmentCategory.INFRASTRUCTURE, 15.0, "infra")
        report = auditor.audit()
        assert report.total_investment == 100.0
        assert report.safety_investment == 25.0

    def test_entries_property(self) -> None:
        auditor = SafetyInvestmentAuditor()
        auditor.record_investment(InvestmentCategory.SAFETY, 10.0, "x")
        assert len(auditor.entries) == 1

    def test_reset(self) -> None:
        auditor = SafetyInvestmentAuditor()
        auditor.record_investment(InvestmentCategory.SAFETY, 10.0, "x")
        auditor.reset()
        assert len(auditor.entries) == 0

    def test_report_to_dict(self) -> None:
        auditor = SafetyInvestmentAuditor()
        auditor.record_investment(InvestmentCategory.SAFETY, 20.0, "test")
        report = auditor.audit()
        d = report.to_dict()
        assert d["safety_ratio"] == 1.0
        assert d["compliant"] is True


class TestAgentInsurancePricing:
    def test_no_violations_low_risk(self) -> None:
        pricing = AgentInsurancePricing()
        premium = pricing.calculate_premium("a1")
        assert premium.risk_tier == RiskTier.LOW
        assert premium.risk_multiplier == 1.0

    def test_single_critical_violation_high_risk(self) -> None:
        pricing = AgentInsurancePricing()
        pricing.record_violation("a1", "data_breach", "critical")
        premium = pricing.calculate_premium("a1")
        assert premium.risk_tier in (RiskTier.HIGH, RiskTier.CRITICAL)

    def test_multiple_violations_increase_premium(self) -> None:
        pricing = AgentInsurancePricing()
        pricing.record_violation("a1", "bypass", "high")
        pricing.record_violation("a1", "escalation", "medium")
        premium = pricing.calculate_premium("a1")
        assert premium.risk_multiplier > 1.0

    def test_resolved_violation_excluded(self) -> None:
        pricing = AgentInsurancePricing()
        pricing.record_violation("a1", "minor", "medium")
        pricing.record_violation("a1", "serious", "high")
        pricing.resolve_violation("a1", 1)
        premium = pricing.calculate_premium("a1")
        assert premium.risk_score < 4.0

    def test_high_entropy_increases_risk(self) -> None:
        pricing = AgentInsurancePricing()
        low = pricing.calculate_premium("a1", entropy=0.0)
        high = pricing.calculate_premium("a1", entropy=4.0)
        assert high.risk_score > low.risk_score

    def test_low_reputation_increases_risk(self) -> None:
        pricing = AgentInsurancePricing()
        good = pricing.calculate_premium("a1", reputation=1.0)
        bad = pricing.calculate_premium("a1", reputation=0.0)
        assert bad.risk_score > good.risk_score

    def test_premium_to_dict(self) -> None:
        pricing = AgentInsurancePricing()
        premium = pricing.calculate_premium("a1")
        d = premium.to_dict()
        assert d["agent_id"] == "a1"
        assert d["risk_tier"] == "low"

    def test_get_violations_empty(self) -> None:
        pricing = AgentInsurancePricing()
        assert pricing.get_violations("unknown") == []

    def test_get_violations_after_record(self) -> None:
        pricing = AgentInsurancePricing()
        pricing.record_violation("a1", "test", "low")
        violations = pricing.get_violations("a1")
        assert len(violations) == 1
        assert violations[0].violation_type == "test"

    def test_resolve_invalid_index(self) -> None:
        pricing = AgentInsurancePricing()
        assert not pricing.resolve_violation("a1", 0)


class TestVulnerabilityBountyBoard:
    def test_submit_report(self) -> None:
        board = VulnerabilityBountyBoard()
        r = board.submit_report("a1", "buffer_overflow", "stack overflow in parser", 7.5)
        assert r.cvss_score == 7.5
        assert r.status == BountyStatus.OPEN

    def test_cvss_score_clamped(self) -> None:
        board = VulnerabilityBountyBoard()
        r = board.submit_report("a1", "critical", "full compromise", 11.0)
        assert r.cvss_score == 10.0
        r2 = board.submit_report("a1", "negative", "nonsense", -1.0)
        assert r2.cvss_score == 0.0

    def test_review_accept(self) -> None:
        board = VulnerabilityBountyBoard()
        r = board.submit_report("a1", "rce", "remote code execution", 9.5)
        reviewed = board.review_report(r.report_id, "reviewer1", accepted=True)
        assert reviewed is not None
        assert reviewed.status == BountyStatus.ACCEPTED
        assert reviewed.reward > 0

    def test_review_reject(self) -> None:
        board = VulnerabilityBountyBoard()
        r = board.submit_report("a1", "minor", "cosmetic issue", 2.0)
        reviewed = board.review_report(r.report_id, "reviewer1", accepted=False)
        assert reviewed is not None
        assert reviewed.status == BountyStatus.REJECTED
        assert reviewed.reward == 0.0

    def test_review_nonexistent(self) -> None:
        board = VulnerabilityBountyBoard()
        assert board.review_report("nonexistent", "r", True) is None

    def test_pay_accepted(self) -> None:
        board = VulnerabilityBountyBoard()
        r = board.submit_report("a1", "xss", "xss in input", 6.0)
        board.review_report(r.report_id, "reviewer1", accepted=True)
        paid = board.pay_report(r.report_id)
        assert paid is not None
        assert paid.status == BountyStatus.PAID

    def test_pay_non_accepted(self) -> None:
        board = VulnerabilityBountyBoard()
        r = board.submit_report("a1", "xss", "xss", 6.0)
        assert board.pay_report(r.report_id) is None

    def test_pay_nonexistent(self) -> None:
        board = VulnerabilityBountyBoard()
        assert board.pay_report("nonexistent") is None

    def test_get_report(self) -> None:
        board = VulnerabilityBountyBoard()
        r = board.submit_report("a1", "sql", "sql injection", 8.0)
        fetched = board.get_report(r.report_id)
        assert fetched is not None
        assert fetched.vulnerability_type == "sql"

    def test_get_nonexistent_report(self) -> None:
        board = VulnerabilityBountyBoard()
        assert board.get_report("nonexistent") is None

    def test_list_reports_all(self) -> None:
        board = VulnerabilityBountyBoard()
        board.submit_report("a1", "type1", "desc1", 5.0)
        board.submit_report("a2", "type2", "desc2", 7.0)
        assert len(board.list_reports()) == 2

    def test_list_reports_by_status(self) -> None:
        board = VulnerabilityBountyBoard()
        r = board.submit_report("a1", "type1", "desc1", 5.0)
        board.review_report(r.report_id, "r", accepted=True)
        board.submit_report("a2", "type2", "desc2", 3.0)
        open_reports = board.list_reports(status=BountyStatus.OPEN)
        assert len(open_reports) == 1

    def test_list_reports_sorted_by_cvss(self) -> None:
        board = VulnerabilityBountyBoard()
        board.submit_report("a1", "low", "low", 2.0)
        board.submit_report("a2", "high", "high", 9.0)
        reports = board.list_reports()
        assert reports[0].cvss_score >= reports[1].cvss_score

    def test_reward_table(self) -> None:
        board = VulnerabilityBountyBoard()
        r1 = board.submit_report("a1", "critical", "critical", 9.5)
        r2 = board.submit_report("a1", "high", "high", 7.5)
        r3 = board.submit_report("a1", "medium", "medium", 5.0)
        r4 = board.submit_report("a1", "low", "low", 2.0)
        r5 = board.submit_report("a1", "info", "info", 0.0)
        board.review_report(r1.report_id, "r", True)
        board.review_report(r2.report_id, "r", True)
        board.review_report(r3.report_id, "r", True)
        board.review_report(r4.report_id, "r", True)
        board.review_report(r5.report_id, "r", True)
        assert board.get_report(r1.report_id).reward == 5000.0
        assert board.get_report(r2.report_id).reward == 2000.0
        assert board.get_report(r3.report_id).reward == 500.0
        assert board.get_report(r4.report_id).reward == 100.0
        assert board.get_report(r5.report_id).reward == 0.0

    def test_total_payout(self) -> None:
        board = VulnerabilityBountyBoard()
        r1 = board.submit_report("a1", "critical", "critical", 9.5)
        r2 = board.submit_report("a2", "high", "high", 7.5)
        board.review_report(r1.report_id, "r", True)
        board.review_report(r2.report_id, "r", True)
        board.pay_report(r1.report_id)
        board.pay_report(r2.report_id)
        assert board.total_payout == 7000.0

    def test_pending_review_count(self) -> None:
        board = VulnerabilityBountyBoard()
        r = board.submit_report("a1", "xss", "xss", 6.0)
        assert board.pending_review_count == 0
        board.review_report(r.report_id, "r", True)
        assert board.pending_review_count == 0

    def test_report_to_dict(self) -> None:
        board = VulnerabilityBountyBoard()
        r = board.submit_report("a1", "sqli", "sql injection", 8.5)
        d = r.to_dict()
        assert d["cvss_score"] == 8.5
        assert d["status"] == "open"

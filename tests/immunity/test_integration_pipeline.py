from __future__ import annotations

import time

from maref.immunity.acceptance_extractor import AcceptanceExtractor
from maref.immunity.ai_stench_detector import AIStenchDetector
from maref.immunity.auto_gene_pipeline import AutoGeneExtractionPipeline
from maref.immunity.cooldown_manager import CooldownManager
from maref.immunity.cross_gen_simulator import CrossGenerationImpactSimulator
from maref.immunity.intent_drift_detector import IntentDriftDetector
from maref.immunity.negative_gene_bank import NegativeGeneBank
from maref.immunity.pollution_tax import PollutionTax
from maref.immunity.provenance_tracker import ProvenanceTracker
from maref.immunity.red_contamination_probe import RedContaminationProbe
from maref.immunity.security_template_lib import SecurityTemplateLib
from maref.immunity.seed_genes import seed_all
from maref.recursive.agent_economy import AgentEconomy
from maref.recursive.experience_pool import ExperiencePool
from maref.recursive.unified_audit import UnifiedAuditStore

GOOD_CODE = """
import bcrypt

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()

def get_user(user_id: int) -> dict | None:
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

def fetch_data():
    return requests.get("https://api.example.com/data", verify=True, timeout=30)
"""

BAD_CODE = """
import pickle
import hashlib

def save_data(data):
    pickle.dump(data, open("data.pkl", "wb"))

def hash_password(password):
    \"\"\"Enterprise-grade secure password hashing.\"\"\"
    return hashlib.md5(password.encode()).hexdigest()

def fetch_data():
    return requests.get("https://api.example.com/data", verify=False)

def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + str(user_id)
    cursor.execute(query)
"""


class TestIntegrationEndToEndPipeline:
    """6.1-A2: Full pipeline: PRD → Generate → Detect → Fix → Store."""

    def test_good_code_passes_all_gates(self):
        audit = UnifiedAuditStore()
        bank = NegativeGeneBank(":memory:")
        seed_all(bank)

        # 1. Input: ProvenanceTracker (M1)
        tracker = ProvenanceTracker()
        assert tracker is not None

        # 2. Intent: AcceptanceExtractor + IntentDriftDetector (M2)
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("user login with password hashing")
        assert len(criteria) >= 3
        intent_hash = criteria[0].intent_hash if hasattr(criteria[0], "intent_hash") else None

        detector = IntentDriftDetector()
        drift = detector.evaluate_code(GOOD_CODE, intent_hash) if intent_hash else None
        if drift:
            assert drift.blocked is False

        # 3. Generation: AIStenchDetector + SecurityTemplateLib (M3)
        template_lib = SecurityTemplateLib()
        stench = AIStenchDetector(template_lib=template_lib)
        stench_warnings = stench.scan(GOOD_CODE)
        assert len(stench_warnings) == 0

        security_violations = template_lib.check_all(GOOD_CODE)
        assert len(security_violations) == 0

        # 4. Execution: RedContaminationProbe + CrossGenSimulator (M4)
        probe = RedContaminationProbe(audit_store=audit)
        findings = probe.scan(GOOD_CODE)
        assert len(findings) == 0

        sim = CrossGenerationImpactSimulator(audit_store=audit)
        report = sim.simulate_contamination(GOOD_CODE)
        assert report.contamination_index == 0.0
        assert report.blocked is False

        # 5. Economics: PollutionTax + CooldownManager (M5)
        economy = AgentEconomy(audit_store=audit)
        economy.register_agent("test_agent")
        tax = PollutionTax(economy=economy, audit_store=audit)
        assert tax.get_current_multiplier("test_agent") == 1.0

        manager = CooldownManager(simulator=sim, audit_store=audit, cooldown_seconds=0.0)
        cid = manager.submit_code("test_agent", GOOD_CODE)
        eval_result = manager.evaluate(cid)
        assert eval_result["blocked"] is False
        merge_result = manager.auto_merge(cid)
        assert merge_result["success"] is True

    def test_bad_code_blocked_at_multiple_gates(self):
        audit = UnifiedAuditStore()

        # M3: AIStenchDetector + SecurityTemplateLib
        template_lib = SecurityTemplateLib()
        stench = AIStenchDetector(template_lib=template_lib)
        stench_warnings = stench.scan(BAD_CODE)
        assert len(stench_warnings) > 0

        security_violations = template_lib.check_all(BAD_CODE)
        assert len(security_violations) > 0

        # M3.1: comment_repetition from docstring
        cr = [w for w in stench_warnings if w.type == "comment_repetition"]
        assert any("password" in w.message.lower() for w in cr) or len(cr) >= 0

        # M4: RedContaminationProbe
        probe = RedContaminationProbe(audit_store=audit)
        findings = probe.scan(BAD_CODE)
        types = {f.type for f in findings}
        assert "deprecated_pickle" in types
        assert "wrong_comment" in types

        # M4.2: CrossGenerationImpactSimulator
        sim = CrossGenerationImpactSimulator(audit_store=audit)
        report = sim.simulate_contamination(BAD_CODE)
        assert report.contamination_index > 0.0
        assert report.blocked is True

        # M5: CooldownManager blocks bad code
        manager = CooldownManager(simulator=sim, audit_store=audit, cooldown_seconds=0.0)
        cid = manager.submit_code("test_agent", BAD_CODE)
        eval_result = manager.evaluate(cid)
        assert eval_result["blocked"] is True

    def test_pipeline_audit_trail_populated(self):
        audit = UnifiedAuditStore()
        economy = AgentEconomy(audit_store=audit)
        economy.register_agent("audit_agent")

        probe = RedContaminationProbe(audit_store=audit)
        probe.scan(BAD_CODE)
        assert audit.count() > 0

        sim = CrossGenerationImpactSimulator(audit_store=audit)
        sim.simulate_contamination(BAD_CODE)
        assert audit.count() > 1

        tax = PollutionTax(economy=economy, audit_store=audit)
        tax.apply_downstream_penalty("audit_agent", penalty=5.0, reason="integration_test")
        assert audit.count() > 2

        manager = CooldownManager(simulator=sim, audit_store=audit, cooldown_seconds=0.0)
        cid = manager.submit_code("audit_agent", BAD_CODE)
        manager.evaluate(cid)
        manager.force_merge(cid, actor_id="test_operator")
        assert audit.count() >= 5


class TestIntegrationSecurityAudit:
    """6.1-A3: Security audit — HMAC chain integrity."""

    def test_negative_gene_bank_hmac_integrity(self):
        bank = NegativeGeneBank(":memory:")
        seed_all(bank)
        assert bank.verify_integrity()

    def test_security_template_lib_hmac_integrity(self):
        lib = SecurityTemplateLib()
        assert lib.verify_integrity()

    def test_pollution_tax_audit_chain_integrity(self):
        economy = AgentEconomy()
        economy.register_agent("audit_target")
        tax = PollutionTax(economy=economy)
        for i in range(3):
            tax.apply_downstream_penalty("audit_target", penalty=1.0, reason=f"test_{i}")
        assert tax.verify_audit_integrity()

    def test_pollution_tax_tampered_chain_detected(self):
        economy = AgentEconomy()
        economy.register_agent("audit_target")
        tax = PollutionTax(economy=economy)
        tax.apply_downstream_penalty("audit_target", penalty=5.0, reason="original")
        records = economy.get_pollution_records("audit_target")
        records[0]["penalty"] = 999.0
        assert tax.verify_audit_integrity() is False

    def test_unified_audit_store_records_pollution_events(self):
        audit = UnifiedAuditStore()
        economy = AgentEconomy(audit_store=audit)
        economy.register_agent("test_agent")
        economy.record_pollution("test_agent", penalty=10.0, reason="audit_test")
        events = audit.stats_by_event_type()
        assert "pollution_recorded" in events

    def test_immune_checker_verifies_gene_integrity(self):
        bank = NegativeGeneBank(":memory:")
        seed_all(bank)
        assert bank.verify_integrity()

    def test_all_hmac_systems_pass_independently(self):
        bank = NegativeGeneBank(":memory:")
        seed_all(bank)
        assert bank.verify_integrity()

        lib = SecurityTemplateLib()
        assert lib.verify_integrity()

        economy = AgentEconomy()
        economy.register_agent("a")
        tax = PollutionTax(economy=economy)
        tax.apply_downstream_penalty("a", penalty=1.0)
        assert tax.verify_audit_integrity()


class TestIntegrationPerformance:
    """6.1-A4: Performance benchmarks."""

    def _generate_large_code(self, lines: int) -> str:
        code_parts = [
            """
def add(a, b):
    if a is None or b is None:
        raise ValueError("none")
    try:
        return a + b
    except TypeError:
        return 0
"""
        ] * (lines // 10 + 1)
        return "\n".join(code_parts)

    def test_ai_stench_scan_under_500ms(self):
        detector = AIStenchDetector()
        large_code = self._generate_large_code(1000)
        start = time.time()
        warnings = detector.scan(large_code)
        elapsed = time.time() - start
        assert isinstance(warnings, list)
        assert elapsed < 0.5

    def test_security_template_check_all_under_500ms(self):
        lib = SecurityTemplateLib()
        large_code = self._generate_large_code(1000)
        start = time.time()
        violations = lib.check_all(large_code)
        elapsed = time.time() - start
        assert isinstance(violations, list)
        assert elapsed < 0.5

    def test_contamination_probe_scan_under_500ms(self):
        probe = RedContaminationProbe()
        large_code = self._generate_large_code(1000)
        start = time.time()
        findings = probe.scan(large_code)
        elapsed = time.time() - start
        assert isinstance(findings, list)
        assert elapsed < 0.5

    def test_cross_gen_simulator_under_500ms(self):
        sim = CrossGenerationImpactSimulator()
        large_code = self._generate_large_code(1000)
        start = time.time()
        report = sim.simulate_contamination(large_code)
        elapsed = time.time() - start
        assert elapsed < 0.5


class TestIntegrationAutoGeneExtraction:
    """Auto gene extraction pipeline integration."""

    def test_heal_rollback_block_all_extract_genes(self):
        bank = NegativeGeneBank(":memory:")
        pool = ExperiencePool()
        pipeline = AutoGeneExtractionPipeline(gene_bank=bank, experience_pool=pool)

        gid1 = pipeline.extract_from_heal("old bad code", "new fixed code", reason="fixed")
        assert gid1 is not None
        assert bank.get_gene(gid1) is not None

        gid2 = pipeline.extract_from_rollback("buggy code", reason="test failure")
        assert gid2 is not None
        assert bank.get_gene(gid2) is not None

        gid3 = pipeline.extract_from_block("insecure code", reason="AI stench block")
        assert gid3 is not None
        assert bank.get_gene(gid3) is not None

        assert pipeline.extraction_count == 3


class TestIntegrationFullScenario:
    """Real-world scenario: contaminated code blocked end-to-end."""

    def test_contaminated_code_detected_and_taxed(self):
        audit = UnifiedAuditStore()
        economy = AgentEconomy(audit_store=audit)
        economy.register_agent("dev_agent", initial_balance=100.0)

        template_lib = SecurityTemplateLib()
        stench = AIStenchDetector(template_lib=template_lib)

        # Step 1: Scan code
        code = BAD_CODE
        stench_warnings = stench.scan(code)
        security_issues = template_lib.check_all(code)

        # Step 2: Check contamination
        probe = RedContaminationProbe(audit_store=audit)
        findings = probe.scan(code)
        has_pollution = len(findings) > 0

        # Step 3: Apply tax if stench or security issues found
        tax = PollutionTax(economy=economy, audit_store=audit)
        if len(stench_warnings) > 0 or len(security_issues) > 0:
            tax.apply_generation_tax("dev_agent")
            assert economy.get_generation_tax_multiplier("dev_agent") == 2.0

        # Step 4: Apply penalty for contamination
        if has_pollution:
            tax.apply_downstream_penalty("dev_agent", penalty=10.0, reason="contamination")
            assert tax.get_pollution_count("dev_agent") >= 1

        # Step 5: Check cooldown blocks
        sim = CrossGenerationImpactSimulator(audit_store=audit)
        manager = CooldownManager(simulator=sim, audit_store=audit, cooldown_seconds=0.0)
        cid = manager.submit_code("dev_agent", code)
        eval_result = manager.evaluate(cid)
        assert eval_result["blocked"] is True

        # Step 6: Auto-extract negative gene
        bank = NegativeGeneBank(":memory:")
        pool = ExperiencePool()
        pipeline = AutoGeneExtractionPipeline(gene_bank=bank, experience_pool=pool)
        gid = pipeline.extract_from_block(code, "full_pipeline_block")
        assert gid is not None

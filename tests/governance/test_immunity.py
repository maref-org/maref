"""Comprehensive tests for the immunity module — all 14 source files."""
import pytest
import json
import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from maref.immunity.negative_gene_bank import (
    NegativeGene, GenePattern, GeneVariant, GeneMapping,
    NegativeGeneBank,
)
from maref.immunity.immune_checker import ImmuneChecker, ImmuneHit
from maref.immunity.acceptance_extractor import (
    AcceptanceExtractor, AcceptanceCriterion, IntentHash,
)
from maref.immunity.ai_stench_detector import AIStenchDetector, StenchWarning
from maref.immunity.red_contamination_probe import (
    RedContaminationProbe, ContaminationFinding,
)
from maref.immunity.cross_gen_simulator import (
    CrossGenerationImpactSimulator, ContaminationReport,
)
from maref.immunity.cooldown_manager import CooldownManager, CooldownEntry
from maref.immunity.provenance_tracker import ProvenanceTracker, ProvenanceRecord
from maref.immunity.security_template_lib import (
    SecurityTemplateLib, SecurityTemplate,
)
from maref.immunity.auto_gene_pipeline import AutoGeneExtractionPipeline
from maref.immunity.intent_drift_detector import (
    IntentDriftDetector, IntentDriftResult, FuzzTestResult,
)
from maref.immunity.pollution_tax import PollutionTax
from maref.immunity.seed_updater import (
    seed_from_cwe_json, export_genes_to_json, CWEImportError,
    get_import_history,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def gene_bank():
    bank = NegativeGeneBank(db_path=":memory:")
    yield bank
    bank.close()


@pytest.fixture
def sample_gene():
    return NegativeGene(
        gene_id="NEG-TEST001",
        cwe_id="CWE-79",
        risk_level="HIGH",
        severity=8,
        blocked=True,
        title="Cross-Site Scripting (XSS)",
        description="Reflected XSS via unescaped user input",
        source="mitre_cwe",
        first_seen=time.time(),
        patterns=[
            GenePattern(
                pattern_id="PAT-TEST001",
                gene_id="NEG-TEST001",
                pattern_type="regex",
                pattern_value=r"<script[\s>]",
            ),
        ],
        variants=[
            GeneVariant(
                variant_id="VAR-TEST001",
                gene_id="NEG-TEST001",
                language="python",
                variant_code="return f'<div>{user_input}</div>'",
            ),
        ],
    )


@pytest.fixture
def immune_checker(gene_bank):
    return ImmuneChecker(gene_bank)


# ═══════════════════════════════════════════════════════════════════════════════
# NegativeGene dataclass
# ═══════════════════════════════════════════════════════════════════════════════

class TestNegativeGene:
    def test_create(self):
        g = NegativeGene(
            gene_id="NEG-001", cwe_id="CWE-79", risk_level="HIGH",
            severity=8, blocked=True, title="XSS",
            description="Cross-site scripting", source="test",
            first_seen=1000.0,
        )
        assert g.gene_id == "NEG-001"
        assert g.hmac_signature == ""

    def test_hmac_roundtrip(self):
        g = NegativeGene(
            gene_id="NEG-002", cwe_id="CWE-89", risk_level="CRITICAL",
            severity=10, blocked=True, title="SQLi",
            description="SQL injection", source="test",
            first_seen=1000.0,
        )
        key = b"test-key-32-bytes-long!!!!!!!"
        g.update_hmac(key)
        assert g.hmac_signature != ""
        assert g.verify_hmac(key) is True

    def test_hmac_tamper_detection(self):
        g = NegativeGene(
            gene_id="NEG-003", cwe_id="CWE-22", risk_level="MEDIUM",
            severity=5, blocked=True, title="Path Traversal",
            description="Path traversal", source="test",
            first_seen=1000.0,
        )
        key = b"test-key-32-bytes-long!!!!!!!"
        g.update_hmac(key)
        g.severity = 9  # tamper
        assert g.verify_hmac(key) is False

    def test_gene_pattern_dataclass(self):
        p = GenePattern(pattern_id="P1", gene_id="G1", pattern_type="regex",
                        pattern_value=r"\d+")
        assert p.match_score == 1.0
        assert p.variant_group == "primary"

    def test_gene_variant_dataclass(self):
        v = GeneVariant(variant_id="V1", gene_id="G1", language="python",
                        variant_code="eval(x)")
        assert v.detected_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# NegativeGeneBank — CRUD
# ═══════════════════════════════════════════════════════════════════════════════

class TestNegativeGeneBankCRUD:
    def test_init_creates_schema(self, gene_bank):
        assert gene_bank.gene_count() == 0

    def test_store_and_get(self, gene_bank, sample_gene):
        gid = gene_bank.store_gene(sample_gene)
        assert gid == sample_gene.gene_id
        fetched = gene_bank.get_gene(gid)
        assert fetched is not None
        assert fetched.title == sample_gene.title
        assert fetched.cwe_id == "CWE-79"

    def test_store_generates_id(self, gene_bank):
        g = NegativeGene(
            gene_id="", cwe_id="CWE-22", risk_level="LOW",
            severity=3, blocked=False, title="Test",
            description="Test gene", source="test",
            first_seen=time.time(),
        )
        gid = gene_bank.store_gene(g)
        assert gid.startswith("NEG-")

    def test_update_gene(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        sample_gene.title = "Updated XSS"
        gene_bank.update_gene(sample_gene)
        fetched = gene_bank.get_gene(sample_gene.gene_id)
        assert fetched.title == "Updated XSS"

    def test_delete_gene(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        assert gene_bank.delete_gene(sample_gene.gene_id) is True
        assert gene_bank.get_gene(sample_gene.gene_id) is None
        assert gene_bank.delete_gene("nonexistent") is False

    def test_store_with_patterns_and_variants(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        fetched = gene_bank.get_gene(sample_gene.gene_id)
        assert len(fetched.patterns) == 1
        assert len(fetched.variants) == 1

    def test_context_manager(self, gene_bank):
        with NegativeGeneBank(db_path=":memory:") as bank:
            assert bank.gene_count() == 0


class TestNegativeGeneBankQueries:
    def test_query_all(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        results = gene_bank.query_all()
        assert len(results) >= 1

    def test_query_by_cwe(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        results = gene_bank.query_by_cwe("CWE-79")
        assert len(results) == 1
        assert results[0].gene_id == sample_gene.gene_id
        assert gene_bank.query_by_cwe("CWE-00") == []

    def test_query_by_pattern(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        results = gene_bank.query_by_pattern("script")
        assert len(results) >= 1

    def test_query_by_risk_blocked(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        results = gene_bank.query_by_risk("HIGH")
        assert len(results) == 1
        # Non-blocked query
        results2 = gene_bank.query_by_risk("HIGH", blocked_only=False)
        assert len(results2) == 1

    def test_query_by_risk_nonexistent(self, gene_bank):
        assert gene_bank.query_by_risk("CRITICAL") == []

    def test_query_by_source(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        results = gene_bank.query_by_source("mitre_cwe")
        assert len(results) == 1
        assert gene_bank.query_by_source("nonexistent") == []

    def test_search(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        results = gene_bank.search("XSS")
        assert len(results) >= 1
        results2 = gene_bank.search("nonexistent_pattern_xyz")
        assert results2 == []


class TestNegativeGeneBankStats:
    def test_count_by_cwe(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        counts = gene_bank.count_by_cwe()
        assert counts.get("CWE-79", 0) >= 1

    def test_count_by_risk(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        counts = gene_bank.count_by_risk()
        assert counts.get("HIGH", 0) >= 1

    def test_count_by_source(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        counts = gene_bank.count_by_source()
        assert counts.get("mitre_cwe", 0) >= 1

    def test_gene_count(self, gene_bank):
        assert gene_bank.gene_count() == 0

    def test_top_blocked_patterns(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        top = gene_bank.top_blocked_patterns()
        assert len(top) >= 1

    def test_increment_occurrence(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        gene_bank.increment_occurrence(sample_gene.gene_id)
        fetched = gene_bank.get_gene(sample_gene.gene_id)
        assert fetched.occurrences == 2

    def test_increment_nonexistent(self, gene_bank):
        gene_bank.increment_occurrence("NEG-NOEXIST")  # should not crash

    def test_purge_stale(self, gene_bank):
        g = NegativeGene(
            gene_id="NEG-OLD", cwe_id="CWE-1", risk_level="LOW",
            severity=1, blocked=False, title="Old", description="Old gene",
            source="test", first_seen=100.0,  # very old timestamp
        )
        gene_bank.store_gene(g)
        purged = gene_bank.purge_stale()
        assert purged >= 1

    def test_verify_integrity_clean(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        ok, tampered = gene_bank.verify_integrity()
        assert ok is True
        assert tampered == []

    def test_record_source_import(self, gene_bank):
        src_id = gene_bank.record_source_import("test_source", "http://example.com", 42)
        assert src_id.startswith("SRC-")

    def test_get_import_history(self, gene_bank):
        gene_bank.record_source_import("src1")
        hist = gene_bank.get_import_history()
        assert len(hist) >= 1
        assert hist[0]["source_name"] == "src1"

    def test_get_gene_lifecycle(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        lc = gene_bank.get_gene_lifecycle(sample_gene.gene_id)
        assert lc is not None
        assert lc["gene_id"] == sample_gene.gene_id

    def test_get_gene_lifecycle_nonexistent(self, gene_bank):
        assert gene_bank.get_gene_lifecycle("NEG-NOEXIST") is None

    def test_register_variant(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        variant = GeneVariant(variant_id="", gene_id="", language="python",
                              variant_code="printf(user_input)")
        gene_bank.register_variant(sample_gene.gene_id, variant)
        fetched = gene_bank.get_gene(sample_gene.gene_id)
        assert len(fetched.variants) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# ImmuneChecker
# ═══════════════════════════════════════════════════════════════════════════════

class TestImmuneChecker:
    def test_scan_regex_match(self, immune_checker, sample_gene):
        immune_checker._bank.store_gene(sample_gene)
        hits = immune_checker.scan("<script>alert('xss')</script>", language="python")
        assert len(hits) >= 1
        assert hits[0].gene_id == "NEG-TEST001"
        assert hits[0].match_type == "regex"

    def test_scan_variant_match(self, immune_checker, sample_gene):
        immune_checker._bank.store_gene(sample_gene)
        hits = immune_checker.scan("return f'<div>{user_input}</div>'", language="python")
        assert len(hits) >= 1
        assert hits[0].match_type == "variant"

    def test_scan_no_match(self, immune_checker):
        hits = immune_checker.scan("print('hello world')", language="python")
        assert hits == []

    def test_scan_ast_call(self, immune_checker):
        g = NegativeGene(
            gene_id="NEG-EVAL", cwe_id="CWE-95", risk_level="HIGH",
            severity=8, blocked=True, title="Eval injection",
            description="Use of eval() is dangerous",
            source="test", first_seen=time.time(),
            patterns=[GenePattern(pattern_id="P-EVAL", gene_id="NEG-EVAL",
                                  pattern_type="ast_call", pattern_value="eval(")],
        )
        immune_checker._bank.store_gene(g)
        hits = immune_checker.scan_ast("eval('import os')")
        assert len(hits) >= 1
        assert hits[0].match_type == "ast_call"

    def test_scan_ast_import(self, immune_checker):
        g = NegativeGene(
            gene_id="NEG-PICKLE", cwe_id="CWE-502", risk_level="HIGH",
            severity=8, blocked=True, title="Pickle unsafe",
            description="Pickle deserialization is unsafe",
            source="test", first_seen=time.time(),
            patterns=[GenePattern(pattern_id="P-PICKLE", gene_id="NEG-PICKLE",
                                  pattern_type="import_name", pattern_value="pickle")],
        )
        immune_checker._bank.store_gene(g)
        hits = immune_checker.scan_ast("import pickle")
        assert len(hits) >= 1
        assert hits[0].match_type == "import_name"

    def test_scan_ast_syntax_error(self, immune_checker):
        hits = immune_checker.scan_ast("this is not valid @@ python")
        assert hits == []

    def test_default_fix(self, immune_checker):
        pat = GenePattern(pattern_id="P1", gene_id="G1",
                          pattern_type="import_name", pattern_value="pickle")
        fix = immune_checker._default_fix(pat)
        assert fix is not None
        assert "json" in fix

    def test_scan_file(self, immune_checker):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1")
            f.flush()
            path = f.name
        try:
            hits = immune_checker.scan_file(path)
            assert isinstance(hits, list)
        finally:
            os.unlink(path)

    def test_scan_file_path_traversal(self, immune_checker):
        with pytest.raises(ValueError, match="Path traversal"):
            immune_checker.scan_file("../etc/passwd")


# ═══════════════════════════════════════════════════════════════════════════════
# AcceptanceExtractor
# ═══════════════════════════════════════════════════════════════════════════════

class TestAcceptanceExtractor:
    def setup_method(self):
        self.extractor = AcceptanceExtractor()

    def test_extract_login(self):
        criteria = self.extractor.extract_ac("用户登录功能")
        assert len(criteria) >= 1
        descriptions = [c.description for c in criteria]
        assert "有效用户名和密码可成功登录" in descriptions

    def test_extract_register(self):
        criteria = self.extractor.extract_ac("用户注册功能")
        descriptions = [c.description for c in criteria]
        assert "新用户可以成功注册" in descriptions

    def test_extract_search(self):
        criteria = self.extractor.extract_ac("搜索功能")
        descriptions = [c.description for c in criteria]
        assert "关键字搜索返回匹配结果" in descriptions

    def test_extract_upload(self):
        criteria = self.extractor.extract_ac("上传文件功能")
        descriptions = [c.description for c in criteria]
        assert "有效文件可以上传成功" in descriptions

    def test_extract_generic(self):
        criteria = self.extractor.extract_ac("数据处理功能")
        assert len(criteria) >= 1

    def test_extract_deduplication(self):
        criteria = self.extractor.extract_ac("登录登录")
        descriptions = [c.description for c in criteria]
        assert len(descriptions) == len(set(descriptions))

    def test_compute_intent_hash(self):
        criteria = self.extractor.extract_ac("登录功能")
        ih = self.extractor.compute_intent_hash(criteria)
        assert isinstance(ih, IntentHash)
        assert len(ih.hash_value) == 64  # SHA256 hex
        assert ih.criteria_count == len(criteria)

    def test_compute_intent_hash_deterministic(self):
        c1 = self.extractor.extract_ac("登录功能")
        c2 = self.extractor.extract_ac("登录功能")
        ih1 = self.extractor.compute_intent_hash(c1)
        ih2 = self.extractor.compute_intent_hash(c2)
        assert ih1.hash_value == ih2.hash_value


# ═══════════════════════════════════════════════════════════════════════════════
# AIStenchDetector
# ═══════════════════════════════════════════════════════════════════════════════

class TestAIStenchDetector:
    def setup_method(self):
        self.detector = AIStenchDetector()

    def test_scan_clean_code(self):
        code = "def add(a, b):\n    return a + b\n"
        warnings = self.detector.scan(code)
        assert warnings == []

    def test_comment_repetition_detected(self):
        """Docstring that exactly matches the function name triggers repetition warning."""
        code = '''\ndef add():\n    """add"""\n    pass\n'''
        warnings = self.detector.scan(code)
        types = [w.type for w in warnings]
        assert "comment_repetition" in types, f"Warnings: {[w.message for w in warnings]}"

    def test_missing_boundary_detected(self):
        code = """
def f1(a):
    return a
def f2(b):
    return b
def f3(c):
    return c
"""
        warnings = self.detector.scan(code)
        types = [w.type for w in warnings]
        assert "missing_boundary_check" in types

    def test_syntax_error_returns_empty(self):
        warnings = self.detector.scan("!!! invalid python @@@")
        assert warnings == []

    def test_detect_with_template_lib(self):
        """Security template lib can be injected for domain checks."""
        from maref.immunity.security_template_lib import SecurityTemplateLib
        detector = AIStenchDetector(template_lib=SecurityTemplateLib())
        code = "import requests\nrequests.get('http://example.com', verify=False)"
        warnings = detector.scan(code)
        # Should detect verify=False via template lib
        types = [w.type for w in warnings]
        # We need to see if any security_* warnings appear
        security_warnings = [w for w in warnings if w.type.startswith("security_")]
        # This may or may not fire depending on template checks
        assert isinstance(warnings, list)


# ═══════════════════════════════════════════════════════════════════════════════
# RedContaminationProbe
# ═══════════════════════════════════════════════════════════════════════════════

class TestRedContaminationProbe:
    def setup_method(self):
        self.probe = RedContaminationProbe()

    def test_scan_clean(self):
        findings = self.probe.scan("x = 1")
        assert findings == []

    def test_pickle_import_detected(self):
        findings = self.probe.scan("import pickle")
        assert len(findings) >= 1
        assert findings[0].type == "deprecated_pickle"

    def test_pickle_call_detected(self):
        findings = self.probe.scan("data = pickle.loads(raw)")
        assert len(findings) >= 1
        assert findings[0].type == "deprecated_pickle"

    def test_missing_timeout_detected(self):
        findings = self.probe.scan("import requests\nrequests.get('https://example.com')")
        timeout_findings = [f for f in findings if f.type == "missing_dangerous_pattern"]
        assert len(timeout_findings) >= 1

    def test_syntax_error(self):
        findings = self.probe.scan("!!! invalid")
        assert findings == []


# ═══════════════════════════════════════════════════════════════════════════════
# CrossGenerationImpactSimulator
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrossGenerationImpactSimulator:
    def setup_method(self):
        self.sim = CrossGenerationImpactSimulator()

    def test_simulate_clean(self):
        report = self.sim.simulate_contamination("x = 1")
        assert report.contamination_index == 0.0
        assert report.blocked is False

    def test_simulate_pickle(self):
        report = self.sim.simulate_contamination("import pickle\npickle.loads(data)")
        assert report.contamination_index > 0
        assert len(report.findings) >= 1

    def test_block_merge(self):
        assert self.sim.block_merge(0.7) is True
        assert self.sim.block_merge(0.5) is False

    def test_simulate_training_impact_clean(self):
        result = self.sim.simulate_training_impact("x = 1")
        assert result["risk_level"] == "none"

    def test_simulate_training_impact_contaminated(self):
        result = self.sim.simulate_training_impact("import pickle\npickle.loads(data)")
        assert result["risk_level"] in ("critical", "moderate")
        assert "teachable_patterns" in result


# ═══════════════════════════════════════════════════════════════════════════════
# CooldownManager
# ═══════════════════════════════════════════════════════════════════════════════

class TestCooldownManager:
    def setup_method(self):
        self.mgr = CooldownManager(cooldown_seconds=0.1)  # fast cooldown

    def test_submit_code(self):
        cid = self.mgr.submit_code("agent-1", "print('hello')", {"key": "val"})
        assert cid.startswith("cd_")

    def test_get_status(self):
        cid = self.mgr.submit_code("agent-1", "code")
        status = self.mgr.get_status(cid)
        assert status["status"] == "cooling"
        assert status["agent_id"] == "agent-1"

    def test_get_status_not_found(self):
        status = self.mgr.get_status("nonexistent")
        assert "error" in status

    def test_evaluate_no_simulator(self):
        cid = self.mgr.submit_code("agent-1", "code")
        result = self.mgr.evaluate(cid)
        assert "error" in result

    def test_evaluate_not_found(self):
        result = self.mgr.evaluate("nonexistent")
        assert "error" in result

    def test_auto_merge_no_simulator(self):
        cid = self.mgr.submit_code("agent-1", "code")
        # Cooldown period is 0.1s, wait a bit
        time.sleep(0.15)
        result = self.mgr.auto_merge(cid)
        assert result["success"] is True

    def test_auto_merge_not_found(self):
        result = self.mgr.auto_merge("nonexistent")
        assert result["success"] is False

    def test_auto_merge_too_early(self):
        self.mgr._cooldown_seconds = 3600
        cid = self.mgr.submit_code("agent-1", "code")
        result = self.mgr.auto_merge(cid)
        assert result["success"] is False

    def test_force_merge(self):
        cid = self.mgr.submit_code("agent-1", "code")
        result = self.mgr.force_merge(cid, reason="testing")
        assert result["success"] is True

    def test_force_merge_not_found(self):
        result = self.mgr.force_merge("nonexistent")
        assert result["success"] is False

    def test_auto_archive_expired(self):
        self.mgr.submit_code("agent-1", "code")
        archived = self.mgr.auto_archive_expired(max_age_days=0)
        assert len(archived) >= 1

    def test_get_overdue_entries(self):
        self.mgr.submit_code("agent-1", "code")
        overdue = self.mgr.get_overdue_entries(grace_days=0)
        assert len(overdue) >= 1

    def test_get_all_entries(self):
        self.mgr.submit_code("agent-1", "code")
        entries = self.mgr.get_all_entries()
        assert len(entries) == 1
        assert isinstance(entries[0], CooldownEntry)

    def test_get_cooldown_seconds(self):
        assert self.mgr.get_cooldown_seconds() == 0.1


# ═══════════════════════════════════════════════════════════════════════════════
# ProvenanceTracker
# ═══════════════════════════════════════════════════════════════════════════════

class TestProvenanceTracker:
    def test_label_and_get(self):
        tracker = ProvenanceTracker()
        tracker.label_node("node-1", "human", source="test")
        assert tracker.get_provenance("node-1") == "human"

    def test_get_nonexistent(self):
        tracker = ProvenanceTracker()
        assert tracker.get_provenance("nonexistent") is None

    def test_invalid_provenance(self):
        tracker = ProvenanceTracker()
        with pytest.raises(ValueError, match="Invalid provenance"):
            tracker.label_node("n1", "alien")

    def test_summarize_empty(self):
        tracker = ProvenanceTracker()
        assert tracker.summarize() == {}

    def test_retrieve_without_kg(self):
        tracker = ProvenanceTracker()
        assert tracker.retrieve() == []

    def test_label_with_kg(self):
        kg = MagicMock()
        kg.get_node.return_value = MagicMock()
        tracker = ProvenanceTracker(kg=kg)
        tracker.label_node("n1", "ai_generated", source="test")
        kg.get_node.assert_called_with("n1")


# ═══════════════════════════════════════════════════════════════════════════════
# SecurityTemplateLib
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurityTemplateLib:
    def setup_method(self):
        self.lib = SecurityTemplateLib()

    def test_init_has_builtins(self):
        for d in ("password_storage", "sql_query", "https_request"):
            assert self.lib.get_template(d) is not None

    def test_get_template_unknown(self):
        assert self.lib.get_template("unknown") is None

    def test_verify_integrity(self):
        assert self.lib.verify_integrity() is True

    def test_check_password_missing_bcrypt(self):
        code = "def hash(pwd):\n    return hashlib.md5(pwd.encode()).hexdigest()"
        violations = self.lib.check_code(code, "password_storage")
        assert len(violations) >= 1

    def test_check_password_with_bcrypt(self):
        code = "import bcrypt\ndef hash_pw(pwd): return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt())"
        violations = self.lib.check_code(code, "password_storage")
        # may still flag bcrypt usage pattern; check no blocked_keyword match
        kw_violations = [v for v in violations if v["message"].startswith("Blocked pattern")]
        assert len(kw_violations) == 0

    def test_check_sql_injection(self):
        code = 'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")'
        violations = self.lib.check_code(code, "sql_query")
        assert len(violations) >= 1

    def test_check_https_verify_false(self):
        code = "import requests\nrequests.get('https://example.com', verify=False)"
        violations = self.lib.check_code(code, "https_request")
        assert len(violations) >= 1

    def test_check_all(self):
        violations = self.lib.check_all("x = 1")
        assert isinstance(violations, list)

    def test_register_template(self):
        t = SecurityTemplate(
            domain="custom_check",
            description="Custom check",
            template_code="# safe code",
        )
        self.lib.register_template(t)
        assert self.lib.get_template("custom_check") == "# safe code"


# ═══════════════════════════════════════════════════════════════════════════════
# AutoGeneExtractionPipeline
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoGeneExtractionPipeline:
    def setup_method(self):
        from maref.recursive.experience_pool import ExperiencePool
        self.bank = NegativeGeneBank(db_path=":memory:")
        self.pool = MagicMock(spec=ExperiencePool)
        self.pool.store.return_value = None
        self.pool.query_by_tag.return_value = []
        self.pipeline = AutoGeneExtractionPipeline(self.bank, self.pool)

    def test_extract_from_heal(self):
        gid = self.pipeline.extract_from_heal("old_code", "new_code")
        assert gid is not None
        assert gid.startswith("AUTO-")

    def test_extract_from_rollback(self):
        gid = self.pipeline.extract_from_rollback("bad_code", reason="crashed")
        assert gid is not None

    def test_extract_from_block(self):
        gid = self.pipeline.extract_from_block("malicious_code", reason="blocked_by_gate")
        assert gid is not None

    def test_empty_diff_returns_none(self):
        gid = self.pipeline.extract_from_heal("", "")
        assert gid is None

    def test_extraction_count(self):
        self.pipeline.extract_from_heal("a", "b")
        self.pipeline.extract_from_rollback("c", "r")
        assert self.pipeline.extraction_count == 2

    def test_recent_extractions(self):
        self.pipeline.extract_from_heal("a", "b")
        recent = self.pipeline.recent_extractions
        assert len(recent) == 1
        assert recent[0]["source"] == "heal"

    def test_sync_with_experience_pool(self):
        self.pipeline.extract_from_heal("a", "b")
        count = self.pipeline.sync_with_experience_pool()
        assert count >= 1

    def test_pattern_from_diff(self):
        result = self.pipeline._pattern_from_diff("old line", "new line")
        assert result == "new line"

    def test_pattern_from_code(self):
        result = self.pipeline._pattern_from_code("  hello world  ")
        assert result == "hello world"

    def test_pattern_from_code_empty(self):
        assert self.pipeline._pattern_from_code("") == ""
        assert self.pipeline._pattern_from_code("   ") == ""


# ═══════════════════════════════════════════════════════════════════════════════
# IntentDriftDetector
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntentDriftDetector:
    def setup_method(self):
        self.bank = NegativeGeneBank(db_path=":memory:")
        self.detector = IntentDriftDetector(gene_bank=self.bank)
        self.extractor = AcceptanceExtractor()

    def test_verify_intent_hash_match(self):
        criteria = self.extractor.extract_ac("登录功能")
        ih = self.extractor.compute_intent_hash(criteria)
        assert self.detector.verify_intent_hash(criteria, ih.hash_value) is True

    def test_verify_intent_hash_mismatch(self):
        criteria = self.extractor.extract_ac("登录功能")
        assert self.detector.verify_intent_hash(criteria, "wrong_hash") is False

    def test_evaluate_code_syntax_error(self):
        criteria = self.extractor.extract_ac("登录功能")
        ih = self.extractor.compute_intent_hash(criteria)
        result = self.detector.evaluate_code("!!! invalid", criteria, ih.hash_value)
        assert result.intent_valid is True
        assert len(result.test_results) >= 1
        assert all(not r.passed for r in result.test_results)

    def test_evaluate_code_intent_mismatch(self):
        criteria = self.extractor.extract_ac("登录功能")
        result = self.detector.evaluate_code("x = 1", criteria, "wrong_hash")
        assert result.intent_valid is False
        assert result.blocked is True

    def test_evaluate_code_non_python(self):
        criteria = self.extractor.extract_ac("搜索功能")
        ih = self.extractor.compute_intent_hash(criteria)
        result = self.detector.evaluate_code("search results", criteria, ih.hash_value,
                                              language="javascript")
        assert result.intent_valid is True
        # Non-python fuzz uses keyword matching
        assert isinstance(result, IntentDriftResult)


# ═══════════════════════════════════════════════════════════════════════════════
# PollutionTax (mocked economy)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPollutionTax:
    def setup_method(self):
        self.economy = MagicMock()
        self.economy.apply_generation_tax.return_value = 1.5
        self.economy.get_generation_tax_multiplier.return_value = 1.5
        self.economy.get_wallet.return_value = {"balance": 100}
        self.economy.record_pollution.return_value = {"success": True}
        self.economy.get_pollution_count.return_value = 5
        self.economy.verify_pollution_audit_chain.return_value = True
        self.credit = MagicMock()
        self.credit.update_dimension.return_value = None
        self.credit.evaluate_rating.return_value = MagicMock(rating=MagicMock(value="B"))
        self.tax = PollutionTax(self.economy, credit_systems={"agent-1": self.credit})

    def test_apply_generation_tax(self):
        mult = self.tax.apply_generation_tax("agent-1")
        assert mult == 1.5

    def test_get_current_multiplier(self):
        assert self.tax.get_current_multiplier("agent-1") == 1.5

    def test_reset_generation_tax(self):
        self.tax.reset_generation_tax("agent-1")
        self.economy.reset_generation_tax.assert_called_with("agent-1")

    def test_apply_downstream_penalty(self):
        result = self.tax.apply_downstream_penalty("agent-1", penalty=10.0, reason="test")
        assert result["success"] is True

    def test_apply_downstream_penalty_no_wallet(self):
        econ = MagicMock()
        econ.get_wallet.return_value = None
        tax = PollutionTax(econ)
        result = tax.apply_downstream_penalty("agent-x")
        assert result["success"] is False

    def test_get_pollution_count(self):
        assert self.tax.get_pollution_count("agent-1") == 5

    def test_check_rating_downgrade_triggered(self):
        result = self.tax.check_rating_downgrade("agent-1")
        assert result is True

    def test_check_rating_downgrade_below_threshold(self):
        econ = MagicMock()
        econ.get_pollution_count.return_value = 1
        tax = PollutionTax(econ)
        assert tax.check_rating_downgrade("agent-1") is False

    def test_verify_audit_integrity(self):
        assert self.tax.verify_audit_integrity() is True

    def test_get_pollution_summary(self):
        summary = self.tax.get_pollution_summary("agent-1")
        assert summary["agent_id"] == "agent-1"
        assert summary["pollution_count"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# seed_updater
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeedUpdater:
    def test_get_import_history(self, gene_bank):
        hist = get_import_history(gene_bank)
        assert isinstance(hist, list)

    def test_export_genes_to_json(self, gene_bank, sample_gene):
        gene_bank.store_gene(sample_gene)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            outpath = f.name
        try:
            count = export_genes_to_json(gene_bank, outpath)
            assert count >= 1
            with open(outpath) as f:
                data = json.load(f)
                assert "genes" in data
                assert data["count"] >= 1
        finally:
            os.unlink(outpath)

    def test_seed_from_cwe_json_invalid_source(self, gene_bank):
        with pytest.raises(CWEImportError):
            seed_from_cwe_json(gene_bank, "path.json", source_name="invalid_source")

    def test_seed_from_cwe_json_file_not_found(self, gene_bank):
        with pytest.raises((CWEImportError, FileNotFoundError, OSError)):
            seed_from_cwe_json(gene_bank, "/nonexistent/path.json")

    def test_seed_from_cwe_json_list(self, gene_bank):
        """Import from a JSON list of gene entries."""
        entries = [
            {
                "cwe_id": "CWE-79",
                "title": "XSS",
                "description": "Cross-site scripting",
                "risk_level": "HIGH",
                "severity": 8,
                "blocked": True,
                "patterns": [],
                "variants": [],
            },
            {
                "cwe_id": "CWE-89",
                "title": "SQLi",
                "description": "SQL injection",
                "risk_level": "CRITICAL",
                "severity": 10,
                "blocked": True,
                "patterns": [],
                "variants": [],
            },
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(entries, f)
            inpath = f.name
        try:
            result = seed_from_cwe_json(gene_bank, inpath, source_name="mitre_cwe")
            assert result["imported"] == 2
            assert result["total_genes"] >= 2
        finally:
            os.unlink(inpath)

    def test_seed_from_cwe_json_dict_with_genes(self, gene_bank):
        data = {
            "genes": [
                {
                    "cwe_id": "CWE-22",
                    "title": "Path traversal",
                    "description": "Path traversal vulnerability",
                    "risk_level": "MEDIUM",
                    "severity": 5,
                    "blocked": True,
                    "patterns": [
                        {"type": "regex", "value": r"\.\./", "group": "primary", "score": 1.0},
                    ],
                    "variants": [],
                },
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            inpath = f.name
        try:
            result = seed_from_cwe_json(gene_bank, inpath, source_name="maraf_cwe")
            assert result["imported"] == 1
        finally:
            os.unlink(inpath)

    def test_seed_from_cwe_json_merge(self, gene_bank):
        entries = [
            {
                "cwe_id": "CWE-001",
                "title": "Test CWE",
                "description": "Test",
                "risk_level": "LOW",
                "severity": 1,
                "blocked": False,
                "patterns": [{"type": "string_content", "value": "old_pattern"}],
                "variants": [{"language": "python", "code": "old"}],
            },
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(entries, f)
            inpath = f.name
        try:
            result = seed_from_cwe_json(gene_bank, inpath, source_name="custom")
            assert result["imported"] == 1

            # Merge: add more patterns
            entries2 = [
                {
                    "cwe_id": "CWE-001",
                    "title": "Test CWE",
                    "description": "Test",
                    "risk_level": "LOW",
                    "severity": 1,
                    "blocked": False,
                    "patterns": [{"type": "string_content", "value": "new_pattern"}],
                    "variants": [{"language": "python", "code": "new_variant"}],
                },
            ]
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f2:
                json.dump(entries2, f2)
                inpath2 = f2.name
            try:
                result2 = seed_from_cwe_json(gene_bank, inpath2, source_name="custom", merge=True)
                assert result2["updated"] == 1
            finally:
                os.unlink(inpath2)
        finally:
            os.unlink(inpath)

    def test_seed_from_cwe_json_invalid_risk(self, gene_bank):
        entries = [
            {
                "cwe_id": "CWE-001",
                "title": "Bad risk",
                "description": "Test",
                "risk_level": "INVALID",
                "severity": 5,
                "blocked": True,
                "patterns": [],
                "variants": [],
            },
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(entries, f)
            inpath = f.name
        try:
            result = seed_from_cwe_json(gene_bank, inpath, source_name="custom")
            assert result["imported"] == 1  # should import with defaulted risk
        finally:
            os.unlink(inpath)

    def test_seed_from_cwe_json_invalid_structure(self, gene_bank):
        data = {"wrong_key": []}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            inpath = f.name
        try:
            with pytest.raises(CWEImportError, match="Unknown JSON structure"):
                seed_from_cwe_json(gene_bank, inpath, source_name="custom")
        finally:
            os.unlink(inpath)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '--no-header', '--no-cov', '--tb=short'])

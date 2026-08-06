from __future__ import annotations

from maref.immunity.red_contamination_probe import ContaminationFinding, RedContaminationProbe
from maref.recursive.unified_audit import UnifiedAuditStore

PICKLE_IMPORT_CODE = """
import pickle

def save_data(data):
    with open("data.pkl", "wb") as f:
        pickle.dump(data, f)
"""

PICKLE_LOADS_CODE = """
import pickle

def load_user_input(data):
    return pickle.loads(data)
"""

PICKLE_SAFE_CODE = """
import json

def save_data(data):
    return json.dumps(data)
"""

WRONG_COMMENT_EVAL_CODE = """
# This is a production-grade secure implementation
result = eval(user_input)
"""

WRONG_COMMENT_MD5_CODE = """
# Secure MD5 encryption for passwords
import hashlib
hashed = hashlib.md5(password.encode()).hexdigest()
"""

WRONG_DOCSTRING_CODE = """
def encrypt(data):
    \"\"\"Enterprise-grade secure encryption using MD5.\"\"\"
    import hashlib
    return hashlib.md5(data.encode()).hexdigest()
"""

WRONG_DOCSTRING_OK_CODE = """
def add(a, b):
    \"\"\"Add two numbers together.\"\"\"
    return a + b
"""

MISSING_TIMEOUT_CODE = """
import requests

def fetch_data():
    return requests.get("https://api.example.com/data")
"""

TIMEOUT_PRESENT_CODE = """
import requests

def fetch_data():
    return requests.get("https://api.example.com/data", timeout=30)
"""

NO_REQUESTS_CODE = """
def fetch(url):
    print(f"fetching {url}")
"""


class TestRedContaminationProbePickle:
    """4.1-A1: Detect deprecated pickle serialization."""

    def test_pickle_import_detected(self):
        probe = RedContaminationProbe()
        findings = probe.scan(PICKLE_IMPORT_CODE)
        pickle_findings = [f for f in findings if f.type == "deprecated_pickle"]
        assert len(pickle_findings) >= 1

    def test_pickle_import_severity_pollution(self):
        probe = RedContaminationProbe()
        findings = probe.scan(PICKLE_IMPORT_CODE)
        pickle_findings = [f for f in findings if f.type == "deprecated_pickle"]
        assert all(f.severity == "POLLUTION" for f in pickle_findings)

    def test_pickle_loads_detected(self):
        probe = RedContaminationProbe()
        findings = probe.scan(PICKLE_LOADS_CODE)
        pickle_findings = [f for f in findings if f.type == "deprecated_pickle"]
        assert len(pickle_findings) >= 1

    def test_pickle_loads_message_informative(self):
        probe = RedContaminationProbe()
        findings = probe.scan(PICKLE_LOADS_CODE)
        pickle_findings = [f for f in findings if f.type == "deprecated_pickle"]
        assert all(len(f.message) > 10 for f in pickle_findings)

    def test_pickle_loads_has_suggestion(self):
        probe = RedContaminationProbe()
        findings = probe.scan(PICKLE_LOADS_CODE)
        pickle_findings = [f for f in findings if f.type == "deprecated_pickle"]
        assert all(f.suggestion for f in pickle_findings)

    def test_safe_json_returns_clean(self):
        probe = RedContaminationProbe()
        findings = probe.scan(PICKLE_SAFE_CODE)
        pickle_findings = [f for f in findings if f.type == "deprecated_pickle"]
        assert len(pickle_findings) == 0

    def test_pickle_call_detected(self):
        probe = RedContaminationProbe()
        findings = probe.scan(PICKLE_IMPORT_CODE)
        pickle_findings = [f for f in findings if f.type == "deprecated_pickle"]
        pickle_calls = [f for f in pickle_findings if "pickle." in f.message]
        assert len(pickle_calls) >= 1

    def test_pickle_finding_has_code_snippet(self):
        probe = RedContaminationProbe()
        findings = probe.scan(PICKLE_IMPORT_CODE)
        pickle_findings = [f for f in findings if f.type == "deprecated_pickle"]
        assert all(f.code_snippet for f in pickle_findings)


class TestRedContaminationProbeWrongComments:
    """4.1-A2: Detect 'professional but wrong' comment patterns."""

    def test_eval_with_authoritative_comment_detected(self):
        probe = RedContaminationProbe()
        findings = probe.scan(WRONG_COMMENT_EVAL_CODE)
        wrong_findings = [f for f in findings if f.type == "wrong_comment"]
        assert len(wrong_findings) >= 1

    def test_eval_finding_severity_pollution(self):
        probe = RedContaminationProbe()
        findings = probe.scan(WRONG_COMMENT_EVAL_CODE)
        wrong_findings = [f for f in findings if f.type == "wrong_comment"]
        assert all(f.severity == "POLLUTION" for f in wrong_findings)

    def test_md5_with_secure_comment_detected(self):
        probe = RedContaminationProbe()
        findings = probe.scan(WRONG_COMMENT_MD5_CODE)
        wrong_findings = [f for f in findings if f.type == "wrong_comment"]
        assert len(wrong_findings) >= 1

    def test_professional_docstring_with_dangerous_body(self):
        probe = RedContaminationProbe()
        findings = probe.scan(WRONG_DOCSTRING_CODE)
        wrong_findings = [f for f in findings if f.type == "wrong_comment"]
        assert len(wrong_findings) >= 1

    def test_honest_docstring_no_false_positive(self):
        probe = RedContaminationProbe()
        findings = probe.scan(WRONG_DOCSTRING_OK_CODE)
        wrong_findings = [f for f in findings if f.type == "wrong_comment"]
        assert len(wrong_findings) == 0

    def test_wrong_comment_has_suggestion(self):
        probe = RedContaminationProbe()
        findings = probe.scan(WRONG_COMMENT_EVAL_CODE)
        wrong_findings = [f for f in findings if f.type == "wrong_comment"]
        assert all(f.suggestion for f in wrong_findings)


class TestRedContaminationProbeMissingTimeout:
    """4.1-A3: Detect missing dangerous patterns like no timeout."""

    def test_missing_timeout_detected(self):
        probe = RedContaminationProbe()
        findings = probe.scan(MISSING_TIMEOUT_CODE)
        timeout_findings = [f for f in findings if f.type == "missing_dangerous_pattern"]
        assert len(timeout_findings) >= 1

    def test_missing_timeout_severity_pollution(self):
        probe = RedContaminationProbe()
        findings = probe.scan(MISSING_TIMEOUT_CODE)
        timeout_findings = [f for f in findings if f.type == "missing_dangerous_pattern"]
        assert all(f.severity == "POLLUTION" for f in timeout_findings)

    def test_timeout_present_returns_clean(self):
        probe = RedContaminationProbe()
        findings = probe.scan(TIMEOUT_PRESENT_CODE)
        timeout_findings = [f for f in findings if f.type == "missing_dangerous_pattern"]
        assert len(timeout_findings) == 0

    def test_no_requests_call_returns_clean(self):
        probe = RedContaminationProbe()
        findings = probe.scan(NO_REQUESTS_CODE)
        timeout_findings = [f for f in findings if f.type == "missing_dangerous_pattern"]
        assert len(timeout_findings) == 0

    def test_missing_timeout_has_suggestion(self):
        probe = RedContaminationProbe()
        findings = probe.scan(MISSING_TIMEOUT_CODE)
        timeout_findings = [f for f in findings if f.type == "missing_dangerous_pattern"]
        assert all(f.suggestion for f in timeout_findings)

    def test_missing_timeout_mentions_timeout_in_message(self):
        probe = RedContaminationProbe()
        findings = probe.scan(MISSING_TIMEOUT_CODE)
        timeout_findings = [f for f in findings if f.type == "missing_dangerous_pattern"]
        assert all("timeout" in f.message.lower() for f in timeout_findings)

    def test_syntax_error_returns_empty(self):
        probe = RedContaminationProbe()
        findings = probe.scan("def broken(")
        assert len(findings) == 0

    def test_empty_code_returns_empty(self):
        probe = RedContaminationProbe()
        findings = probe.scan("")
        assert len(findings) == 0


class TestRedContaminationProbeScanIntegration:
    """Integration: scan returns all finding types."""

    def test_scan_returns_multiple_types(self):
        code = PICKLE_IMPORT_CODE + "\n" + WRONG_COMMENT_EVAL_CODE + "\n" + MISSING_TIMEOUT_CODE
        probe = RedContaminationProbe()
        findings = probe.scan(code)
        types = {f.type for f in findings}
        assert "deprecated_pickle" in types
        assert "wrong_comment" in types
        assert "missing_dangerous_pattern" in types

    def test_scan_returns_all_findings(self):
        code = PICKLE_IMPORT_CODE + "\n" + WRONG_COMMENT_EVAL_CODE + "\n" + MISSING_TIMEOUT_CODE
        probe = RedContaminationProbe()
        findings = probe.scan(code)
        assert len(findings) >= 3

    def test_clean_code_returns_empty(self):
        code = """
def add(a, b):
    \"\"\"Add two numbers.\"\"\"
    return a + b
"""
        probe = RedContaminationProbe()
        findings = probe.scan(code)
        assert len(findings) == 0


class TestRedContaminationProbeAuditStore:
    """4.1-A4: Pollution detection results written to UnifiedAuditStore."""

    def test_audit_store_gets_records(self):
        store = UnifiedAuditStore()
        probe = RedContaminationProbe(audit_store=store)
        probe.scan(PICKLE_IMPORT_CODE)
        assert store.count() >= 1

    def test_audit_store_event_type(self):
        store = UnifiedAuditStore()
        probe = RedContaminationProbe(audit_store=store)
        probe.scan(PICKLE_IMPORT_CODE)
        events = store.stats_by_event_type()
        pickle_events = [k for k in events if "pickle" in k]
        assert len(pickle_events) >= 1

    def test_audit_store_no_store_no_error(self):
        probe = RedContaminationProbe()
        findings = probe.scan(PICKLE_IMPORT_CODE)
        assert len(findings) >= 1

    def test_audit_store_counts_per_finding(self):
        store = UnifiedAuditStore()
        probe = RedContaminationProbe(audit_store=store)
        code = PICKLE_IMPORT_CODE + "\n" + MISSING_TIMEOUT_CODE
        findings = probe.scan(code)
        assert store.count() == len(findings)

    def test_audit_store_writes_decision_pollution(self):
        store = UnifiedAuditStore()
        probe = RedContaminationProbe(audit_store=store)
        probe.scan(PICKLE_IMPORT_CODE)
        records = store.all()
        assert all(r.decision == "POLLUTION" for r in records)

    def test_audit_store_clean_code_writes_nothing(self):
        store = UnifiedAuditStore()
        probe = RedContaminationProbe(audit_store=store)
        probe.scan("def add(a, b): return a + b")
        assert store.count() == 0

    def test_audit_store_module_source(self):
        store = UnifiedAuditStore()
        probe = RedContaminationProbe(audit_store=store)
        probe.scan(PICKLE_IMPORT_CODE)
        records = store.all()
        assert all(r.source_module == "red_contamination_probe" for r in records)

    def test_audit_store_layer_is_execution(self):
        store = UnifiedAuditStore()
        probe = RedContaminationProbe(audit_store=store)
        probe.scan(PICKLE_IMPORT_CODE)
        records = store.all()
        assert all(r.layer == "execution" for r in records)


class TestRedContaminationProbeSecurityCritical:
    """@security_critical decorator on scan."""

    def test_scan_has_security_critical_marker(self):
        probe = RedContaminationProbe()
        assert hasattr(probe.scan, "_maref_security_critical")


class TestContaminationFinding:
    """ContaminationFinding dataclass."""

    def test_finding_creation(self):
        f = ContaminationFinding(
            type="test", severity="POLLUTION", line=1, message="msg", suggestion="sug"
        )
        assert f.type == "test"
        assert f.severity == "POLLUTION"
        assert f.line == 1
        assert f.message == "msg"
        assert f.suggestion == "sug"

    def test_finding_default_code_snippet_empty(self):
        f = ContaminationFinding(
            type="test", severity="POLLUTION", line=1, message="msg", suggestion="sug"
        )
        assert f.code_snippet == ""

    def test_finding_with_code_snippet(self):
        f = ContaminationFinding(
            type="test",
            severity="POLLUTION",
            line=1,
            message="msg",
            suggestion="sug",
            code_snippet="import pickle",
        )
        assert f.code_snippet == "import pickle"

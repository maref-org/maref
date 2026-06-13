from __future__ import annotations

import os

import pytest

from maref.immunity.security_template_lib import (
    SecurityTemplate,
    SecurityTemplateLib,
)


BCRYPT_GOOD_CODE = """
import bcrypt

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()
"""

BCRYPT_BAD_CODE = """
import hashlib

def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()
"""

BCRYPT_NO_PASSWORD_CODE = """
def add(a: int, b: int) -> int:
    return a + b
"""

SQL_PARAMETERIZED_CODE = """
def get_user(user_id: int) -> dict | None:
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()
"""

SQL_CONCAT_CODE = """
def get_user(user_id: int) -> dict | None:
    query = "SELECT * FROM users WHERE id = " + str(user_id)
    cursor.execute(query)
    return cursor.fetchone()
"""

SQL_FSTRING_CODE = """
def get_user(user_id: int) -> dict | None:
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    return cursor.fetchone()
"""

HTTPS_VERIFY_TRUE_CODE = """
import requests
def fetch_data():
    return requests.get("https://api.example.com/data", verify=True, timeout=30)
"""

HTTPS_VERIFY_FALSE_CODE = """
import requests
def fetch_data():
    return requests.get("https://api.example.com/data", verify=False)
"""

HTTPS_NO_VERIFY_CODE = """
import requests
def fetch_data():
    return requests.get("https://api.example.com/data", timeout=10)
"""

HTTPS_HTTP_NO_VERIFY_CODE = """
import requests
def fetch_data():
    return requests.get("http://api.example.com/data", timeout=10)
"""


class TestSecurityTemplateLibHMAC:
    """M3.2-A4: Template library HMAC integrity protection."""

    def test_verify_integrity_returns_true_for_builtins(self):
        lib = SecurityTemplateLib()
        assert lib.verify_integrity() is True

    def test_tampered_template_detected(self):
        lib = SecurityTemplateLib()
        template = lib._templates["password_storage"]
        template.template_code = template.template_code + "\n# EVIL"
        template.hmac = "tampered_hmac_value"
        assert lib.verify_integrity() is False

    def test_register_sets_hmac(self):
        lib = SecurityTemplateLib()
        tmpl = SecurityTemplate(
            domain="custom_test",
            description="test",
            template_code="print('hello')",
        )
        lib.register_template(tmpl)
        assert tmpl.hmac
        assert len(tmpl.hmac) == 64

    def test_hmac_different_for_different_content(self):
        lib = SecurityTemplateLib()
        tmpl_a = SecurityTemplate(domain="a", description="a", template_code="code_a")
        tmpl_b = SecurityTemplate(domain="b", description="b", template_code="code_b")
        lib.register_template(tmpl_a)
        lib.register_template(tmpl_b)
        assert tmpl_a.hmac != tmpl_b.hmac

    def test_env_key_changes_hmac(self):
        os.environ["MAREF_TEMPLATE_HMAC_KEY"] = "custom-test-key"
        try:
            lib = SecurityTemplateLib()
            t = lib._templates["password_storage"]
            assert t.hmac
            assert len(t.hmac) == 64
        finally:
            del os.environ["MAREF_TEMPLATE_HMAC_KEY"]

    def test_verify_integrity_after_unregistered_modification(self):
        lib = SecurityTemplateLib()
        original = lib._templates["sql_query"].hmac
        lib._templates["sql_query"].template_code = "EVIL"
        assert lib.verify_integrity() is False
        assert lib._templates["sql_query"].hmac == original


class TestSecurityTemplateLibPassword:
    """M3.2-A1: Password storage must use bcrypt template."""

    def test_bcrypt_good_code_no_violations(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(BCRYPT_GOOD_CODE, "password_storage")
        assert len(violations) == 0

    def test_bcrypt_bad_code_violation(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(BCRYPT_BAD_CODE, "password_storage")
        assert len(violations) >= 1

    def test_bcrypt_bad_code_message_mentions_bcrypt(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(BCRYPT_BAD_CODE, "password_storage")
        assert any("bcrypt" in v["message"].lower() for v in violations)

    def test_bcrypt_bad_code_suggestion_contains_template(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(BCRYPT_BAD_CODE, "password_storage")
        assert any("bcrypt" in v["suggestion"] for v in violations)

    def test_no_password_mention_returns_clean(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(BCRYPT_NO_PASSWORD_CODE, "password_storage")
        assert len(violations) == 0

    def test_bcrypt_blocked_keyword_md5_detected(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(BCRYPT_BAD_CODE, "password_storage")
        md5_violations = [v for v in violations if "md5" in v["message"].lower()]
        assert len(md5_violations) >= 1

    def test_bcrypt_import_detected_via_different_syntax(self):
        lib = SecurityTemplateLib()
        code = """
from bcrypt import hashpw, gensalt
def hash_pw(p: str) -> str:
    salt = gensalt()
    return hashpw(p.encode(), salt).decode()
"""
        violations = lib.check_code(code, "password_storage")
        assert len(violations) == 0

    def test_bcrypt_direct_call_detected(self):
        lib = SecurityTemplateLib()
        code = """
import something
def hash_pw(p: str) -> str:
    return hashpw(p.encode(), gensalt())
"""
        violations = lib.check_code(code, "password_storage")
        assert len(violations) == 0


class TestSecurityTemplateLibSQL:
    """M3.2-A2: SQL must use parameterized queries."""

    def test_parameterized_sql_no_violations(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(SQL_PARAMETERIZED_CODE, "sql_query")
        assert len(violations) == 0

    def test_string_concat_sql_violation(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(SQL_CONCAT_CODE, "sql_query")
        assert len(violations) >= 1

    def test_fstring_sql_violation(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(SQL_FSTRING_CODE, "sql_query")
        assert len(violations) >= 1

    def test_concat_violation_message_mentions_parameterized(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(SQL_CONCAT_CODE, "sql_query")
        assert any("parameterized" in v["message"].lower() for v in violations)

    def test_fstring_violation_line_number(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(SQL_FSTRING_CODE, "sql_query")
        assert all(v.get("line", 0) > 0 for v in violations)

    def test_no_sql_execute_returns_clean(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code("def add(a, b): return a + b", "sql_query")
        assert len(violations) == 0

    def test_sql_execute_with_no_args_returns_clean(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code("execute()", "sql_query")
        assert len(violations) == 0

    def test_syntax_error_returns_clean(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code("def broken(", "sql_query")
        assert len(violations) == 0

    def test_blocked_keyword_fstring_detected(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(SQL_FSTRING_CODE, "sql_query")
        fstring_violations = [v for v in violations if "f" in v["message"]]
        assert len(fstring_violations) >= 1

    def test_blocked_keyword_concat_detected(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(SQL_CONCAT_CODE, "sql_query")
        concat_violations = [v for v in violations if "concatenation" in v["message"].lower()]
        assert len(concat_violations) >= 1


class TestSecurityTemplateLibHTTPS:
    """M3.2-A3: HTTPS requests must have verify=True."""

    def test_verify_true_no_violations(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(HTTPS_VERIFY_TRUE_CODE, "https_request")
        assert len(violations) == 0

    def test_verify_false_violation(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(HTTPS_VERIFY_FALSE_CODE, "https_request")
        assert len(violations) >= 1

    def test_verify_false_blocked_message(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(HTTPS_VERIFY_FALSE_CODE, "https_request")
        assert any("verify=False" in v["message"] for v in violations)

    def test_no_verify_violation(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(HTTPS_NO_VERIFY_CODE, "https_request")
        assert len(violations) >= 1

    def test_no_verify_message_mentions_explicit(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(HTTPS_NO_VERIFY_CODE, "https_request")
        assert any("explicit" in v["message"].lower() for v in violations)

    def test_http_url_skipped(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(HTTPS_HTTP_NO_VERIFY_CODE, "https_request")
        assert len(violations) == 0

    def test_syntax_error_returns_clean(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code("def broken(", "https_request")
        assert len(violations) == 0

    def test_no_requests_call_returns_clean(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code("print('hello')", "https_request")
        assert len(violations) == 0

    def test_verify_true_with_name_constant(self):
        lib = SecurityTemplateLib()
        code = '''
import requests
r = requests.get("https://example.com", verify=True)
'''
        violations = lib.check_code(code, "https_request")
        assert len(violations) == 0

    def test_line_number_accurate(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code(HTTPS_VERIFY_FALSE_CODE, "https_request")
        assert all(v.get("line", 0) > 0 for v in violations)


class TestSecurityTemplateLibCheckAll:
    """Integration: check_all scans all domains."""

    def test_check_all_returns_empty_for_good_code(self):
        lib = SecurityTemplateLib()
        violations = lib.check_all(BCRYPT_GOOD_CODE)
        assert len(violations) == 0

    def test_check_all_detects_password_violations(self):
        lib = SecurityTemplateLib()
        violations = lib.check_all(BCRYPT_BAD_CODE)
        assert len(violations) >= 1
        domains = {v["domain"] for v in violations}
        assert "password_storage" in domains

    def test_check_all_multiple_domains(self):
        lib = SecurityTemplateLib()
        code = BCRYPT_BAD_CODE + "\n" + SQL_CONCAT_CODE + "\n" + HTTPS_VERIFY_FALSE_CODE
        violations = lib.check_all(code)
        domains = {v["domain"] for v in violations}
        assert "password_storage" in domains
        assert "sql_query" in domains
        assert "https_request" in domains


class TestSecurityTemplateLibTemplateAccess:
    """Template retrieval and builtins."""

    def test_get_template_known_domain(self):
        lib = SecurityTemplateLib()
        tmpl = lib.get_template("password_storage")
        assert tmpl is not None
        assert "bcrypt" in tmpl

    def test_get_template_sql(self):
        lib = SecurityTemplateLib()
        tmpl = lib.get_template("sql_query")
        assert tmpl is not None
        assert "execute" in tmpl

    def test_get_template_https(self):
        lib = SecurityTemplateLib()
        tmpl = lib.get_template("https_request")
        assert tmpl is not None
        assert "verify=True" in tmpl

    def test_get_template_unknown_domain(self):
        lib = SecurityTemplateLib()
        assert lib.get_template("nonexistent") is None

    def test_unknown_domain_check_returns_error(self):
        lib = SecurityTemplateLib()
        violations = lib.check_code("any code", "unknown_domain")
        assert len(violations) >= 1
        assert "Unknown domain" in violations[0]["message"]


class TestSecurityTemplateLibSecurityCritical:
    """@security_critical decorator on register_template."""

    def test_register_template_has_security_critical_marker(self):
        lib = SecurityTemplateLib()
        assert hasattr(lib.register_template, "_maref_security_critical")


class TestAIStenchDetectorSecurityIntegration:
    """M3.2 integration: AIStenchDetector._detect_missing_security with template_lib."""

    def test_detector_auto_creates_template_lib(self):
        from maref.immunity.ai_stench_detector import AIStenchDetector
        detector = AIStenchDetector()
        warnings = detector.scan(BCRYPT_BAD_CODE)
        security_warnings = [w for w in warnings if w.type.startswith("security_")]
        assert len(security_warnings) >= 1

    def test_detector_with_template_lib_detects_violations(self):
        from maref.immunity.ai_stench_detector import AIStenchDetector
        lib = SecurityTemplateLib()
        detector = AIStenchDetector(template_lib=lib)
        warnings = detector.scan(BCRYPT_BAD_CODE)
        security_warnings = [w for w in warnings if w.type.startswith("security_")]
        assert len(security_warnings) >= 1

    def test_detector_security_warnings_are_hard_block(self):
        from maref.immunity.ai_stench_detector import AIStenchDetector
        lib = SecurityTemplateLib()
        detector = AIStenchDetector(template_lib=lib)
        warnings = detector.scan(BCRYPT_BAD_CODE)
        security_warnings = [w for w in warnings if w.type.startswith("security_")]
        assert all(w.severity == "HARD_BLOCK" for w in security_warnings)

    def test_detector_good_code_no_security_warnings(self):
        from maref.immunity.ai_stench_detector import AIStenchDetector
        lib = SecurityTemplateLib()
        detector = AIStenchDetector(template_lib=lib)
        warnings = detector.scan(BCRYPT_GOOD_CODE)
        security_warnings = [w for w in warnings if w.type.startswith("security_")]
        assert len(security_warnings) == 0

    def test_detector_syntax_error_returns_empty(self):
        from maref.immunity.ai_stench_detector import AIStenchDetector
        lib = SecurityTemplateLib()
        detector = AIStenchDetector(template_lib=lib)
        warnings = detector.scan("def broken(")
        security_warnings = [w for w in warnings if w.type.startswith("security_")]
        assert len(security_warnings) == 0

    def test_existing_stench_detectors_still_work(self):
        from maref.immunity.ai_stench_detector import AIStenchDetector
        lib = SecurityTemplateLib()
        detector = AIStenchDetector(template_lib=lib)
        warnings = detector.scan("""
def get_user_by_id(user_id):
    \"\"\"Get user by id\"\"\"
    return query.filter(id=user_id).first()
""")
        cr = [w for w in warnings if w.type == "comment_repetition"]
        assert len(cr) >= 1

    def test_detector_with_good_all_domains_no_warnings(self):
        from maref.immunity.ai_stench_detector import AIStenchDetector
        lib = SecurityTemplateLib()
        detector = AIStenchDetector(template_lib=lib)
        code = BCRYPT_GOOD_CODE + "\n" + SQL_PARAMETERIZED_CODE + "\n" + HTTPS_VERIFY_TRUE_CODE
        warnings = detector.scan(code)
        security_warnings = [w for w in warnings if w.type.startswith("security_")]
        assert len(security_warnings) == 0

    def test_detector_with_bad_all_domains_detects_all(self):
        from maref.immunity.ai_stench_detector import AIStenchDetector
        lib = SecurityTemplateLib()
        detector = AIStenchDetector(template_lib=lib)
        code = BCRYPT_BAD_CODE + "\n" + SQL_CONCAT_CODE + "\n" + HTTPS_VERIFY_FALSE_CODE
        warnings = detector.scan(code)
        security_warnings = [w for w in warnings if w.type.startswith("security_")]
        assert len(security_warnings) >= 3

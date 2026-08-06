from __future__ import annotations

from maref.security.sanitizer import Sanitizer


class TestSanitizer:
    def test_sql_injection_detection(self) -> None:
        sani = Sanitizer()
        result = sani.sanitize_input("DROP TABLE users; SELECT * FROM passwords")
        assert result.sql_risk is True
        assert result.blocked is True
        assert "SQL injection" in result.reason

    def test_sql_injection_or_11(self) -> None:
        sani = Sanitizer()
        result = sani.sanitize_input("username' OR '1'='1")
        assert result.sql_risk is True
        assert result.blocked is True

    def test_pii_email_detection_and_tokenization(self) -> None:
        sani = Sanitizer()
        result = sani.sanitize_input("Contact me at user@example.com for details")
        assert result.pii_found == ["email"]
        assert "[PII_EMAIL_" in result.text
        assert "user@example.com" not in result.text

    def test_pii_phone_detection(self) -> None:
        sani = Sanitizer()
        result = sani.sanitize_input("Call 13800138000 for support")
        assert "phone_cn" in result.pii_found
        assert "[PII_PHONE_CN_" in result.text

    def test_restore_output_unauthorized(self) -> None:
        sani = Sanitizer()
        result = sani.sanitize_input("email: test@test.com")
        restored = sani.restore_output(result.text, result.tokens, authorized=False)
        assert restored == result.text
        assert "@" not in restored

    def test_restore_output_authorized(self) -> None:
        sani = Sanitizer()
        result = sani.sanitize_input("email: test@test.com")
        restored = sani.restore_output(
            result.text, result.tokens, authorized=True, authorized_by="test-agent"
        )
        assert "test@test.com" in restored

    def test_sanitize_output_replaces_raw_pii(self) -> None:
        sani = Sanitizer()
        result = sani.sanitize_output("My email is alice@example.com")
        assert "alice@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_sanitize_output_restores_tokens(self) -> None:
        sani = Sanitizer()
        raw = sani.sanitize_input("email: bob@test.com")
        output = sani.sanitize_output(raw.text, tokens=raw.tokens)
        assert "bob@test.com" not in output
        assert "[PII_EMAIL_" in output

    def test_long_input_blocked(self) -> None:
        sani = Sanitizer()
        result = sani.sanitize_input("x" * 100_001)
        assert result.blocked is True
        assert "exceeds 100K" in result.reason

    def test_clean_input_passes(self) -> None:
        sani = Sanitizer()
        result = sani.sanitize_input("Hello, this is a normal message.")
        assert result.blocked is False
        assert result.sql_risk is False
        assert result.pii_found == []

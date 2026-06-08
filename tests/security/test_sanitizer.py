"""Tests for Sanitizer — PII detection and data protection."""

import pytest

from maref.security.sanitizer import Sanitizer


class TestSanitizer:
    def test_sanitize_phone_cn(self):
        sani = Sanitizer()
        result = sani.sanitize_input("my phone is 13800138000")
        assert "13800138000" not in result.text
        assert "[PII_" in result.text
        assert "phone_cn" in result.pii_found

    def test_sanitize_email(self):
        sani = Sanitizer()
        result = sani.sanitize_input("email me at test@example.com")
        assert "test@example.com" not in result.text
        assert "[PII_" in result.text

    def test_sanitize_id_card(self):
        sani = Sanitizer()
        result = sani.sanitize_input("id: 110101199001011234")
        assert "110101199001011234" not in result.text
        assert "id_card_cn" in result.pii_found

    def test_block_sql_injection(self):
        sani = Sanitizer()
        result = sani.sanitize_input("'; DROP TABLE users; --")
        assert result.blocked is True
        assert result.sql_risk is True

    def test_block_second_sql_pattern(self):
        sani = Sanitizer()
        result = sani.sanitize_input("1=1; DELETE FROM orders")
        assert result.blocked is True

    def test_clean_input_passes(self):
        sani = Sanitizer()
        result = sani.sanitize_input("what is the weather today?")
        assert result.blocked is False
        assert result.text == "what is the weather today?"
        assert len(result.pii_found) == 0

    def test_restore_output_authorized(self):
        sani = Sanitizer()
        result = sani.sanitize_input("call 13800138000 for help")
        restored = sani.restore_output(result.text, result.tokens, authorized=True)
        assert "13800138000" in restored

    def test_restore_output_unauthorized(self):
        sani = Sanitizer()
        result = sani.sanitize_input("call 13800138000 for help")
        restored = sani.restore_output(result.text, result.tokens, authorized=False)
        assert "13800138000" not in restored
        assert "[PII_" in restored

    def test_sanitize_output_prevents_raw_leak(self):
        sani = Sanitizer()
        result = sani.sanitize_output("my email is user@test.com")
        assert "user@test.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_block_oversized_input(self):
        sani = Sanitizer()
        result = sani.sanitize_input("x" * 200_000)
        assert result.blocked is True

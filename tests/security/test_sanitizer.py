"""Tests for Sanitizer — PII detection and data protection."""


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

    def test_sanitize_phone_us(self):
        sani = Sanitizer()
        result = sani.sanitize_input("call 555-123-4567 for info")
        assert "555-123-4567" not in result.text
        assert "phone_us" in result.pii_found

    def test_sanitize_credit_card(self):
        sani = Sanitizer()
        result = sani.sanitize_input("card: 4111 1111 1111 1111")
        assert "4111 1111 1111 1111" not in result.text
        assert "credit_card" in result.pii_found

    def test_sanitize_ip_address(self):
        sani = Sanitizer()
        result = sani.sanitize_input("server is 192.168.1.1")
        assert "192.168.1.1" not in result.text
        assert "ip_address" in result.pii_found

    def test_multiple_pii_types(self):
        sani = Sanitizer()
        result = sani.sanitize_input("email a@b.com and phone 13800138000")
        assert "a@b.com" not in result.text
        assert "13800138000" not in result.text
        assert "email" in result.pii_found
        assert "phone_cn" in result.pii_found

    def test_clean_string_no_pii(self):
        sani = Sanitizer()
        result = sani.sanitize_input("")
        assert result.blocked is False
        assert result.text == ""

    def test_sanitize_output_with_tokens(self):
        sani = Sanitizer()
        result = sani.sanitize_input("email is test@example.com")
        output = sani.sanitize_output(
            result.text, tokens=result.tokens
        )
        assert "test@example.com" not in output
        assert "[PII_" in output

    def test_sanitize_output_empty_tokens(self):
        sani = Sanitizer()
        output = sani.sanitize_output("hello world", tokens={})
        assert output == "hello world"

    def test_restore_output_empty_tokens(self):
        sani = Sanitizer()
        restored = sani.restore_output("hello", {}, authorized=True)
        assert restored == "hello"

    def test_block_sql_drop_database(self):
        sani = Sanitizer()
        result = sani.sanitize_input("DROP DATABASE test")
        assert result.blocked is True
        assert result.sql_risk is True

    def test_block_sql_insert_into(self):
        sani = Sanitizer()
        result = sani.sanitize_input("INSERT INTO users VALUES (1)")
        assert result.blocked is True

    def test_block_sql_xp_cmdshell(self):
        sani = Sanitizer()
        result = sani.sanitize_input("xp_cmdshell 'dir'")
        assert result.blocked is True

    def test_block_sql_union_select(self):
        sani = Sanitizer()
        result = sani.sanitize_input("UNION SELECT * FROM dual")
        assert result.blocked is True

    def test_block_sql_or_true(self):
        sani = Sanitizer()
        result = sani.sanitize_input("OR 1=1 --")
        assert result.blocked is True

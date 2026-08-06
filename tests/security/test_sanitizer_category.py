"""Tests for C2: classification-aware sanitization (v0.51 W3-S2).

sanitize_by_category applies rule sets selected by DataCategory so that the
classification declared on a data field (C1) drives which PII is redacted.
"""

from __future__ import annotations

from maref.compliance.data_sovereignty import DataCategory
from maref.security.sanitizer import Sanitizer


def test_health_category_redacts_id_and_phone() -> None:
    sani = Sanitizer()
    text = "患者身份证 110101199003071234，电话 13800138000，诊断：高血压"
    result = sani.sanitize_by_category(text, DataCategory.HEALTH)
    # id_card 与 phone 都被 token 化
    assert "110101199003071234" not in result.text
    assert "13800138000" not in result.text
    assert "[PII_" in result.text


def test_financial_category_redacts_credit_card() -> None:
    sani = Sanitizer()
    text = "卡号 4111111111111111 消费 800 元"
    result = sani.sanitize_by_category(text, DataCategory.FINANCIAL)
    assert "4111111111111111" not in result.text
    assert "[PII_" in result.text


def test_public_category_passes_through() -> None:
    sani = Sanitizer()
    text = "公开的统计数字 42 与 3.14"
    result = sani.sanitize_by_category(text, DataCategory.PUBLIC)
    assert result.text == text


def test_personal_category_redacts_phone_and_email() -> None:
    sani = Sanitizer()
    text = "联系 13800138000 或 a@b.com"
    result = sani.sanitize_by_category(text, DataCategory.PERSONAL)
    assert "13800138000" not in result.text
    assert "a@b.com" not in result.text


def test_sanitize_by_category_returns_restorable_tokens() -> None:
    sani = Sanitizer()
    text = "电话 13800138000"
    result = sani.sanitize_by_category(text, DataCategory.PERSONAL)
    restored = sani.restore_output(
        result.text, result.tokens, authorized=True, authorized_by="test-agent"
    )
    assert restored == text


def test_unknown_category_falls_back_to_full_pii() -> None:
    sani = Sanitizer()
    text = "电话 13800138000"
    result = sani.sanitize_by_category(text, DataCategory.CRITICAL_INFRASTRUCTURE)
    # 未显式映射的分类回退到全量 PII 规则
    assert "13800138000" not in result.text


def test_legacy_sanitize_input_still_works() -> None:
    """既有 sanitize_input API 不被破坏."""
    sani = Sanitizer()
    result = sani.sanitize_input("电话 13800138000")
    assert "13800138000" not in result.text
    assert "[PII_PHONE_CN" in result.text

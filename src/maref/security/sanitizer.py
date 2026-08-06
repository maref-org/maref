"""Data sanitization gateway — input/output PII protection.

Provides:
- Input sanitization: PII detection + token replacement
- Output sanitization: reverse token restoration for authorized callers
- SQL injection keyword detection
- Input length and encoding validation
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from typing import Any

from maref.security.decorators import security_critical

# PII patterns (conservative — flag and replace, never silently pass)
PII_PATTERNS: dict[str, re.Pattern] = {
    "phone_cn": re.compile(r"1[3-9]\d{9}"),
    "phone_us": re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),
    "id_card_cn": re.compile(
        r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"
    ),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "ip_address": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
}

# Classification-aware rule selection (C1 → C2 linkage).
# Keys are DataCategory.value strings to avoid an import-time cycle with
# maref.compliance.data_sovereignty (which transitively pulls the audit bus).
CATEGORY_RULE_SETS: dict[str, set[str]] = {
    "health": {"id_card_cn", "phone_cn", "phone_us"},
    "financial": {"credit_card"},
    "personal": {"phone_cn", "phone_us", "email"},
    "sensitive_personal": {"id_card_cn", "phone_cn", "phone_us", "email"},
}
_FULL_PII_RULE_SET: set[str] = set(PII_PATTERNS)

SQL_INJECTION_KEYWORDS: list[str] = [
    "'--",
    "';",
    "1=1",
    "1=2",
    "DROP TABLE",
    "DROP DATABASE",
    "DELETE FROM",
    "INSERT INTO",
    "xp_cmdshell",
    "UNION SELECT",
    "OR '1'='1",
    "OR 1=1",
]


@dataclass
class SanitizeResult:
    text: str
    tokens: dict[str, str] = field(default_factory=dict)
    pii_found: list[str] = field(default_factory=list)
    sql_risk: bool = False
    blocked: bool = False
    reason: str = ""


class Sanitizer:
    """Input/output sanitizer with PII detection and tokenization.

    Usage:
        sani = Sanitizer()
        result = sani.sanitize_input("my phone is 13800138000")
        # result.text == "my phone is [PII_PHONE_CN_abc123]"
        # result.tokens = {"[PII_PHONE_CN_abc123]": "13800138000"}
        #
        # Later, for authorized output:
        original = sani.restore_output(
            result.text, result.tokens, authorized_by="agent-01"
        )
    """

    TOKEN_PREFIX = "[PII_"

    def __init__(self, audit_logger: Any | None = None) -> None:
        """可选注入审计 logger，授权还原时记录 ``pii_restore`` 事件（v0.52 M2-H2）。"""
        self._audit_logger = audit_logger

    @security_critical
    def sanitize_by_category(self, text: str, category: object) -> SanitizeResult:
        """Classification-aware sanitization (v0.51 W3-S2 / C2).

        Applies the PII rule set mapped to ``category`` (see
        ``CATEGORY_RULE_SETS``).  ``category`` accepts a
        ``DataCategory`` enum or its ``value`` string.  Unmapped categories
        fall back to the full PII rule set.  Result tokens are restorable by
        authorized callers.
        """
        category_key = getattr(category, "value", str(category))
        rule_set = CATEGORY_RULE_SETS.get(category_key, _FULL_PII_RULE_SET)
        result = SanitizeResult(text=text)

        lowered = text.lower()
        for kw in SQL_INJECTION_KEYWORDS:
            if kw.lower() in lowered:
                result.sql_risk = True
                result.blocked = True
                result.reason = f"SQL injection keyword detected: {kw!r}"
                return result

        for name, pattern in PII_PATTERNS.items():
            if name not in rule_set:
                continue
            matches = pattern.findall(text)
            for match in matches:
                token = f"{self.TOKEN_PREFIX}{name.upper()}_{secrets.token_hex(4)}"
                result.text = result.text.replace(match, token, 1)
                result.tokens[token] = match
                if name not in result.pii_found:
                    result.pii_found.append(name)

        if len(result.text) > 100_000:
            result.blocked = True
            result.reason = "input exceeds 100K character limit"
        return result

    @security_critical
    def sanitize_input(self, text: str) -> SanitizeResult:
        """Sanitize input text: detect PII, SQL injection, validate length."""
        result = SanitizeResult(text=text)

        # Check SQL injection
        lowered = text.lower()
        for kw in SQL_INJECTION_KEYWORDS:
            if kw.lower() in lowered:
                result.sql_risk = True
                result.blocked = True
                result.reason = f"SQL injection keyword detected: {kw!r}"
                return result

        # PII detection and token replacement
        for name, pattern in PII_PATTERNS.items():
            matches = pattern.findall(text)
            for match in matches:
                token = f"{self.TOKEN_PREFIX}{name.upper()}_{secrets.token_hex(4)}"
                result.text = result.text.replace(match, token, 1)
                result.tokens[token] = match
                if name not in result.pii_found:
                    result.pii_found.append(name)

        # Length validation
        if len(result.text) > 100_000:
            result.blocked = True
            result.reason = "input exceeds 100K character limit"
            return result

        return result

    def restore_output(
        self,
        text: str,
        tokens: dict[str, str],
        authorized: bool = False,
        authorized_by: str | None = None,
    ) -> str:
        """Restore original values from tokens.

        Only authorized callers should call this with authorized=True.

        v0.52 M2-H2: 授权还原必须提供执行主体 ``authorized_by``
        （fail-closed），还原动作经注入的 ``audit_logger`` 记录
        ``pii_restore`` 事件。未授权调用返回仍含 token 的文本。
        """
        if not authorized:
            return text
        if not authorized_by:
            raise ValueError(
                "authorized=True 必须提供 authorized_by 执行主体（fail-closed）"
            )
        if self._audit_logger is not None:
            try:
                self._audit_logger.log(
                    event_type="pii_restore",
                    actor=authorized_by,
                    action="restore_output",
                    details=f"restored {len(tokens)} PII tokens",
                )
            except Exception:
                # 审计失败不阻断还原；由审计完整性检查兜底。
                pass
        for token, original in tokens.items():
            text = text.replace(token, original)
        return text

    def sanitize_output(
        self,
        text: str,
        tokens: dict[str, str] | None = None,
    ) -> str:
        """Sanitize output: ensure no raw PII leaks.

        Uses the known tokens from a previous input sanitization.
        As a safety net, also scans for raw PII patterns.
        """
        result = text
        # Replace known tokens
        if tokens:
            for token, original in tokens.items():
                result = result.replace(original, token)

        # Safety net: detect any remaining raw PII
        for name, pattern in PII_PATTERNS.items():
            result = pattern.sub(f"[REDACTED_{name.upper()}]", result)

        return result

"""Tests for Unicode steganography sanitizer (M-001 threat defense).

Covers:
- Known stego codepoint detection (U+02B9, zero-width, BOM)
- Homoglyph detection (Cyrillic/Greek vs Latin)
- Sanitization (stego char removal)
- AuditLogger integration (HIGH threshold)
- ThreatGovernanceBridge integration (CRITICAL threshold)
- VerifierEntry metadata registration
"""

from __future__ import annotations

from unittest.mock import MagicMock

from maref.security.steg_sanitizer import (
    ALLOWED_CATEGORIES,
    HOMOGLYPH_MAP,
    KNOWN_STEGO_CODEPOINTS,
    STEG_ALERT_TYPE,
    SanitizedOutput,
    StegSanitizer,
    UnicodeAnomaly,
    UnicodeAnomalyDetector,
    register_steg_verifier,
)


class TestUnicodeAnomalyDetector:
    def test_detects_claude_stego_marker(self) -> None:
        """U+02B9 (MODIFIER LETTER PRIME) — Claude 隐写标记."""
        detector = UnicodeAnomalyDetector()
        anomalies = detector.detect("hello\u02b9world")
        assert len(anomalies) == 1
        assert anomalies[0].codepoint == 0x02B9
        assert anomalies[0].is_known_stego is True
        assert anomalies[0].position == 5

    def test_detects_zero_width_space(self) -> None:
        """U+200B (ZERO WIDTH SPACE)."""
        detector = UnicodeAnomalyDetector()
        anomalies = detector.detect("a\u200bb")
        assert len(anomalies) == 1
        assert anomalies[0].codepoint == 0x200B
        assert anomalies[0].is_known_stego is True

    def test_detects_zero_width_joiner_and_non_joiner(self) -> None:
        """U+200D (ZWJ) and U+200C (ZWNJ)."""
        detector = UnicodeAnomalyDetector()
        anomalies = detector.detect("x\u200dy\u200cz")
        assert len(anomalies) == 2
        codepoints = {a.codepoint for a in anomalies}
        assert 0x200D in codepoints
        assert 0x200C in codepoints

    def test_detects_bom(self) -> None:
        """U+FEFF (BOM / ZERO WIDTH NO-BREAK SPACE)."""
        detector = UnicodeAnomalyDetector()
        anomalies = detector.detect("\ufeffhello")
        assert len(anomalies) == 1
        assert anomalies[0].codepoint == 0xFEFF

    def test_detects_directional_marks(self) -> None:
        """U+202A-202E directional formatting characters."""
        detector = UnicodeAnomalyDetector()
        anomalies = detector.detect("a\u202eb")
        assert len(anomalies) == 1
        assert anomalies[0].codepoint == 0x202E

    def test_detects_cyrillic_homoglyph(self) -> None:
        """Cyrillic small a (U+0430) visually resembles Latin a."""
        detector = UnicodeAnomalyDetector()
        anomalies = detector.detect("cyrillic \u0430 here")
        # Cyrillic а + possibly other non-allowed chars
        cyrillic_anomalies = [a for a in anomalies if a.codepoint == 0x0430]
        assert len(cyrillic_anomalies) == 1
        assert cyrillic_anomalies[0].homoglyph_of == "a"

    def test_detects_greek_homoglyph(self) -> None:
        """Greek small omicron (U+03BF) visually resembles Latin o."""
        detector = UnicodeAnomalyDetector()
        anomalies = detector.detect("greek \u03bf here")
        greek_anomalies = [a for a in anomalies if a.codepoint == 0x03BF]
        assert len(greek_anomalies) == 1
        assert greek_anomalies[0].homoglyph_of == "o"

    def test_clean_text_has_no_anomalies(self) -> None:
        """Normal ASCII text passes without anomalies."""
        detector = UnicodeAnomalyDetector()
        anomalies = detector.detect("Hello, this is a normal message. 12345.")
        # All chars should be in allowed categories
        assert all(a.codepoint not in KNOWN_STEGO_CODEPOINTS for a in anomalies)
        assert all(a.codepoint not in HOMOGLYPH_MAP for a in anomalies)

    def test_empty_text_returns_empty_list(self) -> None:
        detector = UnicodeAnomalyDetector()
        assert detector.detect("") == []

    def test_anomaly_to_dict(self) -> None:
        anomaly = UnicodeAnomaly(
            codepoint=0x02B9,
            name="MODIFIER LETTER PRIME",
            category="Lm",
            position=3,
            is_known_stego=True,
        )
        d = anomaly.to_dict()
        assert d["codepoint"] == "U+02B9"
        assert d["name"] == "MODIFIER LETTER PRIME"
        assert d["is_known_stego"] is True


class TestStegSanitizer:
    def test_sanitize_removes_claude_marker(self) -> None:
        sani = StegSanitizer()
        result = sani.sanitize("hello\u02b9world")
        assert "\u02b9" not in result.text
        assert result.text == "helloworld"
        assert result.removed_count == 1
        assert result.blocked is False

    def test_sanitize_removes_zero_width_chars(self) -> None:
        sani = StegSanitizer()
        result = sani.sanitize("a\u200b\u200cc\u200dd")
        assert "\u200b" not in result.text
        assert "\u200c" not in result.text
        assert "\u200d" not in result.text
        assert result.removed_count == 3

    def test_sanitize_removes_bom(self) -> None:
        sani = StegSanitizer()
        result = sani.sanitize("\ufeffhello")
        assert "\ufeff" not in result.text
        assert result.removed_count == 1

    def test_sanitize_preserves_homoglyphs(self) -> None:
        """Homoglyphs are detected but not stripped (would break readability)."""
        sani = StegSanitizer()
        result = sani.sanitize("text \u0430 end")
        # Cyrillic а detected as anomaly but not removed
        assert any(a.codepoint == 0x0430 for a in result.anomalies)
        assert "\u0430" in result.text

    def test_clean_text_passes_through(self) -> None:
        sani = StegSanitizer()
        result = sani.sanitize("Hello, normal message.")
        assert result.removed_count == 0
        assert len(result.anomalies) == 0
        assert result.blocked is False
        assert result.text == "Hello, normal message."

    def test_high_threshold_triggers_audit_log(self) -> None:
        """When anomaly count >= threshold (5), AuditLogger.log_anomaly is called."""
        mock_logger = MagicMock()
        sani = StegSanitizer(audit_logger=mock_logger, threshold=5)
        # 6 zero-width chars → exceeds threshold of 5
        text = "a\u200bb\u200cc\u200dd\u200be\u200cf"
        result = sani.sanitize(text)
        mock_logger.log_anomaly.assert_called_once()
        call_kwargs = mock_logger.log_anomaly.call_args
        assert call_kwargs.kwargs["actor"] == "StegSanitizer"
        assert call_kwargs.kwargs["anomaly_type"] == "unicode_steganography"
        assert call_kwargs.kwargs["severity"] == "HIGH"

    def test_below_threshold_does_not_log(self) -> None:
        """When anomaly count < threshold, no audit log."""
        mock_logger = MagicMock()
        sani = StegSanitizer(audit_logger=mock_logger, threshold=5)
        # Only 2 anomalies → below threshold
        sani.sanitize("a\u02b9b\u200cc")
        mock_logger.log_anomaly.assert_not_called()

    def test_critical_threshold_triggers_threat_bridge(self) -> None:
        """When anomaly count >= critical_threshold (15), ThreatGovernanceBridge is called."""
        mock_bridge = MagicMock()
        # threshold=5, critical_multiplier=3 → critical_threshold=15
        sani = StegSanitizer(threat_bridge=mock_bridge, threshold=5, critical_multiplier=3)
        # 16 zero-width chars → exceeds critical threshold
        text = "a" + "\u200b" * 16
        result = sani.sanitize(text)
        mock_bridge.on_threat_alert.assert_called_once()
        alert = mock_bridge.on_threat_alert.call_args.args[0]
        assert alert.alert_type == STEG_ALERT_TYPE
        assert alert.severity.value == "critical"
        assert result.blocked is True
        assert "CRITICAL" in result.reason

    def test_below_critical_does_not_trigger_bridge(self) -> None:
        mock_bridge = MagicMock()
        sani = StegSanitizer(threat_bridge=mock_bridge, threshold=5, critical_multiplier=3)
        # 10 anomalies → above HIGH threshold but below CRITICAL (15)
        text = "a" + "\u200b" * 10
        result = sani.sanitize(text)
        mock_bridge.on_threat_alert.assert_not_called()
        assert result.blocked is False

    def test_no_logger_no_error(self) -> None:
        """Sanitizer without logger/bridge doesn't crash on high anomaly count."""
        sani = StegSanitizer()  # no logger, no bridge
        text = "a" + "\u200b" * 20
        result = sani.sanitize(text)
        assert result.removed_count == 20
        # No crash, just no logging/alerting

    def test_sanitized_output_to_dict(self) -> None:
        output = SanitizedOutput(text="clean", removed_count=1, blocked=False)
        d = output.to_dict()
        assert d["text"] == "clean"
        assert d["removed_count"] == 1
        assert d["blocked"] is False
        assert d["anomalies"] == []


class TestRegisterStegVerifier:
    def test_registers_verifier_entry(self) -> None:
        from maref.governance.verifier_registry import VerifierRegistry, VerifierStatus

        registry = VerifierRegistry()
        register_steg_verifier(registry)

        entry = registry.get("unicode_steg_detector")
        assert entry is not None
        assert entry.model == "StegSanitizer v1"
        assert entry.methodology == "character_codepoint_analysis"
        assert entry.status == VerifierStatus.ACTIVE
        assert entry.accuracy == 0.95
        assert entry.recall == 0.92

    def test_registered_verifier_listed_active(self) -> None:
        from maref.governance.verifier_registry import VerifierRegistry

        registry = VerifierRegistry()
        register_steg_verifier(registry)

        active = registry.list_active()
        names = [v.name for v in active]
        assert "unicode_steg_detector" in names


class TestConstants:
    def test_steg_alert_type_value(self) -> None:
        assert STEG_ALERT_TYPE == "steganography_injection"

    def test_known_stego_includes_claude_marker(self) -> None:
        assert 0x02B9 in KNOWN_STEGO_CODEPOINTS

    def test_known_stego_includes_zero_width_range(self) -> None:
        for cp in range(0x200B, 0x2010):
            assert cp in KNOWN_STEGO_CODEPOINTS

    def test_known_stego_includes_bom(self) -> None:
        assert 0xFEFF in KNOWN_STEGO_CODEPOINTS

    def test_allowed_categories_excludes_modifier_letters(self) -> None:
        """Lm (Modifier Letter) category is NOT in allowed set."""
        assert "Lm" not in ALLOWED_CATEGORIES

    def test_homoglyph_map_has_entries(self) -> None:
        assert len(HOMOGLYPH_MAP) >= 10
        assert HOMOGLYPH_MAP[0x0430] == "a"

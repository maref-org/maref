"""交易授权分级（GB/Z 185.9 7.2.1 / 表4 对齐）。"""

from __future__ import annotations

import pytest

from maref.governance.authorization_level import (
    AuthorizationLevel,
    audit_fields,
    check,
    coerce_level,
    coerce_risk,
    describe,
    required_level,
)


class TestMapping:
    def test_required_level(self):
        assert required_level("high") is AuthorizationLevel.L1
        assert required_level("medium") is AuthorizationLevel.L2
        assert required_level("low") is AuthorizationLevel.L3

    def test_coerce_level_accepts_common_forms(self):
        for raw in ("L1", "l1", "1", " L1 "):
            assert coerce_level(raw) is AuthorizationLevel.L1

    def test_coerce_unknown_fails_closed(self):
        with pytest.raises(ValueError):
            coerce_level("L9")
        with pytest.raises(ValueError):
            coerce_risk("critical")


class TestCheck:
    def test_high_risk_requires_l1(self):
        assert check("L1", "high").satisfied is True
        assert check("L2", "high").satisfied is False
        assert check("L3", "high").satisfied is False

    def test_lower_risk_accepts_stricter(self):
        assert check("L1", "low").satisfied is True
        assert check("L2", "low").satisfied is True
        assert check("L3", "low").satisfied is True

    def test_medium_risk_boundary(self):
        assert check("L2", "medium").satisfied is True
        assert check("L3", "medium").satisfied is False

    def test_reason_mentions_levels(self):
        result = check("L3", "high")
        assert "L1" in result.reason and "L3" in result.reason


class TestDescribe:
    def test_descriptions_match_standard(self):
        assert "每次交易需智能体委托方确认" in describe("L1")
        assert "有效期" in describe("L2")
        assert "自动执行" in describe("L3")


class TestAuditFields:
    def test_fields_roundtrip(self):
        fields = audit_fields("L1", "high", credential_id="cred-1", subject="human:alice")
        assert fields["authorization_level"] == "L1"
        assert fields["risk_level"] == "high"
        assert fields["authorization_satisfied"] == "true"
        assert fields["authorization_credential_id"] == "cred-1"
        assert fields["primary_subject"] == "human:alice"

    def test_unsatisfied_marked_false(self):
        assert audit_fields("L3", "high")["authorization_satisfied"] == "false"

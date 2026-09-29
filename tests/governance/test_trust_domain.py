"""TrustDomain 单元测试 — 信任域强制默认化."""

from __future__ import annotations

import pytest

from maref.governance.trust_domain import (
    TrustDomainError,
    TrustDomainMode,
    assess,
    enforce,
    resolve_mode,
)


class TestResolveMode:
    def test_default_local(self) -> None:
        assert resolve_mode({}) == TrustDomainMode.LOCAL

    def test_explicit_enforce(self) -> None:
        assert resolve_mode({"MAREF_TRUST_DOMAIN": "enforce"}) == TrustDomainMode.ENFORCE

    def test_explicit_local(self) -> None:
        assert resolve_mode({"MAREF_TRUST_DOMAIN": "local"}) == TrustDomainMode.LOCAL

    def test_production_defaults_to_enforce(self) -> None:
        assert resolve_mode({"MAREF_PRODUCTION": "1"}) == TrustDomainMode.ENFORCE

    def test_explicit_local_overrides_production(self) -> None:
        mode = resolve_mode({"MAREF_PRODUCTION": "1", "MAREF_TRUST_DOMAIN": "off"})
        assert mode == TrustDomainMode.LOCAL


class TestAssess:
    def test_local_mode_is_compliant(self) -> None:
        report = assess({})
        assert report.mode == TrustDomainMode.LOCAL
        assert report.compliant is True
        assert report.issues == []

    def test_enforce_without_separation_has_issues(self) -> None:
        report = assess({"MAREF_TRUST_DOMAIN": "enforce"})
        assert report.mode == TrustDomainMode.ENFORCE
        assert report.compliant is False
        joined = "; ".join(report.issues)
        assert "MAREF_AUDIT_SIGNER_URL" in joined
        assert "MAREF_SIDECAR_URL" in joined

    def test_enforce_with_separation_is_compliant(self) -> None:
        report = assess(
            {
                "MAREF_TRUST_DOMAIN": "enforce",
                "MAREF_AUDIT_SIGNER_URL": "http://sidecar/sign",
                "MAREF_SIDECAR_URL": "http://sidecar",
            }
        )
        assert report.compliant is True
        assert report.remote_signer_configured is True
        assert report.out_of_process is True

    def test_enforce_detects_local_key(self) -> None:
        report = assess(
            {
                "MAREF_TRUST_DOMAIN": "enforce",
                "MAREF_AUDIT_SIGNER_URL": "http://sidecar/sign",
                "MAREF_SIDECAR_URL": "http://sidecar",
                "MAREF_HMAC_SECRET_KEY": "leaked-key",
            }
        )
        assert report.compliant is False
        assert any("HMAC key" in issue for issue in report.issues)

    def test_report_serializable(self) -> None:
        payload = assess({}).to_dict()
        assert payload["mode"] == "local"
        assert payload["compliant"] is True


class TestEnforce:
    def test_enforce_raises_when_violated(self) -> None:
        with pytest.raises(TrustDomainError):
            enforce({"MAREF_TRUST_DOMAIN": "enforce"})

    def test_enforce_passes_when_compliant(self) -> None:
        report = enforce(
            {
                "MAREF_TRUST_DOMAIN": "enforce",
                "MAREF_AUDIT_SIGNER_URL": "http://sidecar/sign",
                "MAREF_SIDECAR_URL": "http://sidecar",
            }
        )
        assert report.compliant is True

    def test_enforce_noop_in_local_mode(self) -> None:
        report = enforce({})
        assert report.mode == TrustDomainMode.LOCAL

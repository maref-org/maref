"""框架 3.0 SM2 Agent 身份证书（P4）测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from maref.crypto.sm2 import SM2KeyPair
from maref.identity.did_registry import AgentDID
from maref.identity.sm2_certificate import (
    CERT_FORMAT,
    NATIONAL_CA_UNAVAILABLE,
    UnavailableNationalCAAdapter,
    VerifyResult,
    export_certificate,
    import_certificate,
    issue_certificate,
    issue_certificate_for_did,
    sm3_fingerprint,
    verify_certificate,
    verify_did_binding,
)


@pytest.fixture(scope="module")
def casp() -> SM2KeyPair:
    return SM2KeyPair.generate()


@pytest.fixture(scope="module")
def agent() -> SM2KeyPair:
    return SM2KeyPair.generate()


def _issue(casp: SM2KeyPair, agent: SM2KeyPair, **kwargs):
    return issue_certificate(
        agent_id="agent-1",
        subject_public_key=agent.public_key,
        casp_private_key=casp.private_key,
        casp_public_key=casp.public_key,
        casp_id="casp-1",
        **kwargs,
    )


class TestIssueVerify:
    def test_roundtrip_valid(self, casp, agent):
        cert = _issue(casp, agent)
        result = verify_certificate(cert, casp.public_key)
        assert result.valid
        assert result.reasons == ()

    def test_wrong_casp_key_invalid(self, casp, agent):
        cert = _issue(casp, agent)
        other = SM2KeyPair.generate()
        result = verify_certificate(cert, other.public_key)
        assert not result.valid
        assert "signature-invalid" in result.reasons

    def test_result_is_truthy(self, casp, agent):
        cert = _issue(casp, agent)
        assert bool(verify_certificate(cert, casp.public_key)) is True


class TestTampering:
    def test_tamper_agent_id(self, casp, agent):
        cert = _issue(casp, agent)
        assert not verify_certificate(replace(cert, agent_id="evil"), casp.public_key).valid

    def test_tamper_public_key(self, casp, agent):
        cert = _issue(casp, agent)
        other = SM2KeyPair.generate()
        assert not verify_certificate(replace(cert, public_key=other.public_key), casp.public_key).valid

    def test_tamper_validity(self, casp, agent):
        cert = _issue(casp, agent)
        start, end = cert.validity_period
        tampered = replace(cert, validity_period=(start + 1, end))
        assert not verify_certificate(tampered, casp.public_key).valid


class TestValidity:
    def test_expired(self, casp, agent):
        cert = _issue(casp, agent, validity_days=1, now=1000)
        result = verify_certificate(cert, casp.public_key, now=1000 + 86400 + 10)
        assert "expired" in result.reasons

    def test_not_yet_valid(self, casp, agent):
        cert = _issue(casp, agent, validity_days=1, now=10_000)
        result = verify_certificate(cert, casp.public_key, now=9999)
        assert "not-yet-valid" in result.reasons

    def test_validity_check_disabled(self, casp, agent):
        cert = _issue(casp, agent, validity_days=1, now=1000)
        result = verify_certificate(
            cert, casp.public_key, now=1000 + 86400 + 10, check_validity=False
        )
        assert result.valid


class TestDidBinding:
    def test_issue_for_did_uses_short_id(self, casp, agent):
        did = AgentDID(namespace="ns", agent_short_id="abc123").did_string
        cert = issue_certificate_for_did(
            did,
            subject_public_key=agent.public_key,
            casp_private_key=casp.private_key,
            casp_public_key=casp.public_key,
            casp_id="casp-1",
        )
        assert cert.agent_id == "abc123"
        assert verify_did_binding(cert, did)

    def test_binding_mismatch(self, casp, agent):
        cert = _issue(casp, agent)
        other_did = AgentDID(namespace="ns", agent_short_id="other").did_string
        assert not verify_did_binding(cert, other_did)

    def test_invalid_did_returns_false(self, casp, agent):
        cert = _issue(casp, agent)
        assert not verify_did_binding(cert, "not-a-did")


class TestFingerprintAndExport:
    def test_fingerprint_stable_and_hex(self, agent):
        fp1 = sm3_fingerprint(agent.public_key)
        fp2 = sm3_fingerprint(agent.public_key)
        assert fp1 == fp2
        assert len(fp1) == 64
        int(fp1, 16)

    def test_export_import_roundtrip(self, casp, agent):
        cert = _issue(casp, agent)
        restored = import_certificate(export_certificate(cert))
        assert restored == cert
        assert verify_certificate(restored, casp.public_key).valid

    def test_export_fields(self, casp, agent):
        data = export_certificate(_issue(casp, agent))
        assert data["format"] == CERT_FORMAT
        assert data["public_key_fingerprint"] == sm3_fingerprint(data["public_key"])
        assert len(data["validity_period"]) == 2


class TestNationalCAAdapter:
    def test_placeholder_raises(self):
        adapter = UnavailableNationalCAAdapter()
        with pytest.raises(NotImplementedError, match="预留接口"):
            adapter.issue(agent_id="x", subject_public_key="y")

    def test_unavailable_message(self):
        assert "未与任何外部 CA 联调" in NATIONAL_CA_UNAVAILABLE


class TestVerifyResult:
    def test_bool_and_dict(self):
        assert bool(VerifyResult(valid=True)) is True
        assert bool(VerifyResult(valid=False, reasons=("expired",))) is False
        assert VerifyResult(valid=False, reasons=("expired",)).to_dict() == {
            "valid": False,
            "reasons": ["expired"],
        }

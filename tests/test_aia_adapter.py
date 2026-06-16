"""AIA 国密适配层单元测试."""

from __future__ import annotations

from maref.crypto.aia_adapter import (
    AgentIdentityCertificate,
    check_agent_identity,
    generate_certificate_verify,
    verify_cai_certificate,
    verify_certificate_verify,
)
from maref.crypto.sm2 import sm2_sign

SM2_PRIVATE_KEY = "00B9AB0B828FF68872F21A837FC303668428DEA11DCD1B24429D0C99E24EED83D5"
SM2_PUBLIC_KEY = "B9C9A6E04E9C91F7BA880429273747D7EF5DDEB0BB2FF6317EB00BEF331A83081A6994B8993F3F5D6EADDDB81872266C87C018FB4162F5AF347B483E24620207"


class TestVerifyCAI:
    def test_verify_valid_cai(self) -> None:
        """测试合法 CAI 证书验证."""
        cai_plaintext = (f"AIC-12345:{SM2_PUBLIC_KEY}:CASP-001:1700000000:1800000000").encode()
        signature = sm2_sign(
            SM2_PRIVATE_KEY, cai_plaintext, public_key=SM2_PUBLIC_KEY, use_sm3=True
        )

        cai = AgentIdentityCertificate(
            agent_id="AIC-12345",
            public_key=SM2_PUBLIC_KEY,
            signature=signature,
            casp_id="CASP-001",
            validity_period=(1700000000, 1800000000),
        )

        assert verify_cai_certificate(cai, SM2_PUBLIC_KEY)

    def test_verify_invalid_cai(self) -> None:
        """测试篡改后的 CAI 证书验证失败."""
        cai = AgentIdentityCertificate(
            agent_id="AIC-12345",
            public_key=SM2_PUBLIC_KEY,
            signature="invalid_signature",
            casp_id="CASP-001",
            validity_period=(1700000000, 1800000000),
        )

        assert not verify_cai_certificate(cai, SM2_PUBLIC_KEY)


class TestCertificateVerify:
    def test_generate_and_verify(self) -> None:
        """测试 CertificateVerify 签名生成与验证."""
        handshake_messages = b"client_hello||server_hello||certificate"

        signature = generate_certificate_verify(SM2_PRIVATE_KEY, SM2_PUBLIC_KEY, handshake_messages)

        assert verify_certificate_verify(SM2_PUBLIC_KEY, handshake_messages, signature)

    def test_verify_tampered_messages(self) -> None:
        """测试篡改握手消息后验证失败."""
        handshake_messages = b"client_hello||server_hello||certificate"

        signature = generate_certificate_verify(SM2_PRIVATE_KEY, SM2_PUBLIC_KEY, handshake_messages)

        assert not verify_certificate_verify(SM2_PUBLIC_KEY, b"tampered", signature)


class TestCheckAgentIdentity:
    def test_matching_aic(self) -> None:
        cai = AgentIdentityCertificate(
            agent_id="AIC-12345",
            public_key=SM2_PUBLIC_KEY,
            signature="sig",
            casp_id="CASP-001",
            validity_period=(0, 0),
        )
        assert check_agent_identity("AIC-12345", cai)

    def test_mismatched_aic(self) -> None:
        cai = AgentIdentityCertificate(
            agent_id="AIC-12345",
            public_key=SM2_PUBLIC_KEY,
            signature="sig",
            casp_id="CASP-001",
            validity_period=(0, 0),
        )
        assert not check_agent_identity("AIC-99999", cai)

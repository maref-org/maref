"""
v0.50 W7 — 身份与凭证收敛（A7/A6/A5）

覆盖：
- A7: 未注册公钥的 DID 签发治理凭证抛 ValueError（fail-closed）
- A7: 注册公钥且匹配 → 签发成功
- A6: VerifiableCredential.issue issuer_secret=None → ValueError（不再隐式随机）
- A5: identity/__init__ 不再导出死代码 CredentialStore/VerifiableCredential
"""

from __future__ import annotations

import pytest

from maref.governance.state_machine import GovernanceStateMachine
from maref.identity.agent_identity_service import AgentIdentityService
from maref.identity.credential import VerifiableCredential
from maref.identity.did_registry import AgentDID
from maref.signing.signing_key import ReportSigningKey


class TestW7EmptyPublicKeyRejected:
    def test_issue_without_registered_key_rejected(self) -> None:
        service = AgentIdentityService(signing_key=ReportSigningKey.generate())
        did = AgentDID.generate()
        state_machine = GovernanceStateMachine()
        service._did_registry.register(did, state_machine)
        with pytest.raises(ValueError, match="公钥"):
            service.issue(
                subject_did=did.did_string,
                scope=["audit"],
                signing_key=ReportSigningKey.generate(),
            )

    def test_issue_with_matching_key_succeeds(self) -> None:
        key = ReportSigningKey.generate()
        service = AgentIdentityService(signing_key=key)
        did = AgentDID.generate()
        state_machine = GovernanceStateMachine()
        record = service._did_registry.register(did, state_machine)
        record.metadata["ed25519_public_key_pem"] = key.public_key_pem
        cred = service.issue(subject_did=did.did_string, scope=["audit"], signing_key=key)
        assert cred.subject_did == did.did_string

    def test_issue_with_mismatched_key_rejected(self) -> None:
        key = ReportSigningKey.generate()
        other = ReportSigningKey.generate()
        service = AgentIdentityService(signing_key=key)
        did = AgentDID.generate()
        state_machine = GovernanceStateMachine()
        record = service._did_registry.register(did, state_machine)
        record.metadata["ed25519_public_key_pem"] = key.public_key_pem
        with pytest.raises(ValueError):
            service.issue(
                subject_did=did.did_string,
                scope=["audit"],
                signing_key=other,
            )


class TestW6IssuerSecretRequired:
    def test_issue_without_secret_raises(self) -> None:
        issuer = AgentDID.generate()
        subject = AgentDID.generate()
        with pytest.raises(ValueError):
            VerifiableCredential.issue(
                issuer=issuer,
                subject=subject,
                credential_type="Test",
                claims={},
                issuer_secret=None,
            )

    def test_issue_with_secret_succeeds(self) -> None:
        issuer = AgentDID.generate()
        subject = AgentDID.generate()
        vc = VerifiableCredential.issue(
            issuer=issuer,
            subject=subject,
            credential_type="Test",
            claims={},
            issuer_secret=b"test-secret-32-bytes-000000000000",
        )
        assert vc.issuer == issuer
        assert vc.verify(issuer_secret=b"test-secret-32-bytes-000000000000") is True


class TestW5DeadCodeExportRemoved:
    def test_legacy_credential_not_exported_from_package(self) -> None:
        import maref.identity as identity_pkg

        assert not hasattr(identity_pkg, "VerifiableCredential")
        assert not hasattr(identity_pkg, "CredentialStore")

    def test_legacy_credential_still_importable_from_module(self) -> None:
        from maref.identity.credential import CredentialStore, VerifiableCredential

        assert CredentialStore is not None
        assert VerifiableCredential is not None

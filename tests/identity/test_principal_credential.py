"""PrincipalCredential / PrincipalRegistry 单元测试 — 身份锚定 (P1-6)."""

from __future__ import annotations

import time

import pytest

from maref.identity.principal_credential import (
    PrincipalCredential,
    PrincipalDecision,
    PrincipalRegistry,
)
from maref.signing.signing_key import ReportSigningKey

PRINCIPAL = "did:human:alice"
AGENT = "did:agent:worker-1"
ACTION = "file.read"


def _registry_with_principal() -> tuple[PrincipalRegistry, ReportSigningKey]:
    key = ReportSigningKey.generate()
    registry = PrincipalRegistry()
    registry.register(PRINCIPAL, key.public_key_pem)
    return registry, key


def _signed_credential(key: ReportSigningKey, **overrides: object) -> PrincipalCredential:
    credential = PrincipalCredential.issue(
        principal_did=str(overrides.get("principal_did", PRINCIPAL)),
        agent_did=str(overrides.get("agent_did", AGENT)),
        allowed_actions=overrides.get("allowed_actions", [ACTION]),  # type: ignore[arg-type]
        ttl_seconds=overrides.get("ttl_seconds", 3600),  # type: ignore[arg-type]
        issuer=str(overrides.get("issuer", "")),
    )
    credential.sign(key)
    return credential


class TestCredentialSigning:
    def test_sign_verify_roundtrip(self) -> None:
        key = ReportSigningKey.generate()
        credential = _signed_credential(key)
        assert credential.verify_signature(key.public_key_pem) is True

    def test_tampered_scope_fails_verification(self) -> None:
        key = ReportSigningKey.generate()
        credential = _signed_credential(key)
        credential.allowed_actions = [ACTION, "shell.exec"]
        assert credential.verify_signature(key.public_key_pem) is False

    def test_wrong_key_fails_verification(self) -> None:
        key = ReportSigningKey.generate()
        other = ReportSigningKey.generate()
        credential = _signed_credential(key)
        assert credential.verify_signature(other.public_key_pem) is False

    def test_empty_signature_fails(self) -> None:
        credential = PrincipalCredential.issue(PRINCIPAL, AGENT, [ACTION])
        key = ReportSigningKey.generate()
        assert credential.verify_signature(key.public_key_pem) is False


class TestScopeAndExpiry:
    def test_empty_scope_denies_all(self) -> None:
        credential = PrincipalCredential.issue(PRINCIPAL, AGENT, [])
        assert credential.allows_action(ACTION) is False

    def test_scope_allows_listed_action(self) -> None:
        credential = PrincipalCredential.issue(PRINCIPAL, AGENT, [ACTION])
        assert credential.allows_action(ACTION) is True
        assert credential.allows_action("shell.exec") is False

    def test_expired(self) -> None:
        credential = PrincipalCredential.issue(PRINCIPAL, AGENT, [ACTION], ttl_seconds=-1)
        assert credential.is_expired() is True

    def test_not_expired(self) -> None:
        credential = PrincipalCredential.issue(PRINCIPAL, AGENT, [ACTION], ttl_seconds=3600)
        assert credential.is_expired() is False

    def test_unparseable_valid_until_fails_closed(self) -> None:
        credential = PrincipalCredential.issue(PRINCIPAL, AGENT, [ACTION])
        credential.valid_until = "not-a-time"  # type: ignore[assignment]
        assert credential.is_expired() is True


class TestAuthorize:
    def test_happy_path(self) -> None:
        registry, key = _registry_with_principal()
        credential = _signed_credential(key)
        decision = registry.authorize(credential, AGENT, ACTION)
        assert decision.allowed is True

    def test_no_credential_denied(self) -> None:
        registry, _ = _registry_with_principal()
        decision = registry.authorize(None, AGENT, ACTION)
        assert decision.allowed is False
        assert "no principal credential" in decision.reason

    def test_unknown_principal_denied(self) -> None:
        registry, key = _registry_with_principal()
        credential = _signed_credential(key, principal_did="did:human:mallory")
        decision = registry.authorize(credential, AGENT, ACTION)
        assert decision.allowed is False
        assert "unknown principal" in decision.reason

    def test_forged_signature_denied(self) -> None:
        registry, _ = _registry_with_principal()
        attacker_key = ReportSigningKey.generate()
        # 攻击者用自己的私钥签名，冒充 PRINCIPAL
        credential = _signed_credential(attacker_key)
        decision = registry.authorize(credential, AGENT, ACTION)
        assert decision.allowed is False
        assert "invalid principal signature" in decision.reason

    def test_agent_binding_enforced(self) -> None:
        registry, key = _registry_with_principal()
        credential = _signed_credential(key, agent_did="did:agent:other")
        decision = registry.authorize(credential, AGENT, ACTION)
        assert decision.allowed is False
        assert "not bound" in decision.reason

    def test_issuer_mismatch_denied(self) -> None:
        registry, key = _registry_with_principal()
        credential = _signed_credential(key, issuer="did:human:other")
        decision = registry.authorize(credential, AGENT, ACTION)
        assert decision.allowed is False
        assert "issuer" in decision.reason

    def test_expired_denied(self) -> None:
        registry, key = _registry_with_principal()
        credential = _signed_credential(key, ttl_seconds=-1)
        decision = registry.authorize(credential, AGENT, ACTION)
        assert decision.allowed is False
        assert "expired" in decision.reason

    def test_action_out_of_scope_denied(self) -> None:
        registry, key = _registry_with_principal()
        credential = _signed_credential(key, allowed_actions=[ACTION])
        decision = registry.authorize(credential, AGENT, "shell.exec")
        assert decision.allowed is False
        assert "not in principal scope" in decision.reason

    def test_integrity_leak_scenario(self) -> None:
        # agent 幻觉出委托人身份但无凭据 -> 拒绝（不是自报字段放行）
        registry, _ = _registry_with_principal()
        decision = registry.authorize(None, AGENT, ACTION)
        assert decision.allowed is False


class TestRegistryBookkeeping:
    def test_register_requires_values(self) -> None:
        registry = PrincipalRegistry()
        with pytest.raises(ValueError):
            registry.register("", "pem")
        with pytest.raises(ValueError):
            registry.register("did:human:alice", "")

    def test_is_registered_and_count(self) -> None:
        registry, _ = _registry_with_principal()
        assert registry.is_registered(PRINCIPAL) is True
        assert registry.is_registered("did:human:bob") is False
        assert registry.principal_count == 1

    def test_decision_and_credential_serializable(self) -> None:
        registry, key = _registry_with_principal()
        credential = _signed_credential(key)
        assert PrincipalDecision(True, "ok").to_dict() == {"allowed": True, "reason": "ok"}
        payload = credential.to_dict()
        assert payload["principal_did"] == PRINCIPAL
        assert payload["agent_did"] == AGENT

    def test_expired_with_explicit_now(self) -> None:
        registry, key = _registry_with_principal()
        credential = _signed_credential(key)
        future = time.time() + 99999
        decision = registry.authorize(credential, AGENT, ACTION, now=future)
        assert decision.allowed is False
        assert "expired" in decision.reason

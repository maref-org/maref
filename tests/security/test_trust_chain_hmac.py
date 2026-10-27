"""委托链 HMAC 每跳签名与序列化测试。"""

from __future__ import annotations

from maref.security.trust_chain import (
    DelegationCapability,
    DelegationChain,
    ValidationStatus,
)

KEY = b"deployment-hmac-key"
KEY_ID = "k1"


def _signed_chain() -> DelegationChain:
    chain = DelegationChain.create_hmac(
        "agent-root",
        KEY,
        key_id=KEY_ID,
        root_principal="did:principal:alice",
    )
    assert chain.add_delegation_hmac(
        "agent-root", "agent-child", DelegationCapability.DELEGATE, KEY, key_id=KEY_ID
    )
    assert chain.add_delegation_hmac(
        "agent-child", "agent-leaf", DelegationCapability.READ, KEY, key_id=KEY_ID
    )
    return chain


def test_hmac_chain_validates():
    chain = _signed_chain()
    result = chain.validate_hmac([KEY])
    assert result.status == ValidationStatus.VALID
    assert result.is_valid is True


def test_hmac_chain_roundtrip_preserves_validity():
    restored = DelegationChain.from_dict(_signed_chain().to_dict())
    assert restored.root_principal == "did:principal:alice"
    assert restored.depth == 3
    assert restored.validate_hmac([KEY]).is_valid is True


def test_hmac_chain_detects_tampering():
    restored = DelegationChain.from_dict(_signed_chain().to_dict())
    restored.nodes[1].capability = DelegationCapability.ADMIN
    result = restored.validate_hmac([KEY])
    assert result.status == ValidationStatus.INVALID_SIGNATURE


def test_hmac_chain_rejects_wrong_key():
    chain = _signed_chain()
    result = chain.validate_hmac([b"another-key"])
    assert result.status == ValidationStatus.INVALID_SIGNATURE


def test_hmac_chain_unsigned_node_rejected():
    chain = DelegationChain.create("agent-root")
    chain.add_delegation("agent-root", "agent-child", DelegationCapability.READ)
    result = chain.validate_hmac([KEY])
    assert result.status == ValidationStatus.INVALID_SIGNATURE

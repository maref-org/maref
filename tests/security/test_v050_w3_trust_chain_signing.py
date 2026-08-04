"""
v0.50 W3-S2 — DelegationChain 签名验证测试（I11）

覆盖：
- create() 支持根签名，add_delegation() 节点签名入链
- validate() 验签失败返回 INVALID_SIGNATURE（原枚举未用）
- 篡改 agent_id / 伪造签名链被拒绝
"""

from __future__ import annotations

from maref.security.trust_chain import (
    DelegationCapability,
    DelegationChain,
    ValidationStatus,
)
from maref.signing.signing_key import ReportSigningKey


def _make_key() -> ReportSigningKey:
    return ReportSigningKey.generate()


class TestW3S2ChainSigning:
    def test_create_with_root_signature(self) -> None:
        root_key = _make_key()
        chain = DelegationChain.create_signed(
            root_agent_id="agent-root",
            root_signing_key=root_key,
        )
        assert chain.root_agent_id == "agent-root"
        assert len(chain.nodes) == 1
        assert chain.nodes[0].signature != ""

    def test_add_delegation_signs_node(self) -> None:
        root_key = _make_key()
        chain = DelegationChain.create_signed(
            root_agent_id="agent-root",
            root_signing_key=root_key,
        )
        ok = chain.add_delegation_signed(
            parent_agent_id="agent-root",
            child_agent_id="agent-child",
            capability=DelegationCapability.EXECUTE,
            signing_key=root_key,
        )
        assert ok is True
        assert len(chain.nodes) == 2
        assert chain.nodes[1].signature != ""
        assert chain.nodes[1].signer_id == "agent-root"

    def test_validate_passes_for_signed_chain(self) -> None:
        root_key = _make_key()
        chain = DelegationChain.create_signed(
            root_agent_id="agent-root",
            root_signing_key=root_key,
        )
        chain.add_delegation_signed(
            parent_agent_id="agent-root",
            child_agent_id="agent-child",
            capability=DelegationCapability.EXECUTE,
            signing_key=root_key,
        )
        result = chain.validate_signed(
            public_keys={
                "agent-root": root_key.public_key_pem,
                "agent-child": root_key.public_key_pem,
            }
        )
        assert result.status == ValidationStatus.VALID

    def test_validate_rejects_tampered_node(self) -> None:
        root_key = _make_key()
        chain = DelegationChain.create_signed(
            root_agent_id="agent-root",
            root_signing_key=root_key,
        )
        chain.add_delegation_signed(
            parent_agent_id="agent-root",
            child_agent_id="agent-child",
            capability=DelegationCapability.EXECUTE,
            signing_key=root_key,
        )
        chain.nodes[1].agent_id = "agent-evil"
        result = chain.validate_signed(
            public_keys={
                "agent-root": root_key.public_key_pem,
                "agent-child": root_key.public_key_pem,
            }
        )
        assert result.status == ValidationStatus.INVALID_SIGNATURE

    def test_validate_rejects_unknown_signer(self) -> None:
        root_key = _make_key()
        chain = DelegationChain.create_signed(
            root_agent_id="agent-root",
            root_signing_key=root_key,
        )
        result = chain.validate_signed(
            public_keys={"agent-other": root_key.public_key_pem}
        )
        assert result.status == ValidationStatus.INVALID_SIGNATURE

    def test_legacy_chain_without_signatures_still_validates_structurally(self) -> None:
        chain = DelegationChain.create("agent-root")
        assert chain.validate().status == ValidationStatus.VALID

    def test_validate_signed_accepts_unsigned_when_no_verification_requested(self) -> None:
        chain = DelegationChain.create("agent-root")
        result = chain.validate_signed(public_keys={})
        assert result.status == ValidationStatus.VALID

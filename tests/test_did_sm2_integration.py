"""DID 与国密 SM2 集成测试.

覆盖 did_registry.py 的 DIDDocument、register_with_sm2、sign、verify。
"""
from __future__ import annotations

import pytest

from maref.crypto.sm2 import SM2KeyPair
from maref.governance.state_machine import GovernanceStateMachine
from maref.identity.did_registry import AgentDID, DIDDocument, DIDRegistry


class TestDIDDocument:
    def test_to_dict_structure(self) -> None:
        did = AgentDID.generate("test")
        doc = DIDDocument(did=did, public_key="04" + "ab" * 64)
        d = doc.to_dict()
        assert d["id"] == did.did_string
        assert len(d["verificationMethod"]) == 1
        assert d["verificationMethod"][0]["type"] == "SM2VerificationKey2020"
        assert d["verificationMethod"][0]["publicKeyHex"] == "04" + "ab" * 64
        assert d["authentication"] == [f"{did.did_string}#keys-1"]


class TestDIDRegistrySM2:
    def test_register_with_sm2_auto_generates_keypair(self) -> None:
        registry = DIDRegistry()
        did = AgentDID.generate("test")
        sm = GovernanceStateMachine()
        record = registry.register_with_sm2(did, sm)
        assert record.did == did
        kp = registry.get_keypair(did)
        assert kp is not None
        assert kp.public_key.startswith("04")
        doc = registry.resolve_document(did)
        assert doc is not None
        assert doc.public_key == kp.public_key

    def test_register_with_sm2_uses_provided_keypair(self) -> None:
        registry = DIDRegistry()
        did = AgentDID.generate("test")
        sm = GovernanceStateMachine()
        kp = SM2KeyPair.generate()
        record = registry.register_with_sm2(did, sm, keypair=kp)
        assert registry.get_keypair(did) == kp

    def test_sign_and_verify_roundtrip(self) -> None:
        registry = DIDRegistry()
        did = AgentDID.generate("test")
        sm = GovernanceStateMachine()
        registry.register_with_sm2(did, sm)
        data = b"hello maref"
        sig = registry.sign(did, data)
        assert registry.verify(did, data, sig) is True

    def test_verify_tampered_data_fails(self) -> None:
        registry = DIDRegistry()
        did = AgentDID.generate("test")
        sm = GovernanceStateMachine()
        registry.register_with_sm2(did, sm)
        data = b"hello maref"
        sig = registry.sign(did, data)
        assert registry.verify(did, b"tampered", sig) is False

    def test_sign_without_keypair_raises(self) -> None:
        registry = DIDRegistry()
        did = AgentDID.generate("test")
        sm = GovernanceStateMachine()
        registry.register(did, sm)
        with pytest.raises(KeyError):
            registry.sign(did, b"data")

    def test_verify_without_document_raises(self) -> None:
        registry = DIDRegistry()
        did = AgentDID.generate("test")
        sm = GovernanceStateMachine()
        registry.register(did, sm)
        with pytest.raises(KeyError):
            registry.verify(did, b"data", "sig")

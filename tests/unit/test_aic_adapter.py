"""Unit tests for the AIC (Agent Identity Code) adapter."""

from __future__ import annotations

import pytest

from maref.identity.aic_adapter import (
    AIC,
    AICIdentityAdapter,
    AIC_OID_ROOT,
    _base36_encode,
    _crc16_ccitt_false,
    compute_aic_checksum,
)
from maref.identity.did_registry import AgentDID


class TestCRC16:
    """Tests for the CRC-16/CCITT-FALSE primitive."""

    def test_known_vector_empty(self) -> None:
        # CRC-16/CCITT-FALSE of empty bytes is 0xFFFF.
        assert _crc16_ccitt_false(b"") == 0xFFFF

    def test_known_vector_123456789(self) -> None:
        # Standard check value for CRC-16/CCITT-FALSE.
        assert _crc16_ccitt_false(b"123456789") == 0x29B1

    def test_deterministic(self) -> None:
        assert _crc16_ccitt_false(b"maref") == _crc16_ccitt_false(b"maref")

    def test_different_inputs_different_output(self) -> None:
        assert _crc16_ccitt_false(b"a") != _crc16_ccitt_false(b"b")


class TestBase36:
    """Tests for the Base36 encoder."""

    def test_zero(self) -> None:
        assert _base36_encode(0) == "0"

    def test_single_digit(self) -> None:
        assert _base36_encode(5) == "5"

    def test_ten_becomes_a(self) -> None:
        assert _base36_encode(10) == "a"

    def test_35_becomes_z(self) -> None:
        assert _base36_encode(35) == "z"

    def test_36_becomes_10(self) -> None:
        assert _base36_encode(36) == "10"

    def test_large_value(self) -> None:
        # 36^9 - 1 = zzzzzzzzz (9 z's)
        assert _base36_encode(36 ** 9 - 1) == "z" * 9

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            _base36_encode(-1)


class TestAIC:
    """Tests for the AIC dataclass."""

    def test_aic_string_format(self) -> None:
        aic = AIC(
            arsp="1",
            provider_id="2",
            ontology_seq="3",
            entity_seq="abc123",
            version="1",
            checksum="xy",
        )
        assert aic.aic_string == f"{AIC_OID_ROOT}.1.2.3.abc123.1.xy"

    def test_parse_valid(self) -> None:
        aic_string = f"{AIC_OID_ROOT}.1.2.3.abc123.1.xy"
        aic = AIC.parse(aic_string)
        assert aic.arsp == "1"
        assert aic.provider_id == "2"
        assert aic.ontology_seq == "3"
        assert aic.entity_seq == "abc123"
        assert aic.version == "1"
        assert aic.checksum == "xy"

    def test_parse_normalizes_uppercase_to_lowercase(self) -> None:
        aic_string = f"{AIC_OID_ROOT}.1.2.3.ABC123.1.XY"
        aic = AIC.parse(aic_string)
        assert aic.entity_seq == "abc123"
        assert aic.checksum == "xy"

    def test_parse_invalid_root(self) -> None:
        with pytest.raises(ValueError):
            AIC.parse("1.2.3.4.5.6.7.8")

    def test_parse_missing_field(self) -> None:
        with pytest.raises(ValueError):
            AIC.parse(f"{AIC_OID_ROOT}.1.2.3")

    def test_parse_empty(self) -> None:
        with pytest.raises(ValueError):
            AIC.parse("")

    def test_is_ontology_true(self) -> None:
        aic = AIC("1", "1", "1", "0", "1", "ab")
        assert aic.is_ontology is True

    def test_is_ontology_false(self) -> None:
        aic = AIC("1", "1", "1", "abc", "1", "ab")
        assert aic.is_ontology is False

    def test_generate_produces_valid_checksum(self) -> None:
        aic = AIC.generate()
        assert aic.verify() is True

    def test_generate_with_no_salt(self) -> None:
        # AIC checksums are pure CRC-16 per ACPs spec — no salt involved.
        aic = AIC.generate()
        assert aic.verify() is True

    def test_generate_entity_seq_length(self) -> None:
        aic = AIC.generate()
        assert len(aic.entity_seq) == 9

    def test_verify_tampered_checksum(self) -> None:
        aic = AIC.generate()
        tampered = AIC(
            arsp=aic.arsp,
            provider_id=aic.provider_id,
            ontology_seq=aic.ontology_seq,
            entity_seq=aic.entity_seq,
            version=aic.version,
            checksum="00",
        )
        assert tampered.verify() is False

    def test_to_dict(self) -> None:
        aic = AIC("1", "2", "3", "abc", "1", "xy")
        d = aic.to_dict()
        assert d["arsp"] == "1"
        assert d["provider_id"] == "2"
        assert d["ontology_seq"] == "3"
        assert d["entity_seq"] == "abc"
        assert d["version"] == "1"
        assert d["checksum"] == "xy"
        assert d["aic_string"] == f"{AIC_OID_ROOT}.1.2.3.abc.1.xy"
        assert d["is_ontology"] is False


class TestComputeAICChecksum:
    """Tests for the checksum function."""

    def test_deterministic(self) -> None:
        args = {
            "arsp": "1",
            "provider_id": "2",
            "ontology_seq": "3",
            "entity_seq": "abc123",
            "version": "1",
        }
        assert compute_aic_checksum(**args) == compute_aic_checksum(**args)

    def test_different_entity_different_checksum(self) -> None:
        base = {
            "arsp": "1",
            "provider_id": "2",
            "ontology_seq": "3",
            "version": "1",
        }
        c1 = compute_aic_checksum(entity_seq="abc", **base)
        c2 = compute_aic_checksum(entity_seq="abd", **base)
        assert c1 != c2


class TestAICIdentityAdapter:
    """Tests for the DID ↔ AIC bidirectional mapper."""

    def test_register_new_generates_aic(self) -> None:
        adapter = AICIdentityAdapter()
        did = AgentDID.generate(namespace="test")
        aic = adapter.register_new(did)
        assert aic.verify() is True
        assert adapter.mapping_count == 1

    def test_register_with_precomputed_aic(self) -> None:
        adapter = AICIdentityAdapter()
        did = AgentDID.generate(namespace="test")
        aic = AIC.generate()
        bound = adapter.register(did, aic)
        assert bound.aic_string == aic.aic_string

    def test_register_invalid_checksum_raises(self) -> None:
        adapter = AICIdentityAdapter()
        did = AgentDID.generate()
        bad_aic = AIC("1", "1", "1", "abc", "1", "00")  # wrong checksum
        with pytest.raises(ValueError, match="checksum verification failed"):
            adapter.register(did, bad_aic)

    def test_register_duplicate_did_same_aic_idempotent(self) -> None:
        adapter = AICIdentityAdapter()
        did = AgentDID.generate()
        aic = AIC.generate()
        adapter.register(did, aic)
        # Re-registering the same DID with the same AIC should succeed.
        adapter.register(did, aic)
        assert adapter.mapping_count == 1

    def test_register_duplicate_did_different_aic_raises(self) -> None:
        adapter = AICIdentityAdapter()
        did = AgentDID.generate()
        aic1 = AIC.generate()
        adapter.register(did, aic1)
        aic2 = AIC.generate()
        with pytest.raises(ValueError, match="already registered"):
            adapter.register(did, aic2)

    def test_register_aic_bound_to_different_did_raises(self) -> None:
        adapter = AICIdentityAdapter()
        did1 = AgentDID.generate()
        aic = AIC.generate()
        adapter.register(did1, aic)
        did2 = AgentDID.generate()
        with pytest.raises(ValueError, match="already bound"):
            adapter.register(did2, aic)

    def test_did_to_aic_resolution(self) -> None:
        adapter = AICIdentityAdapter()
        did = AgentDID.generate(namespace="test")
        aic = adapter.register_new(did)
        resolved = adapter.did_to_aic(did)
        assert resolved is not None
        assert resolved.aic_string == aic.aic_string

    def test_aic_to_did_resolution(self) -> None:
        adapter = AICIdentityAdapter()
        did = AgentDID.generate(namespace="test")
        aic = adapter.register_new(did)
        resolved = adapter.aic_to_did(aic)
        assert resolved is not None
        assert resolved == did

    def test_translate_did_to_aic_string(self) -> None:
        adapter = AICIdentityAdapter()
        did = AgentDID.generate(namespace="test")
        aic = adapter.register_new(did)
        result = adapter.translate_did_to_aic_string(did.did_string)
        assert result == aic.aic_string

    def test_translate_did_to_aic_string_unmapped_raises(self) -> None:
        adapter = AICIdentityAdapter()
        with pytest.raises(ValueError, match="No AIC mapping"):
            adapter.translate_did_to_aic_string("did:maref:test:unmapped")

    def test_translate_aic_to_did_string(self) -> None:
        adapter = AICIdentityAdapter()
        did = AgentDID.generate(namespace="test")
        aic = adapter.register_new(did)
        result = adapter.translate_aic_string_to_did(aic.aic_string)
        assert result == did.did_string

    def test_translate_aic_to_did_string_unmapped_raises(self) -> None:
        adapter = AICIdentityAdapter()
        aic = AIC.generate()
        with pytest.raises(ValueError, match="No DID mapping"):
            adapter.translate_aic_string_to_did(aic.aic_string)

    def test_list_mappings(self) -> None:
        adapter = AICIdentityAdapter()
        did1 = AgentDID.generate(namespace="a")
        did2 = AgentDID.generate(namespace="b")
        aic1 = adapter.register_new(did1)
        aic2 = adapter.register_new(did2)
        mappings = adapter.list_mappings()
        assert len(mappings) == 2
        did_strings = {m["did"] for m in mappings}
        aic_strings = {m["aic"] for m in mappings}
        assert did1.did_string in did_strings
        assert did2.did_string in did_strings
        assert aic1.aic_string in aic_strings
        assert aic2.aic_string in aic_strings

    def test_bidirectional_translation_roundtrip(self) -> None:
        """DID → AIC → DID should return the original DID."""
        adapter = AICIdentityAdapter()
        did = AgentDID.generate(namespace="roundtrip")
        adapter.register_new(did)
        aic_string = adapter.translate_did_to_aic_string(did.did_string)
        did_string = adapter.translate_aic_string_to_did(aic_string)
        assert did_string == did.did_string

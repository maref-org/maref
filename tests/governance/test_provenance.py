"""Provenance / InformationFlowGate 单元测试 — IFC-lite (P1-5)."""

from __future__ import annotations

import pytest

from maref.governance.destructive_gate import DestructiveOperationGate, GateVerdict
from maref.governance.provenance import (
    Endorsement,
    InformationFlowGate,
    ProvenanceLabel,
    TaintTracker,
    is_clean_label,
    join_all,
    join_labels,
)
from maref.signing.signing_key import ReportSigningKey

TRUSTED = ProvenanceLabel.TRUSTED
ENDORSED = ProvenanceLabel.ENDORSED
MIXED = ProvenanceLabel.MIXED
UNTRUSTED = ProvenanceLabel.UNTRUSTED


class TestLattice:
    def test_same_labels_preserved(self) -> None:
        assert join_labels(TRUSTED, TRUSTED) == TRUSTED
        assert join_labels(UNTRUSTED, UNTRUSTED) == UNTRUSTED

    def test_clean_join_clean(self) -> None:
        assert join_labels(TRUSTED, ENDORSED) == TRUSTED

    def test_mixed_results(self) -> None:
        assert join_labels(TRUSTED, UNTRUSTED) == MIXED
        assert join_labels(ENDORSED, UNTRUSTED) == MIXED

    def test_join_all_empty_is_trusted(self) -> None:
        assert join_all([]) == TRUSTED

    def test_join_all_mixed(self) -> None:
        assert join_all([TRUSTED, UNTRUSTED, TRUSTED]) == MIXED

    def test_is_clean_label_fail_closed(self) -> None:
        assert is_clean_label("trusted") is True
        assert is_clean_label("endorsed") is True
        assert is_clean_label("mixed") is False
        assert is_clean_label("untrusted") is False
        assert is_clean_label("bogus") is False


class TestTaintTracker:
    def test_unknown_value_is_untrusted(self) -> None:
        tracker = TaintTracker()
        assert tracker.label_of("nope") == UNTRUSTED

    def test_set_and_label_of(self) -> None:
        tracker = TaintTracker()
        tracker.set("v", TRUSTED)
        assert tracker.label_of("v") == TRUSTED

    def test_set_endorsed_rejected(self) -> None:
        tracker = TaintTracker()
        with pytest.raises(ValueError):
            tracker.set("v", ProvenanceLabel.ENDORSED)

    def test_derive_propagates_taint(self) -> None:
        tracker = TaintTracker()
        tracker.set("user_input", UNTRUSTED)
        tracker.set("system", TRUSTED)
        assert tracker.derive("out", ["user_input", "system"]) == MIXED
        assert tracker.label_of("out") == MIXED

    def test_derive_unknown_input_is_tainted(self) -> None:
        tracker = TaintTracker()
        assert tracker.derive("out", ["never-seen"]) == UNTRUSTED

    def test_derive_all_clean(self) -> None:
        tracker = TaintTracker()
        tracker.set("a", TRUSTED)
        tracker.set("b", TRUSTED)
        assert tracker.derive("out", ["a", "b"]) == TRUSTED

    def test_clear_and_count(self) -> None:
        tracker = TaintTracker()
        tracker.set("a", TRUSTED)
        tracker.set("b", TRUSTED)
        assert tracker.count == 2
        tracker.clear()
        assert tracker.count == 0


class TestEndorsement:
    def test_sign_verify(self) -> None:
        key = ReportSigningKey.generate()
        endorsement = Endorsement("v", "did:human:alice")
        endorsement.sign(key)
        assert endorsement.verify(key.public_key_pem) is True

    def test_tampered_endorsement_fails(self) -> None:
        key = ReportSigningKey.generate()
        endorsement = Endorsement("v", "did:human:alice")
        endorsement.sign(key)
        endorsement.value_id = "other"
        assert endorsement.verify(key.public_key_pem) is False


class TestInformationFlowGate:
    def test_check_clean_allowed(self) -> None:
        gate = InformationFlowGate()
        gate.tracker.set("a", TRUSTED)
        assert gate.check(["a"]).allowed is True

    def test_check_tainted_denied(self) -> None:
        gate = InformationFlowGate()
        gate.tracker.set("a", UNTRUSTED)
        decision = gate.check(["a"])
        assert decision.allowed is False
        assert decision.offending == ["a"]

    def test_check_unknown_fail_closed(self) -> None:
        gate = InformationFlowGate()
        assert gate.check(["never-seen"]).allowed is False

    def test_endorse_marks_value_clean(self) -> None:
        gate = InformationFlowGate()
        key = ReportSigningKey.generate()
        gate.tracker.set("v", UNTRUSTED)
        gate.endorse("v", "did:human:alice", key)
        assert gate.tracker.label_of("v") == ProvenanceLabel.ENDORSED
        assert gate.check(["v"]).allowed is True

    def test_apply_endorsement_requires_trusted_key(self) -> None:
        gate = InformationFlowGate()
        key = ReportSigningKey.generate()
        endorsement = Endorsement("v", "did:human:alice")
        endorsement.sign(key)
        assert gate.apply_endorsement(endorsement) is False
        gate.register_endorser("did:human:alice", key.public_key_pem)
        assert gate.apply_endorsement(endorsement) is True

    def test_forged_endorsement_rejected(self) -> None:
        gate = InformationFlowGate()
        real_key = ReportSigningKey.generate()
        gate.register_endorser("did:human:alice", real_key.public_key_pem)
        attacker_key = ReportSigningKey.generate()
        forged = Endorsement("v", "did:human:alice")
        forged.sign(attacker_key)
        assert gate.apply_endorsement(forged) is False


class TestDestructiveGateIntegration:
    def test_untrusted_provenance_forces_block(self) -> None:
        gate = DestructiveOperationGate()
        decision = gate.evaluate("read_data", "read_file", source_labels=["untrusted"])
        assert decision.verdict == GateVerdict.BLOCK
        assert "provenance" in decision.reason.lower()

    def test_mixed_provenance_forces_block(self) -> None:
        gate = DestructiveOperationGate()
        decision = gate.evaluate("read_data", "read_file", source_labels=["endorsed", "untrusted"])
        assert decision.verdict == GateVerdict.BLOCK

    def test_clean_provenance_allows(self) -> None:
        gate = DestructiveOperationGate()
        decision = gate.evaluate("read_data", "read_file", source_labels=["trusted"])
        assert decision.verdict == GateVerdict.ALLOW

    def test_unknown_label_fail_closed(self) -> None:
        gate = DestructiveOperationGate()
        decision = gate.evaluate("read_data", "read_file", source_labels=["bogus"])
        assert decision.verdict == GateVerdict.BLOCK

    def test_no_labels_behavior_unchanged(self) -> None:
        gate = DestructiveOperationGate()
        decision = gate.evaluate("read_data", "read_file")
        assert decision.verdict == GateVerdict.ALLOW

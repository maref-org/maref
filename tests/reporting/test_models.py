from __future__ import annotations

import json

from maref.reporting.models import AuditSummary, GovernanceReport, SystemStateSnapshot


class TestAuditSummary:
    def test_defaults(self) -> None:
        s = AuditSummary()
        assert s.total_events == 0
        assert s.event_types == {}
        assert s.actor_counts == {}

    def test_with_values(self) -> None:
        s = AuditSummary(
            total_events=42,
            time_range_start=1000.0,
            time_range_end=2000.0,
            event_types={"decision": 30, "verify": 12},
            actor_counts={"agent-a": 22, "agent-b": 20},
        )
        assert s.total_events == 42
        assert s.event_types["decision"] == 30


class TestSystemStateSnapshot:
    def test_defaults(self) -> None:
        s = SystemStateSnapshot()
        assert s.governance_state == ""

    def test_with_values(self) -> None:
        s = SystemStateSnapshot(
            governance_state="VERIFY",
            active_agents_count=5,
            merkle_tree_size=1024,
            version="v0.39.0",
        )
        assert s.governance_state == "VERIFY"
        assert s.active_agents_count == 5


class TestGovernanceReport:
    def test_default_report(self) -> None:
        r = GovernanceReport()
        assert r.report_version == "1.0"
        assert r.generated_by == "maref v0.39.0"
        assert r.signature == ""
        assert r.signer_fingerprint == ""
        assert r.merkle_root == ""

    def test_to_json_roundtrip(self) -> None:
        r1 = GovernanceReport(
            signer_fingerprint="abc123",
            merkle_root="deadbeef",
            audit_summary=AuditSummary(total_events=10),
            system_state=SystemStateSnapshot(governance_state="VERIFY"),
            signature="sig_base64_here",
        )
        json_str = r1.to_json()
        r2 = GovernanceReport.from_json(json_str)
        assert r2.signer_fingerprint == "abc123"
        assert r2.merkle_root == "deadbeef"
        assert r2.audit_summary.total_events == 10
        assert r2.system_state.governance_state == "VERIFY"
        assert r2.signature == "sig_base64_here"

    def test_payload_bytes_excludes_signature(self) -> None:
        r = GovernanceReport(
            signature="should_not_appear",
            merkle_root="root123",
        )
        payload = r.payload_bytes()
        payload_dict = json.loads(payload)
        assert "signature" not in payload_dict
        assert payload_dict["merkle_root"] == "root123"

    def test_verify_signature_no_sig_returns_false(self) -> None:
        r = GovernanceReport()
        assert r.verify_signature("anything") is False

    def test_verify_signature_valid(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        kp = Ed25519KeyPair.generate()
        r = GovernanceReport(merkle_root="test-root")
        payload = r.payload_bytes()
        sig = kp.sign(payload)
        import base64

        r = r.model_copy(update={"signature": base64.b64encode(sig).decode("utf-8")})
        assert r.verify_signature(kp.public_key_pem) is True

    def test_verify_signature_tampered(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair

        kp = Ed25519KeyPair.generate()
        r = GovernanceReport(merkle_root="original-root")
        payload = r.payload_bytes()
        sig = kp.sign(payload)
        import base64

        r = r.model_copy(
            update={
                "signature": base64.b64encode(sig).decode("utf-8"),
                "merkle_root": "tampered-root",
            }
        )
        assert r.verify_signature(kp.public_key_pem) is False

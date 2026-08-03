"""v0.47 S4 — peer trust report signing.

When :class:`FederatedTrustEngine` is configured with
``trusted_peer_public_keys`` (key_id → Ed25519 public key PEM), every
submitted :class:`PeerTrustReport` must carry a valid signature over its
canonical fields.  Invalid / unsigned / tampered reports are **discarded**
and recorded in the engine's audit-visible rejection list (fail-closed).

When no trusted keys are configured the engine keeps its historical
behaviour (backward compatible — existing E2E stacks submit unsigned
reports).

Three-state coverage: normal (valid signature accepted), bypass (missing /
forged signature rejected), demotion (unconfigured → unsigned still works).
"""

from __future__ import annotations

from maref.federation.trust import FederatedTrustEngine, PeerTrustReport
from maref.federation.trust_hardening import (
    peer_report_payload,
    sign_peer_report,
    verify_report_signature,
)
from maref.recursive.trust_engine_v2 import TrustEngineV2
from maref.signing.signing_key import ReportSigningKey


def _engine(**kwargs: object) -> FederatedTrustEngine:
    return FederatedTrustEngine(
        local_engine=TrustEngineV2(),
        **kwargs,
    )


def _report(**overrides: object) -> PeerTrustReport:
    fields: dict[str, object] = {
        "agent_id": "did:maref:federated:agent-abc",
        "source_server": "org-remote",
        "trust_score": 88.5,
        "tier": "AA",
        "confidence": 0.9,
    }
    fields.update(overrides)
    return PeerTrustReport(**fields)


# ── Component: payload + signature helpers ────────────────────────────────


def test_payload_is_canonical_and_deterministic() -> None:
    r1 = _report(timestamp=123.0)
    r2 = _report(timestamp=123.0)
    assert peer_report_payload(r1) == peer_report_payload(r2)
    assert isinstance(peer_report_payload(r1), bytes)
    assert b"agent-abc" in peer_report_payload(r1)
    assert b"org-remote" in peer_report_payload(r1)


def test_payload_changes_with_any_field() -> None:
    base = peer_report_payload(_report())
    assert peer_report_payload(_report(trust_score=1.0)) != base
    assert peer_report_payload(_report(source_server="org-evil")) != base
    assert peer_report_payload(_report(agent_id="did:maref:x")) != base
    assert peer_report_payload(_report(confidence=0.1)) != base


def test_sign_and_verify_roundtrip() -> None:
    key = ReportSigningKey.generate()
    report = _report()
    signed = sign_peer_report(report, key, key_id="org-remote")
    assert signed.signature
    assert signed.signer_key_id == "org-remote"
    assert verify_report_signature(signed, {"org-remote": key.public_key_pem}) is True


def test_verify_rejects_wrong_key() -> None:
    key = ReportSigningKey.generate()
    other = ReportSigningKey.generate()
    signed = sign_peer_report(_report(), key, key_id="org-remote")
    assert verify_report_signature(signed, {"org-remote": other.public_key_pem}) is False


def test_verify_rejects_unsigned() -> None:
    assert verify_report_signature(_report(), {"org-remote": "ignored"}) is False


def test_verify_rejects_unknown_key_id() -> None:
    key = ReportSigningKey.generate()
    signed = sign_peer_report(_report(), key, key_id="org-remote")
    assert verify_report_signature(signed, {"other": key.public_key_pem}) is False


def test_verify_rejects_tampered_report() -> None:
    key = ReportSigningKey.generate()
    signed = sign_peer_report(_report(), key, key_id="org-remote")
    signed.trust_score = 99.9
    assert verify_report_signature(signed, {"org-remote": key.public_key_pem}) is False


# ── Engine integration: fail-closed when configured ───────────────────────


def test_valid_signature_accepted() -> None:
    key = ReportSigningKey.generate()
    engine = _engine(
        trusted_peer_public_keys={"org-remote": key.public_key_pem}
    )
    signed = sign_peer_report(_report(), key, key_id="org-remote")
    engine.submit_peer_report(signed)
    reports = engine.get_peer_reports("did:maref:federated:agent-abc")
    assert len(reports) == 1
    assert engine.rejected_report_count == 0


def test_unsigned_rejected_when_configured() -> None:
    key = ReportSigningKey.generate()
    engine = _engine(
        trusted_peer_public_keys={"org-remote": key.public_key_pem}
    )
    engine.submit_peer_report(_report())
    assert engine.get_peer_reports("did:maref:federated:agent-abc") == []
    assert engine.rejected_report_count == 1


def test_forged_signature_rejected() -> None:
    server_key = ReportSigningKey.generate()
    attacker_key = ReportSigningKey.generate()
    engine = _engine(
        trusted_peer_public_keys={"org-remote": server_key.public_key_pem}
    )
    forged = sign_peer_report(_report(), attacker_key, key_id="org-remote")
    engine.submit_peer_report(forged)
    assert engine.get_peer_reports("did:maref:federated:agent-abc") == []
    assert engine.rejected_report_count == 1


def test_tampered_report_rejected() -> None:
    key = ReportSigningKey.generate()
    engine = _engine(
        trusted_peer_public_keys={"org-remote": key.public_key_pem}
    )
    signed = sign_peer_report(_report(), key, key_id="org-remote")
    signed.trust_score = 0.5  # tamper after signing
    engine.submit_peer_report(signed)
    assert engine.get_peer_reports("did:maref:federated:agent-abc") == []
    assert engine.rejected_report_count == 1


def test_unknown_signer_rejected() -> None:
    key = ReportSigningKey.generate()
    engine = _engine(
        trusted_peer_public_keys={"org-remote": key.public_key_pem}
    )
    signed = sign_peer_report(_report(), key, key_id="org-stranger")
    engine.submit_peer_report(signed)
    assert engine.get_peer_reports("did:maref:federated:agent-abc") == []
    assert engine.rejected_report_count == 1


def test_rejected_reports_recorded_for_audit() -> None:
    key = ReportSigningKey.generate()
    engine = _engine(
        trusted_peer_public_keys={"org-remote": key.public_key_pem}
    )
    engine.submit_peer_report(_report(trust_score=10.0))
    engine.submit_peer_report(_report(trust_score=20.0))
    rejected = engine.rejected_reports()
    assert len(rejected) == 2
    assert all(r["reason"] == "invalid_signature" for r in rejected)
    assert {r["trust_score"] for r in rejected} == {10.0, 20.0}
    assert engine.rejected_report_count == 2


def test_rejected_reports_included_in_summary() -> None:
    key = ReportSigningKey.generate()
    engine = _engine(
        trusted_peer_public_keys={"org-remote": key.public_key_pem}
    )
    engine.submit_peer_report(_report())
    summary = engine.federated_summary()
    assert summary["rejected_report_count"] == 1
    assert summary["trusted_peer_count"] == 1


# ── Backward compatibility: unconfigured ──────────────────────────────────


def test_unconfigured_accepts_unsigned_reports() -> None:
    """No trusted keys → historical behaviour (existing E2E keeps working)."""
    engine = _engine()
    engine.submit_peer_report(_report())
    assert len(engine.get_peer_reports("did:maref:federated:agent-abc")) == 1
    assert engine.rejected_report_count == 0
    assert engine.trusted_peer_count == 0


def test_report_to_dict_includes_signature_fields() -> None:
    key = ReportSigningKey.generate()
    signed = sign_peer_report(_report(), key, key_id="org-remote")
    d = signed.to_dict()
    assert d["signature"] == signed.signature
    assert d["signer_key_id"] == "org-remote"

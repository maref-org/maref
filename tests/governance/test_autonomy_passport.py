"""自治护照（P1-T1）——绑定人类委托人的可离线验证行动授权。"""

from __future__ import annotations

import json

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.autonomy_passport import (
    PASSPORT_EVENT,
    PASSPORT_KIND,
    REASON_EXPIRED,
    REASON_NOT_PASSPORT,
    REASON_OK,
    REASON_REVOKED,
    REASON_SCOPE,
    REASON_SIGNATURE,
    REASON_TOOL,
    AutonomyPassport,
)
from maref.governance.verifiable_governance_credential import (
    GovernanceCredentialStore,
    VerifiableGovernanceCredential,
)
from maref.signing.signing_key import ReportSigningKey

AGENT = "did:maref:tenant-a:agent-1"
HUMAN = "did:maref:human:alice"
ROOT = "did:maref:human:alice#delegation-root"


def _issue(**overrides) -> AutonomyPassport:
    params = {
        "agent_did": AGENT,
        "human_principal": HUMAN,
        "delegation_root": ROOT,
        "allowed_tools": ["file.read", "http.get"],
        "task_scope": ["file.read:/data/*", "http.get:api.example.com/*"],
        "signing_key": ReportSigningKey.generate(),
    }
    params.update(overrides)
    return AutonomyPassport.issue_passport(**params)


class TestIssuance:
    def test_passport_binds_human_principal_and_delegation_root(self):
        passport = _issue()

        assert passport.is_passport is True
        assert passport.passport_id.startswith("passport-")
        assert passport.human_principal == HUMAN
        assert passport.delegation_root == ROOT
        assert passport.subject_did == AGENT
        assert passport.allowed_tools == ["file.read", "http.get"]
        assert passport.to_dict()["extensions"]["kind"] == PASSPORT_KIND

    @pytest.mark.parametrize("field", ["human_principal", "delegation_root"])
    def test_missing_binding_refuses_issuance(self, field):
        with pytest.raises(ValueError):
            _issue(**{field: "  "})

    def test_missing_agent_did_refuses_issuance(self):
        with pytest.raises(ValueError):
            _issue(agent_did="")


class TestOfflineVerification:
    def test_valid_with_only_public_key(self):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key)

        result = passport.verify_offline(key.public_key_pem)

        assert result["valid"] is True
        assert result["reason"] == REASON_OK
        assert result["signature_valid"] is True
        assert result["bound"] is True

    def test_json_round_trip_verifies_offline(self):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key)

        restored = AutonomyPassport.from_json(passport.to_json())

        decision = restored.authorize(
            "file.read", "file.read:/data/a", public_key_pem=key.public_key_pem
        )
        assert isinstance(restored, AutonomyPassport)
        assert restored.passport_id == passport.passport_id
        assert decision.allowed is True

    def test_wrong_public_key_rejected(self):
        passport = _issue()
        other = ReportSigningKey.generate()

        result = passport.verify_offline(other.public_key_pem)

        assert result["valid"] is False
        assert result["reason"] == REASON_SIGNATURE

    def test_tampered_extensions_rejected(self):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key)
        passport.extensions["allowed_tools"].append("shell:*")

        result = passport.verify_offline(key.public_key_pem)

        assert result["valid"] is False
        assert result["reason"] == REASON_SIGNATURE

    def test_expired_rejected(self):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key, ttl_seconds=-1)

        result = passport.verify_offline(key.public_key_pem)

        assert result["reason"] == REASON_EXPIRED

    def test_revoked_rejected(self):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key)

        result = passport.verify_offline(key.public_key_pem, revoked=[passport.passport_id])

        assert result["reason"] == REASON_REVOKED

    def test_non_passport_credential_rejected(self):
        key = ReportSigningKey.generate()
        base = VerifiableGovernanceCredential.issue(
            subject_did=AGENT,
            issuer_did=HUMAN,
            scope=["audit"],
            merkle_proof={},
            signing_key=key,
        )
        credential = AutonomyPassport.from_dict(base.to_dict())

        result = credential.verify_offline(key.public_key_pem)

        assert result["reason"] == REASON_NOT_PASSPORT


class TestAuthorization:
    def test_wildcard_allows_and_records_passport_id(self, tmp_path):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key, allowed_tools=["file.*"], task_scope=["file.*"])
        audit = AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key="test-key")

        first = passport.authorize(
            "file.read",
            "file.read:/data/a",
            public_key_pem=key.public_key_pem,
            audit=audit,
        )
        second = passport.authorize(
            "file.write",
            "file.write:/data/b",
            public_key_pem=key.public_key_pem,
            audit=audit,
        )

        assert first.allowed is True and first.reason == REASON_OK
        assert second.allowed is True
        events = audit.read_filtered(event_type=PASSPORT_EVENT)
        assert len(events) == 2
        assert all(e.metadata["passport_id"] == passport.passport_id for e in events)
        assert events[0].metadata["tool"] == "file.read"

    def test_tool_not_in_whitelist_denied(self, tmp_path):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key)
        audit = AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key="test-key")

        decision = passport.authorize(
            "shell.exec",
            "file.read:/data/a",
            public_key_pem=key.public_key_pem,
            audit=audit,
        )

        assert decision.allowed is False
        assert decision.reason == REASON_TOOL
        assert decision.passport_id == passport.passport_id
        assert audit.read_filtered(event_type=PASSPORT_EVENT) == []

    def test_action_out_of_scope_denied(self, tmp_path):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key)

        decision = passport.authorize(
            "file.read", "file.read:/etc/passwd", public_key_pem=key.public_key_pem
        )

        assert decision.allowed is False
        assert decision.reason == REASON_SCOPE

    def test_expired_passport_denied(self):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key, ttl_seconds=-1)

        decision = passport.authorize(
            "file.read", "file.read:/data/a", public_key_pem=key.public_key_pem
        )

        assert decision.allowed is False
        assert decision.reason == REASON_EXPIRED

    def test_revoked_passport_denied(self):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key)

        decision = passport.authorize(
            "file.read",
            "file.read:/data/a",
            public_key_pem=key.public_key_pem,
            revoked={passport.passport_id: "operator revoked"},
        )

        assert decision.allowed is False
        assert decision.reason == REASON_REVOKED

    def test_decision_serializes(self):
        key = ReportSigningKey.generate()
        decision = _issue(signing_key=key).authorize(
            "nope", "nope", public_key_pem=key.public_key_pem
        )

        payload = decision.to_dict()
        assert payload["allowed"] is False
        assert payload["reason"] == REASON_TOOL
        assert payload["passport_id"].startswith("passport-")

    def test_missing_public_key_fails_closed(self):
        """未显式提供签发方公钥时，不得回退到护照自带公钥自我授权。"""
        decision = _issue().authorize("file.read", "file.read:/data/a")

        assert decision.allowed is False
        assert decision.reason == REASON_SIGNATURE


class TestStoreReuse:
    def test_store_revocation_list_used_for_offline_check(self):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key)
        store = GovernanceCredentialStore()
        store.store(passport)
        store.revoke(passport.passport_id, reason="compromised")

        result = passport.verify_offline(key.public_key_pem, revoked=store.revocation_list())

        assert result["reason"] == REASON_REVOKED

    def test_signed_revocation_list_round_trip(self, tmp_path):
        key = ReportSigningKey.generate()
        passport = _issue(signing_key=key)
        store = GovernanceCredentialStore()
        store.store(passport)
        store.revoke(passport.passport_id, reason="compromised")
        path = tmp_path / "revoked.json"
        store.save_signed_revocation_list(path, key)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert GovernanceCredentialStore.verify_signed_revocation_list(data) is True
        assert passport.passport_id in data["revoked"]

        result = passport.verify_offline(key.public_key_pem, revoked=data["revoked"])
        assert result["reason"] == REASON_REVOKED

        data["revoked"][passport.passport_id] = "tampered"
        assert GovernanceCredentialStore.verify_signed_revocation_list(data) is False

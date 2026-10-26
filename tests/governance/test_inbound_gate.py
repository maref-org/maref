"""入向边界（P1-T2）——外部请求认证、护照、委托链前置校验。"""

from __future__ import annotations

import copy
import json
import time

from maref.federation.federation_auth import (
    FederationRequestSigner,
    FederationRequestVerifier,
)
from maref.governance.audit import AuditLogger
from maref.governance.autonomy_passport import AutonomyPassport
from maref.governance.inbound_gate import INBOUND_EVENT, InboundGate, InboundRequest
from maref.security.trust_chain import DelegationCapability, DelegationChain
from maref.signing.signing_key import ReportSigningKey

SOURCE_AGENT = "did:maref:fed:agent-3"
HUMAN = "did:maref:human:alice"
OTHER_HUMAN = "did:maref:human:mallory"
HMAC_KEY = b"test-federation-hmac-key"
KEY_ID = "org-external"
METHOD = "POST"
PATH = "/api/v1/federation/agents"
BODY = b'{"aic":"aic:example"}'
ACTION = "federation.register"
TOOL = "federation.register"


class _Fixture:
    def __init__(self, tmp_path, **passport_overrides):
        self.fed_key = ReportSigningKey.generate()
        self.issuer_key = ReportSigningKey.generate()
        self.audit = AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key="test-key")
        self.chain = _chain()
        passport_params = {
            "agent_did": SOURCE_AGENT,
            "human_principal": HUMAN,
            "delegation_root": HUMAN,
            "allowed_tools": [TOOL],
            "task_scope": [ACTION],
            "signing_key": self.issuer_key,
            "issuer_did": HUMAN,
        }
        passport_params.update(passport_overrides)
        self.passport = AutonomyPassport.issue_passport(**passport_params)
        self.verifier = FederationRequestVerifier({KEY_ID: self.fed_key.public_key_pem})

    def gate(self, **overrides) -> InboundGate:
        options = {
            "verifier": self.verifier,
            "passport_public_keys": {HUMAN: self.issuer_key.public_key_pem},
            "hmac_keys": [HMAC_KEY],
            "audit": self.audit,
        }
        options.update(overrides)
        return InboundGate(**options)

    def request(self, **overrides) -> InboundRequest:
        base = {
            "source_agent_did": SOURCE_AGENT,
            "action": ACTION,
            "tool": TOOL,
            "method": METHOD,
            "path": PATH,
            "body": BODY,
            "auth_header": self.signed_header(),
            "body_hash_header": _body_hash(),
            "nonce": "nonce-1",
            "passport": self.passport.to_dict(),
            "delegation_chain": self.chain.to_dict(),
        }
        base.update(overrides)
        return InboundRequest(**base)

    def signed_header(
        self,
        timestamp: int | None = None,
        body: bytes = BODY,
        nonce: str = "nonce-1",
    ) -> str:
        signer = FederationRequestSigner(self.fed_key, KEY_ID)
        return signer.sign(METHOD, PATH, body, timestamp=timestamp, nonce=nonce)["X-MAREF-Fed-Auth"]


def _body_hash(body: bytes = BODY) -> str:
    import hashlib

    return hashlib.sha256(body).hexdigest()


def _chain(root_principal: str = HUMAN, tail: str = SOURCE_AGENT) -> DelegationChain:
    chain = DelegationChain.create_hmac(
        "did:maref:fed:agent-1",
        HMAC_KEY,
        root_principal=root_principal,
        max_depth=5,
    )
    assert chain.add_delegation_hmac(
        "did:maref:fed:agent-1",
        "did:maref:fed:agent-2",
        DelegationCapability.DELEGATE,
        HMAC_KEY,
    )
    assert chain.add_delegation_hmac(
        "did:maref:fed:agent-2",
        tail,
        DelegationCapability.DELEGATE,
        HMAC_KEY,
    )
    return chain


class TestAuthentication:
    def test_valid_request_allowed(self, tmp_path):
        fixture = _Fixture(tmp_path)

        decision = fixture.gate().evaluate(fixture.request())

        assert decision.allowed is True
        assert decision.passport_id == fixture.passport.passport_id
        assert decision.chain_digest

    def test_missing_auth_header_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)

        decision = fixture.gate().evaluate(fixture.request(auth_header=""))

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:unauthenticated"

    def test_forged_signature_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)
        other = ReportSigningKey.generate()
        forged = FederationRequestSigner(other, KEY_ID).sign(METHOD, PATH, BODY)["X-MAREF-Fed-Auth"]

        decision = fixture.gate().evaluate(fixture.request(auth_header=forged))

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:unauthenticated"

    def test_body_tampering_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)

        decision = fixture.gate().evaluate(fixture.request(body=b'{"aic":"tampered"}'))

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:unauthenticated"

    def test_expired_timestamp_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)

        decision = fixture.gate().evaluate(
            fixture.request(auth_header=fixture.signed_header(timestamp=int(time.time()) - 1000))
        )

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:unauthenticated"

    def test_nonce_replay_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)
        gate = fixture.gate()
        request = fixture.request(
            nonce="replay-nonce", auth_header=fixture.signed_header(nonce="replay-nonce")
        )

        first = gate.evaluate(request)
        second = gate.evaluate(request)

        assert first.allowed is True
        assert second.allowed is False
        assert second.rule == "inbound_gate:unauthenticated"

    def test_nonce_is_covered_by_signature(self, tmp_path):
        """换新 nonce 重放旧签名必须被拒绝（nonce 已纳入签名载荷）。"""
        fixture = _Fixture(tmp_path)
        gate = fixture.gate()
        replay = fixture.request(
            nonce="fresh-nonce", auth_header=fixture.signed_header(nonce="original-nonce")
        )

        decision = gate.evaluate(replay)

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:unauthenticated"

    def test_missing_nonce_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)

        decision = fixture.gate().evaluate(fixture.request(nonce=""))

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:nonce_missing"


class TestPassport:
    def test_missing_passport_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)

        decision = fixture.gate().evaluate(fixture.request(passport=None))

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:passport_missing"

    def test_action_outside_scope_denied(self, tmp_path):
        fixture = _Fixture(tmp_path, task_scope=["other.action"])

        decision = fixture.gate().evaluate(fixture.request())

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:passport_action_out_of_scope"

    def test_tool_not_whitelisted_denied(self, tmp_path):
        fixture = _Fixture(tmp_path, allowed_tools=["file.read"])

        decision = fixture.gate().evaluate(fixture.request())

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:passport_tool_not_allowed"

    def test_expired_passport_denied(self, tmp_path):
        fixture = _Fixture(tmp_path, ttl_seconds=-1)

        decision = fixture.gate().evaluate(fixture.request())

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:passport_expired"

    def test_revoked_passport_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)
        gate = fixture.gate(revoked=[fixture.passport.passport_id])

        decision = gate.evaluate(fixture.request())

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:passport_revoked"

    def test_untrusted_issuer_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)
        gate = fixture.gate(passport_public_keys={})

        decision = gate.evaluate(fixture.request())

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:passport_untrusted_issuer"

    def test_tampered_passport_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)
        document = fixture.passport.to_dict()
        document["extensions"]["allowed_tools"].append("shell:*")

        decision = fixture.gate().evaluate(fixture.request(passport=document))

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:passport_signature_invalid"

    def test_subject_mismatch_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)

        decision = fixture.gate().evaluate(
            fixture.request(source_agent_did="did:maref:fed:agent-9")
        )

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:passport_subject_mismatch"


class TestDelegationChain:
    def test_missing_chain_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)

        decision = fixture.gate().evaluate(fixture.request(delegation_chain=None))

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:delegation_missing"

    def test_broken_hmac_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)
        payload = copy.deepcopy(fixture.chain.to_dict())
        payload["nodes"][1]["signature"] = "0" * 64

        decision = fixture.gate().evaluate(fixture.request(delegation_chain=payload))

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:delegation_denied"

    def test_tail_not_source_agent_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)
        chain = _chain(tail="did:maref:fed:agent-9")

        decision = fixture.gate().evaluate(fixture.request(delegation_chain=chain.to_dict()))

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:delegation_denied"

    def test_root_principal_mismatch_with_passport_denied(self, tmp_path):
        fixture = _Fixture(tmp_path)
        chain = _chain(root_principal=OTHER_HUMAN)

        decision = fixture.gate().evaluate(fixture.request(delegation_chain=chain.to_dict()))

        assert decision.allowed is False
        assert decision.rule == "inbound_gate:delegation_root_mismatch"


class TestAudit:
    def test_allowed_request_writes_inbound_event(self, tmp_path):
        fixture = _Fixture(tmp_path)

        decision = fixture.gate().evaluate(
            fixture.request(
                nonce="audit-nonce", auth_header=fixture.signed_header(nonce="audit-nonce")
            )
        )

        assert decision.allowed is True
        events = fixture.audit.read_filtered(event_type=INBOUND_EVENT)
        assert len(events) == 1
        metadata = events[0].metadata
        assert metadata["source_agent_did"] == SOURCE_AGENT
        assert metadata["passport_id"] == fixture.passport.passport_id
        assert metadata["chain_digest"] == decision.chain_digest
        assert metadata["decision"] is True

    def test_denied_request_writes_inbound_event(self, tmp_path):
        fixture = _Fixture(tmp_path)

        decision = fixture.gate().evaluate(fixture.request(passport=None))

        assert decision.allowed is False
        events = fixture.audit.read_filtered(event_type=INBOUND_EVENT)
        assert len(events) == 1
        assert events[0].metadata["decision"] is False
        assert events[0].metadata["rule"] == "inbound_gate:passport_missing"


def test_decision_serializes(tmp_path):
    fixture = _Fixture(tmp_path)

    payload = fixture.gate().evaluate(fixture.request()).to_dict()

    assert json.loads(json.dumps(payload))["allowed"] is True
    assert payload["rule"] == ""

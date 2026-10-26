"""联邦网关入向边界接线（P1-T2）。"""

from __future__ import annotations

import hashlib

import pytest

from maref.federation.federation_auth import (
    FederationRequestSigner,
    FederationRequestVerifier,
)
from maref.federation.gateway import (
    FederationGateway,
    FederationGatewayError,
    FederationRequest,
)
from maref.governance.audit import AuditLogger
from maref.governance.autonomy_passport import AutonomyPassport
from maref.governance.inbound_gate import InboundGate, InboundRequest
from maref.identity.aic_adapter import AIC
from maref.integration.acs_parser import ACSParser
from maref.orchestration.decomposer import SubTask
from maref.security.trust_chain import DelegationCapability, DelegationChain
from maref.signing.signing_key import ReportSigningKey

SOURCE_AGENT = "did:maref:fed:agent-3"
HUMAN = "did:maref:human:alice"
HMAC_KEY = b"test-federation-hmac-key"
KEY_ID = "org-external"
METHOD = "POST"
PATH = "/api/v1/federation/agents"
ACTION = "federation.register"
TOOL = "federation.register"


def _acs_document() -> dict:
    return (
        ACSParser()
        .from_maref_capabilities(
            aic=AIC.generate().aic_string,
            agent_name="inbound-agent",
            agent_description="P1-T2 inbound boundary",
            capabilities=["research"],
            endpoint_url="http://127.0.0.1:9999",
            provider_organization="external",
        )
        .to_dict()
    )


def _chain() -> DelegationChain:
    chain = DelegationChain.create_hmac(
        "did:maref:fed:agent-1",
        HMAC_KEY,
        root_principal=HUMAN,
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
        SOURCE_AGENT,
        DelegationCapability.DELEGATE,
        HMAC_KEY,
    )
    return chain


def _build(tmp_path, *, with_passport: bool = True):
    fed_key = ReportSigningKey.generate()
    issuer_key = ReportSigningKey.generate()
    audit = AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    passport = AutonomyPassport.issue_passport(
        agent_did=SOURCE_AGENT,
        human_principal=HUMAN,
        delegation_root=HUMAN,
        allowed_tools=[TOOL],
        task_scope=[ACTION],
        signing_key=issuer_key,
        issuer_did=HUMAN,
    )
    body = b'{"aic":"aic:example"}'
    auth = FederationRequestSigner(fed_key, KEY_ID).sign(METHOD, PATH, body)[
        "X-MAREF-Fed-Auth"
    ]
    inbound = InboundRequest(
        source_agent_did=SOURCE_AGENT,
        action=ACTION,
        tool=TOOL,
        method=METHOD,
        path=PATH,
        body=body,
        auth_header=auth,
        body_hash_header=hashlib.sha256(body).hexdigest(),
        nonce="gateway-nonce-1",
        passport=passport.to_dict() if with_passport else None,
        delegation_chain=_chain().to_dict(),
    )
    gate = InboundGate(
        verifier=FederationRequestVerifier({KEY_ID: fed_key.public_key_pem}),
        passport_public_keys={HUMAN: issuer_key.public_key_pem},
        hmac_keys=[HMAC_KEY],
        audit=audit,
    )
    return gate, inbound, audit


def _registration_request(inbound) -> FederationRequest:
    acs_doc = _acs_document()
    return FederationRequest(
        aic_string=acs_doc["aic"],
        acs_document=acs_doc,
        endpoint_url="http://127.0.0.1:9999",
        protocol="a2a",
        inbound=inbound,
    )


def test_valid_inbound_request_registers_agent(tmp_path):
    gate, inbound, audit = _build(tmp_path)
    gateway = FederationGateway(
        audit_logger=audit,
        inbound_gate=gate,
    )

    response = gateway.register_agent(_registration_request(inbound))

    assert response.success is True
    assert gateway.agent_count == 1
    events = audit.read_filtered(event_type="federation_inbound")
    assert len(events) == 1
    assert events[0].metadata["source_agent_did"] == SOURCE_AGENT
    assert events[0].metadata["passport_id"].startswith("passport-")


def test_gate_requires_inbound_envelope(tmp_path):
    gate, _, audit = _build(tmp_path)
    gateway = FederationGateway(audit_logger=audit, inbound_gate=gate)

    response = gateway.register_agent(_registration_request(None))

    assert response.success is False
    assert "inbound" in response.error
    assert gateway.agent_count == 0


def test_denied_inbound_blocks_registration(tmp_path):
    gate, inbound, audit = _build(tmp_path, with_passport=False)
    gateway = FederationGateway(audit_logger=audit, inbound_gate=gate)

    response = gateway.register_agent(_registration_request(inbound))

    assert response.success is False
    assert "passport" in response.error
    assert gateway.agent_count == 0
    denied = audit.read_filtered(event_type="federation_inbound")
    assert len(denied) == 1
    assert denied[0].metadata["decision"] is False


def test_dispatch_requires_inbound_envelope(tmp_path):
    gate, _, audit = _build(tmp_path)
    gateway = FederationGateway(audit_logger=audit, inbound_gate=gate)
    task = SubTask(
        task_id="task-1",
        description="research",
        estimated_complexity=0.5,
        required_capabilities=["research"],
    )

    with pytest.raises(FederationGatewayError, match="inbound"):
        gateway.dispatch_task(task)


def test_dispatch_valid_inbound_without_dispatcher_returns_none(tmp_path):
    gate, inbound, audit = _build(tmp_path)
    gateway = FederationGateway(audit_logger=audit, inbound_gate=gate)
    task = SubTask(
        task_id="task-1",
        description="research",
        estimated_complexity=0.5,
        required_capabilities=["research"],
    )

    assert gateway.dispatch_task(task, inbound=inbound) is None


def test_gateway_without_gate_keeps_legacy_behaviour(tmp_path):
    acs_doc = _acs_document()
    gateway = FederationGateway()

    response = gateway.register_agent(
        FederationRequest(
            aic_string=acs_doc["aic"],
            acs_document=acs_doc,
            endpoint_url="http://127.0.0.1:9999",
        )
    )

    assert response.success is True
    assert gateway.agent_count == 1
    assert response.did_string

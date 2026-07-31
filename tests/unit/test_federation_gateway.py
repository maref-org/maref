"""Unit tests for the Federation Gateway."""

from __future__ import annotations

import pytest

from maref.federation.gateway import (
    FederatedAgent,
    FederationGateway,
    FederationGatewayError,
    FederationRequest,
    FederationResponse,
)
from maref.identity.aic_adapter import AIC, AICIdentityAdapter
from maref.identity.did_registry import AgentDID, DIDRegistry
from maref.integration.acs_parser import ACSParser
from maref.orchestration.decomposer import SubTask
from maref.orchestration.dispatcher import AgentDispatcher


@pytest.fixture
def acs_document() -> dict:
    return {
        "aic": "",  # filled in by test
        "name": "federated-agent",
        "description": "A federated test agent",
        "protocolVersion": "2.00",
        "version": "1.0",
        "provider": {
            "organization": "TestOrg",
        },
        "capabilities": {
            "streaming": False,
            "notification": False,
            "messageQueue": [],
        },
        "endpoints": [
            {
                "url": "https://agent.example.com/api",
                "transport": "HTTP_JSON",
                "security": ["mutualTLS"],
            }
        ],
        "skills": [
            {
                "id": "research",
                "name": "Research",
                "description": "Research capability",
            },
            {
                "id": "analysis",
                "name": "Analysis",
                "description": "Analysis capability",
            },
        ],
        "securitySchemes": {
            "mutualTLS": {"type": "mutualTLS"},
        },
    }


@pytest.fixture
def gateway() -> FederationGateway:
    return FederationGateway(
        identity_adapter=AICIdentityAdapter(),
        acs_parser=ACSParser(),
        dispatcher=AgentDispatcher(),
        did_registry=DIDRegistry(),
    )


@pytest.fixture
def valid_aic_string() -> str:
    aic = AIC.generate()
    return aic.aic_string


class TestFederationRequest:
    def test_defaults(self) -> None:
        req = FederationRequest(
            aic_string="aic",
            acs_document={},
            endpoint_url="https://example.com",
        )
        assert req.protocol == "aip"
        assert req.did_namespace == "federated"


class TestFederationResponse:
    def test_defaults(self) -> None:
        resp = FederationResponse(success=False)
        assert resp.did_string == ""
        assert resp.aic_string == ""
        assert resp.error == ""
        assert resp.metadata == {}


class TestFederatedAgent:
    def test_touch_updates_last_seen(self) -> None:
        did = AgentDID.generate()
        aic = AIC.generate()
        from maref.integration.acs_parser import AgentCapabilitySpec

        acs = AgentCapabilitySpec(aic=aic.aic_string, name="n", description="d")
        agent = FederatedAgent(
            did=did,
            aic=aic,
            acs=acs,
            endpoint_url="https://example.com",
            protocol="aip",
            registered_at=0.0,
        )
        assert agent.last_seen == 0.0
        agent.touch()
        assert agent.last_seen > 0.0


class TestFederationGatewayRegister:
    def test_register_agent_success(
        self,
        gateway: FederationGateway,
        acs_document: dict,
        valid_aic_string: str,
    ) -> None:
        acs_document["aic"] = valid_aic_string
        request = FederationRequest(
            aic_string=valid_aic_string,
            acs_document=acs_document,
            endpoint_url="https://agent.example.com/api",
        )
        response = gateway.register_agent(request)
        assert response.success is True
        assert response.aic_string == valid_aic_string
        assert response.did_string.startswith("did:maref:federated:")
        assert gateway.agent_count == 1

    def test_register_agent_invalid_aic(
        self,
        gateway: FederationGateway,
        acs_document: dict,
    ) -> None:
        acs_document["aic"] = "invalid-aic"
        request = FederationRequest(
            aic_string="invalid-aic",
            acs_document=acs_document,
            endpoint_url="https://agent.example.com",
        )
        response = gateway.register_agent(request)
        assert response.success is False
        assert "Invalid AIC" in response.error
        assert gateway.agent_count == 0

    def test_register_agent_invalid_acs(
        self,
        gateway: FederationGateway,
        valid_aic_string: str,
    ) -> None:
        # ACS missing required "name" field
        bad_acs = {
            "aic": valid_aic_string,
            "endpoints": [],
            "skills": [],
        }
        request = FederationRequest(
            aic_string=valid_aic_string,
            acs_document=bad_acs,
            endpoint_url="https://agent.example.com",
        )
        response = gateway.register_agent(request)
        assert response.success is False
        assert "Invalid ACS" in response.error
        assert gateway.agent_count == 0

    def test_register_agent_aic_acs_mismatch(
        self,
        gateway: FederationGateway,
        acs_document: dict,
        valid_aic_string: str,
    ) -> None:
        # ACS document claims a different AIC than the request.
        other_aic = AIC.generate()
        acs_document["aic"] = other_aic.aic_string
        request = FederationRequest(
            aic_string=valid_aic_string,
            acs_document=acs_document,
            endpoint_url="https://agent.example.com",
        )
        response = gateway.register_agent(request)
        assert response.success is False
        assert "AIC mismatch" in response.error
        assert gateway.agent_count == 0

    def test_register_identity_failure_no_did_string(
        self,
        gateway: FederationGateway,
        acs_document: dict,
    ) -> None:
        # Register an AIC first, then try to register the same AIC with a
        # different DID — the identity adapter should reject the duplicate.
        aic = AIC.generate()
        acs_document["aic"] = aic.aic_string
        request1 = FederationRequest(
            aic_string=aic.aic_string,
            acs_document={**acs_document},
            endpoint_url="https://agent1.example.com",
        )
        gateway.register_agent(request1)

        # Second registration with same AIC should fail at identity step.
        request2 = FederationRequest(
            aic_string=aic.aic_string,
            acs_document={**acs_document},
            endpoint_url="https://agent2.example.com",
        )
        response2 = gateway.register_agent(request2)
        assert response2.success is False
        assert "Identity registration failed" in response2.error
        # Issue 8: did_string should NOT be set on identity failure.
        assert response2.did_string == ""

    def test_register_multiple_agents(
        self,
        gateway: FederationGateway,
        acs_document: dict,
    ) -> None:
        for _ in range(3):
            aic = AIC.generate()
            acs_copy = {**acs_document, "aic": aic.aic_string}
            request = FederationRequest(
                aic_string=aic.aic_string,
                acs_document=acs_copy,
                endpoint_url="https://agent.example.com",
            )
            response = gateway.register_agent(request)
            assert response.success is True
        assert gateway.agent_count == 3


class TestFederationGatewayLookup:
    def test_get_agent_by_did(
        self,
        gateway: FederationGateway,
        acs_document: dict,
        valid_aic_string: str,
    ) -> None:
        acs_document["aic"] = valid_aic_string
        request = FederationRequest(
            aic_string=valid_aic_string,
            acs_document=acs_document,
            endpoint_url="https://agent.example.com",
        )
        response = gateway.register_agent(request)
        did = AgentDID.parse(response.did_string)
        agent = gateway.get_agent_by_did(did)
        assert agent is not None
        assert agent.aic.aic_string == valid_aic_string

    def test_get_agent_by_aic(
        self,
        gateway: FederationGateway,
        acs_document: dict,
        valid_aic_string: str,
    ) -> None:
        acs_document["aic"] = valid_aic_string
        request = FederationRequest(
            aic_string=valid_aic_string,
            acs_document=acs_document,
            endpoint_url="https://agent.example.com",
        )
        gateway.register_agent(request)
        agent = gateway.get_agent_by_aic(valid_aic_string)
        assert agent is not None

    def test_list_agents_filtered_by_protocol(
        self,
        gateway: FederationGateway,
        acs_document: dict,
    ) -> None:
        # Register one AIP and one A2A agent
        for protocol in ("aip", "a2a"):
            aic = AIC.generate()
            acs_copy = {**acs_document, "aic": aic.aic_string}
            request = FederationRequest(
                aic_string=aic.aic_string,
                acs_document=acs_copy,
                endpoint_url="https://agent.example.com",
                protocol=protocol,
            )
            gateway.register_agent(request)

        assert len(gateway.list_agents()) == 2
        assert len(gateway.list_agents(protocol_filter="aip")) == 1
        assert len(gateway.list_agents(protocol_filter="a2a")) == 1
        assert len(gateway.list_agents(protocol_filter="mcp")) == 0

    def test_discover_by_capability(
        self,
        gateway: FederationGateway,
        acs_document: dict,
    ) -> None:
        aic = AIC.generate()
        acs_copy = {**acs_document, "aic": aic.aic_string}
        request = FederationRequest(
            aic_string=aic.aic_string,
            acs_document=acs_copy,
            endpoint_url="https://agent.example.com",
        )
        gateway.register_agent(request)
        # The fixture ACS has "research" and "analysis" skills
        research_agents = gateway.discover_by_capability("research")
        assert len(research_agents) == 1
        analysis_agents = gateway.discover_by_capability("analysis")
        assert len(analysis_agents) == 1
        no_agents = gateway.discover_by_capability("nonexistent")
        assert no_agents == []


class TestFederationGatewayUnregister:
    def test_unregister_existing_agent(
        self,
        gateway: FederationGateway,
        acs_document: dict,
        valid_aic_string: str,
    ) -> None:
        acs_document["aic"] = valid_aic_string
        request = FederationRequest(
            aic_string=valid_aic_string,
            acs_document=acs_document,
            endpoint_url="https://agent.example.com",
        )
        response = gateway.register_agent(request)
        did = AgentDID.parse(response.did_string)
        assert gateway.unregister_agent(did) is True
        assert gateway.agent_count == 0
        assert gateway.get_agent_by_aic(valid_aic_string) is None

    def test_unregister_nonexistent_returns_false(self, gateway: FederationGateway) -> None:
        did = AgentDID.generate()
        assert gateway.unregister_agent(did) is False

    def test_unregister_cleans_downstream(
        self,
        gateway: FederationGateway,
        acs_document: dict,
        valid_aic_string: str,
    ) -> None:
        acs_document["aic"] = valid_aic_string
        request = FederationRequest(
            aic_string=valid_aic_string,
            acs_document=acs_document,
            endpoint_url="https://agent.example.com",
        )
        response = gateway.register_agent(request)
        did = AgentDID.parse(response.did_string)

        # Verify downstream registrations exist.
        assert gateway._identity.did_to_aic(did) is not None
        assert gateway._did_registry is not None
        assert gateway._did_registry.resolve(did) is not None
        assert gateway._dispatcher is not None
        assert did in gateway._dispatcher._agent_capabilities

        # Unregister.
        assert gateway.unregister_agent(did) is True

        # Verify downstream registrations are cleaned up.
        assert gateway._identity.did_to_aic(did) is None
        assert gateway._did_registry.resolve(did) is None
        assert did not in gateway._dispatcher._agent_capabilities

    def test_unregister_allows_reregistration(
        self,
        gateway: FederationGateway,
        acs_document: dict,
    ) -> None:
        aic = AIC.generate()
        acs_document["aic"] = aic.aic_string
        request = FederationRequest(
            aic_string=aic.aic_string,
            acs_document={**acs_document},
            endpoint_url="https://agent.example.com",
        )
        response = gateway.register_agent(request)
        did = AgentDID.parse(response.did_string)
        gateway.unregister_agent(did)

        # Same AIC should be re-registerable after unregister.
        response2 = gateway.register_agent(request)
        assert response2.success is True


class TestFederationGatewayTranslation:
    def test_translate_did_to_aic(
        self,
        gateway: FederationGateway,
        acs_document: dict,
        valid_aic_string: str,
    ) -> None:
        acs_document["aic"] = valid_aic_string
        request = FederationRequest(
            aic_string=valid_aic_string,
            acs_document=acs_document,
            endpoint_url="https://agent.example.com",
        )
        response = gateway.register_agent(request)
        translated = gateway.translate_did_to_aic(response.did_string)
        assert translated == valid_aic_string

    def test_translate_aic_to_did(
        self,
        gateway: FederationGateway,
        acs_document: dict,
        valid_aic_string: str,
    ) -> None:
        acs_document["aic"] = valid_aic_string
        request = FederationRequest(
            aic_string=valid_aic_string,
            acs_document=acs_document,
            endpoint_url="https://agent.example.com",
        )
        response = gateway.register_agent(request)
        translated = gateway.translate_aic_to_did(valid_aic_string)
        assert translated == response.did_string

    def test_translate_unknown_did_raises(
        self, gateway: FederationGateway
    ) -> None:
        with pytest.raises(FederationGatewayError):
            gateway.translate_did_to_aic("did:maref:test:unknown")

    def test_translate_unknown_aic_raises(
        self, gateway: FederationGateway
    ) -> None:
        aic = AIC.generate()
        with pytest.raises(FederationGatewayError):
            gateway.translate_aic_to_did(aic.aic_string)


class TestFederationGatewayDispatch:
    def test_dispatch_task_returns_result(
        self,
        gateway: FederationGateway,
        acs_document: dict,
    ) -> None:
        aic = AIC.generate()
        acs_copy = {**acs_document, "aic": aic.aic_string}
        request = FederationRequest(
            aic_string=aic.aic_string,
            acs_document=acs_copy,
            endpoint_url="https://agent.example.com",
        )
        gateway.register_agent(request)

        task = SubTask(
            task_id="task-1",
            description="research task",
            estimated_complexity=0.5,
            required_capabilities=["research"],
        )
        result = gateway.dispatch_task(task)
        assert result is not None
        assert result.task_id == "task-1"

    def test_dispatch_updates_last_seen(
        self,
        gateway: FederationGateway,
        acs_document: dict,
    ) -> None:
        aic = AIC.generate()
        acs_copy = {**acs_document, "aic": aic.aic_string}
        request = FederationRequest(
            aic_string=aic.aic_string,
            acs_document=acs_copy,
            endpoint_url="https://agent.example.com",
        )
        response = gateway.register_agent(request)
        did = AgentDID.parse(response.did_string)
        agent = gateway.get_agent_by_did(did)
        assert agent is not None
        last_seen_before = agent.last_seen

        import time as _time

        _time.sleep(0.01)

        task = SubTask(
            task_id="task-1",
            description="research task",
            estimated_complexity=0.5,
            required_capabilities=["research"],
        )
        gateway.dispatch_task(task)

        # Issue 9: last_seen should be updated after dispatch.
        assert agent.last_seen > last_seen_before

    def test_dispatch_without_dispatcher_returns_none(self) -> None:
        gw = FederationGateway()  # no dispatcher
        task = SubTask(
            task_id="t",
            description="d",
            estimated_complexity=0.1,
            required_capabilities=["c"],
        )
        assert gw.dispatch_task(task) is None


class TestACSVerification:
    def test_register_with_valid_acs_signature(self, acs_document: dict, gateway: FederationGateway) -> None:
        import json

        from maref.crypto.ed25519_keys import Ed25519KeyPair
        aic = AIC.generate()
        doc = dict(acs_document, aic=aic.aic_string)
        kp = Ed25519KeyPair.generate()
        sig = kp.sign(json.dumps(doc, sort_keys=True).encode()).hex()
        req = FederationRequest(
            aic_string=aic.aic_string,
            acs_document=doc,
            endpoint_url="https://agent.example.com/api",
            acs_signature=sig,
            acs_public_key_pem=kp.public_key_pem,
        )
        resp = gateway.register_agent(req)
        assert resp.success is True
        assert resp.did_string != ""

    def test_register_with_invalid_acs_signature_rejected(self, acs_document: dict, gateway: FederationGateway) -> None:
        import json

        from maref.crypto.ed25519_keys import Ed25519KeyPair
        aic = AIC.generate()
        doc = dict(acs_document, aic=aic.aic_string)
        real_kp = Ed25519KeyPair.generate()
        fake_kp = Ed25519KeyPair.generate()
        acs_bytes = json.dumps(doc, sort_keys=True).encode()
        wrong_sig = real_kp.sign(acs_bytes).hex()
        req = FederationRequest(
            aic_string=aic.aic_string,
            acs_document=doc,
            endpoint_url="https://evil.com/api",
            acs_signature=wrong_sig,
            acs_public_key_pem=fake_kp.public_key_pem,
        )
        resp = gateway.register_agent(req)
        assert resp.success is False
        assert "signature" in resp.error.lower()

    def test_register_without_signature_succeeds(self, acs_document: dict, gateway: FederationGateway) -> None:
        aic = AIC.generate()
        doc = dict(acs_document, aic=aic.aic_string)
        req = FederationRequest(
            aic_string=aic.aic_string,
            acs_document=doc,
            endpoint_url="https://agent.example.com/api",
        )
        resp = gateway.register_agent(req)
        assert resp.success is True

    def test_stored_agent_has_signature_fields(self, acs_document: dict, gateway: FederationGateway) -> None:
        import json

        from maref.crypto.ed25519_keys import Ed25519KeyPair
        aic = AIC.generate()
        doc = dict(acs_document, aic=aic.aic_string)
        kp = Ed25519KeyPair.generate()
        sig = kp.sign(json.dumps(doc, sort_keys=True).encode()).hex()
        req = FederationRequest(
            aic_string=aic.aic_string,
            acs_document=doc,
            endpoint_url="https://agent.example.com/api",
            acs_signature=sig,
            acs_public_key_pem=kp.public_key_pem,
        )
        gateway.register_agent(req)
        agent = gateway.get_agent_by_aic(aic.aic_string)
        assert agent is not None
        assert agent.acs_signature == sig
        assert agent.acs_public_key_pem == kp.public_key_pem
        assert agent.acs_digest != ""
        assert agent.verify_acs_integrity(raw_acs_document=doc) is True


class TestFederationGatewaySummary:
    def test_summary_initial_state(self) -> None:
        gw = FederationGateway()
        summary = gw.gateway_summary()
        assert summary["agent_count"] == 0
        assert summary["identity_mapping_count"] == 0
        assert summary["protocols"] == {}
        assert summary["has_dispatcher"] is False
        assert summary["has_audit"] is False

    def test_summary_after_registration(
        self,
        gateway: FederationGateway,
        acs_document: dict,
    ) -> None:
        aic = AIC.generate()
        acs_copy = {**acs_document, "aic": aic.aic_string}
        request = FederationRequest(
            aic_string=aic.aic_string,
            acs_document=acs_copy,
            endpoint_url="https://agent.example.com",
            protocol="aip",
        )
        gateway.register_agent(request)

        summary = gateway.gateway_summary()
        assert summary["agent_count"] == 1
        assert summary["identity_mapping_count"] == 1
        assert summary["protocols"] == {"aip": 1}
        assert summary["has_dispatcher"] is True

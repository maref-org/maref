"""Phase 3.4 — global identity service.

Covers the two sub-goals of task 3.4:

1. **DID registration / resolution / deactivation over HTTP** — the
   :class:`~maref.federation.identity_service.IdentityService` exposes a
   ``did:maref:{namespace}:{id}`` lifecycle: create (auto-derives a fresh
   ACPs AIC), resolve to a W3C DID Document, soft-deactivate (resolution
   then reports ``deactivated``).
2. **AIC derivation + verification** — every created DID carries a
   checksum-correct AIC (AUTOSAR CRC-16/CCITT-FALSE) that can be verified
   and translated back to its DID over HTTP.

The E2E test boots a real HTTP server and exercises the full lifecycle:
create → resolve → verify → DID↔AIC translation → deactivate.
"""

from __future__ import annotations

import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.federation.federation_http import (
    FederationHTTPClient,
    create_federation_app,
)
from maref.federation.gateway import FederationGateway
from maref.federation.identity_service import IdentityService
from maref.federation.policy import FederationPolicyEngine
from maref.federation.policy_subscriber import FederatedPolicySubscriber
from maref.federation.trust import FederatedTrustEngine
from maref.recursive.trust_engine_v2 import TrustEngineV2

HEALTH_PATH = "/api/v1/federation/health"


def _build_identity_app(
    server_id: str,
    identity: IdentityService,
) -> FastAPI:
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    subscriber = FederatedPolicySubscriber(
        local_engine=FederationPolicyEngine(),
        local_org=server_id,
    )
    return create_federation_app(
        gateway,
        trust_engine,
        subscriber,
        server_id=server_id,
        identity_service=identity,
    )


class ThreadedIdentityServer:
    """Run a federation FastAPI app under uvicorn in a background thread."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""

    def start(self) -> None:
        config = uvicorn.Config(self._app, host="127.0.0.1", port=0, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.time() + 15.0
        while time.time() < deadline:
            if self._server.started and self._server.servers:
                port = self._server.servers[0].sockets[0].getsockname()[1]
                self.base_url = f"http://127.0.0.1:{port}"
                deadline2 = time.time() + 5.0
                while time.time() < deadline2:
                    try:
                        response = httpx.get(f"{self.base_url}{HEALTH_PATH}", timeout=1.0)
                        if response.status_code == 200:
                            return
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.05)
                return
            time.sleep(0.05)
        raise RuntimeError("threaded identity server failed to start")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10.0)


# ── Component tests ──────────────────────────────────────────────────────


def test_create_resolve_verify_cycle() -> None:
    """create → resolve (W3C doc) → verify AIC: the full happy path."""
    service = IdentityService()
    keypair = Ed25519KeyPair.generate()
    services = [
        {
            "id": "did:maref:ns:placeholder#a2a",
            "type": "A2AAgentService",
            "serviceEndpoint": "https://agent.example.com/a2a",
        }
    ]
    result = service.create_did(
        namespace="ns",
        roles=["worker"],
        ed25519_public_key_pem=keypair.public_key_pem,
        service_endpoints=services,
    )
    assert result.did.startswith("did:maref:ns:")
    assert result.registered_at > 0

    resolved = service.resolve_did(result.did)
    assert resolved["resolution_metadata"]["resolved"] is True
    doc = resolved["did_document"]
    assert doc["id"] == result.did
    assert doc["verificationMethod"][0]["publicKeyPem"] == keypair.public_key_pem
    assert doc["service"] == services

    verified = service.verify_aic(result.aic)
    assert verified["valid"] is True
    assert verified["checksum_valid"] is True
    assert verified["bound"] is True
    assert verified["did"] == result.did


def test_create_derives_crc16_valid_aic_and_bidirectional() -> None:
    """Derived AIC passes CRC-16 and translates DID↔AIC both ways."""
    service = IdentityService()
    result = service.create_did(namespace="acme")
    assert service.verify_aic(result.aic)["checksum_valid"] is True
    assert service.did_to_aic(result.did) == result.aic
    assert service.aic_to_did(result.aic) == result.did


def test_resolve_unknown_not_found() -> None:
    service = IdentityService()
    resolved = service.resolve_did("did:maref:ns:deadbeef")
    assert resolved["resolution_metadata"]["error"] == "notFound"
    assert "did_document" not in resolved


def test_resolve_invalid_format() -> None:
    service = IdentityService()
    resolved = service.resolve_did("not-a-did")
    assert resolved["resolution_metadata"]["error"] == "invalidDid"


def test_deactivate_then_resolve_deactivated() -> None:
    service = IdentityService()
    result = service.create_did(namespace="ns")
    status = service.deactivate_did(result.did)
    assert status["success"] is True
    # Resolution now reports deactivated (record retained).
    resolved = service.resolve_did(result.did)
    assert resolved["resolution_metadata"]["error"] == "deactivated"
    assert resolved["document_metadata"]["deactivated"] is True
    # Idempotent: re-deactivating reports already_deactivated.
    assert service.deactivate_did(result.did)["already_deactivated"] is True
    # AIC still bound but flagged deactivated.
    verified = service.verify_aic(result.aic)
    assert verified["bound"] is True
    assert verified["deactivated"] is True


def test_deactivate_unknown_raises() -> None:
    service = IdentityService()
    with pytest.raises(ValueError):
        service.deactivate_did("did:maref:ns:nope")


def test_verify_aic_tampered_invalid() -> None:
    service = IdentityService()
    result = service.create_did(namespace="ns")
    # Flip one checksum character → CRC-16 fails.
    tampered = result.aic[:-1] + ("0" if result.aic[-1] != "0" else "1")
    verified = service.verify_aic(tampered)
    assert verified["valid"] is False
    assert verified["checksum_valid"] is False
    assert verified["bound"] is False
    # Malformed string → invalid_format.
    assert service.verify_aic("garbage")["reason"] == "invalid_format"


def test_verify_unbound_but_checksum_valid_aic() -> None:
    """A well-formed AIC with a valid CRC but no DID mapping."""
    service = IdentityService()
    result = service.create_did(namespace="ns")
    # Re-derive the checksum-correct AIC without registering it.
    from maref.identity.aic_adapter import AIC

    fresh = AIC.generate()
    while fresh.aic_string == result.aic:
        fresh = AIC.generate()
    verified = service.verify_aic(fresh.aic_string)
    assert verified["valid"] is True
    assert verified["bound"] is False
    assert verified["did"] is None


def test_list_identities_and_summary() -> None:
    service = IdentityService()
    service.create_did(namespace="ns", roles=["worker"])
    deactivated = service.create_did(namespace="ns")
    service.deactivate_did(deactivated.did)
    identities = service.list_identities()
    assert len(identities) == 2
    by_did = {i["did"]: i for i in identities}
    assert by_did[deactivated.did]["deactivated"] is True
    summary = service.summary()
    assert summary["identities"] == 2
    assert summary["deactivated"] == 1
    assert summary["aic_mappings"] == 2


def test_persistence_roundtrip(tmp_path) -> None:
    """Identity state survives a restart via the JSONL change log."""
    store_path = tmp_path / "identity.jsonl"
    service = IdentityService(persist_path=store_path)
    result = service.create_did(
        namespace="ns",
        roles=["worker"],
        ed25519_public_key_pem="pem-x",
    )
    service.deactivate_did(result.did)
    service.close()

    reloaded = IdentityService(persist_path=store_path)
    resolved = reloaded.resolve_did(result.did)
    assert resolved["resolution_metadata"]["error"] == "deactivated"
    assert reloaded.verify_aic(result.aic)["did"] == result.did
    assert reloaded.verify_aic(result.aic)["deactivated"] is True
    assert reloaded.summary()["identities"] == 1
    assert reloaded.summary()["deactivated"] == 1
    reloaded.close()


def test_create_invalid_namespace_raises() -> None:
    service = IdentityService()
    with pytest.raises(ValueError):
        service.create_did(namespace="ns:evil")


def test_acceptance_did_maref_ns_xxx_registered_resolved_verified() -> None:
    """Acceptance: ``did:maref:ns:xxx`` registers, resolves, verifies."""
    service = IdentityService()
    result = service.create_did(namespace="ns")
    assert result.did.startswith("did:maref:ns:")
    assert result.did.count(":") == 3
    # Registered: resolution returns a DID Document.
    resolved = service.resolve_did(result.did)
    assert resolved["did_document"]["id"] == result.did
    # Verified: the derived AIC passes CRC-16 and maps back to the DID.
    verified = service.verify_aic(result.aic)
    assert verified["valid"] and verified["did"] == result.did
    # Deactivated resolution lifecycle closes the loop.
    service.deactivate_did(result.did)
    assert service.resolve_did(result.did)["resolution_metadata"]["error"] == "deactivated"


# ── HTTP E2E ─────────────────────────────────────────────────────────────


def test_identity_http_lifecycle_e2e() -> None:
    """Full DID lifecycle over a real HTTP server + client."""
    identity = IdentityService()
    server = ThreadedIdentityServer(_build_identity_app("id-server", identity))
    server.start()
    try:
        keypair = Ed25519KeyPair.generate()
        with FederationHTTPClient(server.base_url) as client:
            # create
            created = client.create_identity(
                {
                    "namespace": "ns",
                    "roles": ["worker"],
                    "ed25519_public_key_pem": keypair.public_key_pem,
                    "service_endpoints": [
                        {
                            "id": "placeholder#a2a",
                            "type": "A2AAgentService",
                            "serviceEndpoint": "https://agent.example.com/a2a",
                        }
                    ],
                }
            )
            did = created["did"]
            assert created["aic"]
            assert did.startswith("did:maref:ns:")
            assert created["did_document"]["verificationMethod"][0][
                "publicKeyPem"
            ] == keypair.public_key_pem

            # resolve
            resolved = client.resolve_identity(did)
            assert resolved["resolution_metadata"]["resolved"] is True
            assert resolved["did_document"]["id"] == did

            # verify AIC + DID↔AIC translation
            verified = client.verify_aic(created["aic"])
            assert verified["valid"] and verified["did"] == did
            assert client.identity_did_to_aic(did)["aic"] == created["aic"]
            assert client.identity_aic_to_did(created["aic"])["did"] == did

            # summary + list
            summary = client.fetch_identity_summary()
            assert summary["identities"] == 1
            assert len(client.fetch_identities()) == 1

            # deactivate → resolve reports deactivated
            assert client.deactivate_identity(did)["success"] is True
            deactivated = client.resolve_identity(did)
            assert deactivated["resolution_metadata"]["error"] == "deactivated"
            assert client.verify_aic(created["aic"])["deactivated"] is True
    finally:
        server.stop()


def test_identity_unconfigured_returns_503() -> None:
    """Without an identity service the endpoints answer 503."""
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    subscriber = FederatedPolicySubscriber(
        local_engine=FederationPolicyEngine(),
        local_org="plain",
    )
    app = create_federation_app(gateway, trust_engine, subscriber, server_id="plain")
    server = ThreadedIdentityServer(app)
    server.start()
    try:
        with FederationHTTPClient(server.base_url) as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.create_identity({"namespace": "ns"})
            with pytest.raises(httpx.HTTPStatusError):
                client.resolve_identity("did:maref:ns:abc")
    finally:
        server.stop()

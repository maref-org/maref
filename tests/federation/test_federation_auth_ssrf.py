"""v0.47 S1/S2 — federated HTTP request signing + SSRF protection.

S1: ``FederationRequestSigner``/``FederationRequestVerifier`` provide Ed25519
    request authentication for the federated HTTP transport.  When a
    verifier is configured on the app every POST under
    ``/api/v1/federation/`` must carry a valid signature, otherwise the
    request is rejected with 401 (fail-closed).  When no verifier is
    configured behaviour is unchanged (backward compatible — existing E2E
    stacks never signed).

S2: ``validate_peer_url`` blocks non-http(s) schemes, loopback, link-local,
    private / reserved addresses unless explicitly whitelisted through
    ``peer_url_policy``.  Applied to ``settlement/reconcile``.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from fastapi.testclient import TestClient

from maref.federation.federation_http import create_federation_app
from maref.federation.gateway import FederationGateway
from maref.federation.metering import TaskMeteringEngine
from maref.federation.policy import FederationPolicyEngine
from maref.federation.policy_subscriber import FederatedPolicySubscriber
from maref.federation.settlement import FederatedSettlement
from maref.federation.trust import FederatedTrustEngine, PeerTrustReport
from maref.recursive.trust_engine_v2 import TrustEngineV2
from maref.signing.signing_key import ReportSigningKey

HEALTH_PATH = "/api/v1/federation/health"
TRUST_REPORT_PATH = "/api/v1/federation/trust/report"
RECONCILE_PATH = "/api/v1/federation/settlement/reconcile"

_AUTH_HEADER = "X-MAREF-Fed-Auth"
_BODY_HASH_HEADER = "X-MAREF-Fed-Body-Hash"


# ── Helpers ───────────────────────────────────────────────────────────────


def _build_base_components() -> tuple[FederationGateway, FederatedTrustEngine, FederatedPolicySubscriber]:
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    subscriber = FederatedPolicySubscriber(
        local_engine=FederationPolicyEngine(), local_org="org-alpha"
    )
    return gateway, trust_engine, subscriber


def _build_app(**kwargs: Any) -> TestClient:
    """Build a TestClient-wrapped federation app with optional hardening config."""
    gateway, trust_engine, subscriber = _build_base_components()
    app = create_federation_app(
        gateway,
        trust_engine,
        subscriber,
        server_id="org-alpha",
        **kwargs,
    )
    return TestClient(app)


def _build_reconcile_client(**kwargs: Any) -> TestClient:
    """Like :func:`_build_app` but with a settlement engine configured."""
    gateway, trust_engine, subscriber = _build_base_components()
    settlement = FederatedSettlement(metering=TaskMeteringEngine())
    app = create_federation_app(
        gateway,
        trust_engine,
        subscriber,
        server_id="org-alpha",
        settlement=settlement,
        **kwargs,
    )
    return TestClient(app)


def _body_hash(body_bytes: bytes) -> str:
    return hashlib.sha256(body_bytes).hexdigest()


def _signed_headers(
    key: ReportSigningKey,
    key_id: str,
    method: str,
    path: str,
    body_bytes: bytes,
    timestamp: int | None = None,
) -> dict[str, str]:
    """Build signing headers using the public ReportSigningKey API."""
    ts = int(time.time()) if timestamp is None else timestamp
    body_hash = _body_hash(body_bytes)
    payload = f"{ts}\n{method}\n{path}\n{body_hash}".encode("utf-8")
    signature = key.sign_report(payload)
    return {
        _AUTH_HEADER: f"{key_id}:{ts}:{signature}",
        _BODY_HASH_HEADER: body_hash,
    }


def _valid_report() -> dict[str, Any]:
    return PeerTrustReport(
        agent_id="did:maref:federated:e2e-abc",
        source_server="org-remote",
        trust_score=88.5,
        tier="AA",
        confidence=0.9,
    ).to_dict()


def _report_body_bytes() -> bytes:
    return json.dumps(_valid_report()).encode("utf-8")


def _json_headers(headers: dict[str, str]) -> dict[str, str]:
    return {"Content-Type": "application/json", **headers}


# ── S1: request signing ───────────────────────────────────────────────────


def test_signed_request_accepted_when_verifier_configured() -> None:
    key = ReportSigningKey.generate()
    client = _build_app(request_verifier={"org-alpha": key.public_key_pem})
    body_bytes = _report_body_bytes()
    headers = _signed_headers(
        key, "org-alpha", "POST", TRUST_REPORT_PATH, body_bytes
    )
    response = client.post(TRUST_REPORT_PATH, content=body_bytes, headers=_json_headers(headers))
    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_unsigned_request_rejected_when_verifier_configured() -> None:
    key = ReportSigningKey.generate()
    client = _build_app(request_verifier={"org-alpha": key.public_key_pem})
    response = client.post(TRUST_REPORT_PATH, json=_valid_report())
    assert response.status_code == 401


def test_wrong_signature_rejected() -> None:
    server_key = ReportSigningKey.generate()
    attacker_key = ReportSigningKey.generate()
    client = _build_app(request_verifier={"org-alpha": server_key.public_key_pem})
    body_bytes = _report_body_bytes()
    headers = _signed_headers(
        attacker_key, "org-alpha", "POST", TRUST_REPORT_PATH, body_bytes
    )
    response = client.post(TRUST_REPORT_PATH, content=body_bytes, headers=_json_headers(headers))
    assert response.status_code == 401


def test_tampered_body_rejected() -> None:
    """Signature over the body-hash must not survive body modification."""
    key = ReportSigningKey.generate()
    client = _build_app(request_verifier={"org-alpha": key.public_key_pem})
    body_bytes = _report_body_bytes()
    headers = _signed_headers(
        key, "org-alpha", "POST", TRUST_REPORT_PATH, body_bytes
    )
    tampered = body_bytes.replace(b"88.5", b"99.0")
    response = client.post(TRUST_REPORT_PATH, content=tampered, headers=_json_headers(headers))
    assert response.status_code == 401


def test_expired_timestamp_rejected() -> None:
    """A signature with an old timestamp (beyond max skew) is rejected."""
    key = ReportSigningKey.generate()
    client = _build_app(request_verifier={"org-alpha": key.public_key_pem})
    body_bytes = _report_body_bytes()
    old = int(time.time()) - 100_000
    headers = _signed_headers(
        key, "org-alpha", "POST", TRUST_REPORT_PATH, body_bytes, timestamp=old
    )
    response = client.post(TRUST_REPORT_PATH, content=body_bytes, headers=_json_headers(headers))
    assert response.status_code == 401


def test_health_stays_public_with_verifier() -> None:
    key = ReportSigningKey.generate()
    client = _build_app(request_verifier={"org-alpha": key.public_key_pem})
    response = client.get(HEALTH_PATH)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unconfigured_verifier_backward_compatible() -> None:
    """Without a verifier, unsigned requests keep working (existing E2E)."""
    client = _build_app()
    response = client.post(TRUST_REPORT_PATH, json=_valid_report())
    assert response.status_code == 200
    assert response.json()["accepted"] is True


# ── S2: SSRF protection on settlement/reconcile ───────────────────────────


def test_ssrf_rejects_loopback_peer() -> None:
    client = _build_reconcile_client(peer_url_policy={"allowed_hosts": set()})
    response = client.post(
        RECONCILE_PATH,
        json={"peer_url": "http://127.0.0.1:9100/api", "arbitrate": False, "timeout": 1.0},
    )
    assert response.status_code == 400


def test_ssrf_rejects_link_local_peer() -> None:
    client = _build_reconcile_client(peer_url_policy={"allowed_hosts": set()})
    response = client.post(
        RECONCILE_PATH,
        json={"peer_url": "http://169.254.169.254/latest/meta-data", "arbitrate": False, "timeout": 1.0},
    )
    assert response.status_code == 400


def test_ssrf_rejects_non_http_scheme() -> None:
    client = _build_reconcile_client(peer_url_policy={"allowed_hosts": set()})
    response = client.post(
        RECONCILE_PATH,
        json={"peer_url": "file:///etc/passwd", "arbitrate": False, "timeout": 1.0},
    )
    assert response.status_code == 400


def test_ssrf_rejects_private_range_peer() -> None:
    client = _build_reconcile_client(peer_url_policy={"allowed_hosts": set()})
    response = client.post(
        RECONCILE_PATH,
        json={"peer_url": "http://10.0.0.5:9100/ledger", "arbitrate": False, "timeout": 1.0},
    )
    assert response.status_code == 400


def test_ssrf_allows_whitelisted_host() -> None:
    """A host explicitly whitelisted is allowed past the SSRF gate."""
    client = _build_reconcile_client(
        peer_url_policy={"allowed_hosts": {"10.0.0.5"}},
    )
    response = client.post(
        RECONCILE_PATH,
        json={"peer_url": "http://10.0.0.5:9100/ledger", "arbitrate": False, "timeout": 1.0},
    )
    # Reaches the httpx fetch stage (502 = connection failure, not 400 SSRF).
    assert response.status_code == 502


def test_ssrf_unconfigured_backward_compatible() -> None:
    """Without a peer_url_policy the reconcile endpoint behaves as before."""
    client = _build_reconcile_client()
    response = client.post(
        RECONCILE_PATH,
        json={"peer_url": "http://127.0.0.1:1/ledger", "arbitrate": False, "timeout": 1.0},
    )
    assert response.status_code == 502


# ── S1 client auto-signing + auth_failed audit ─────────────────────────────


def test_http_client_auto_signs_requests() -> None:
    """FederationHTTPClient's signing hook attaches headers that a
    verifier-configured server accepts."""
    import asyncio

    import httpx

    from maref.federation.federation_auth import (
        FederationRequestSigner,
        FederationRequestVerifier,
    )
    from maref.federation.federation_http import FederationHTTPClient

    client_key = ReportSigningKey.generate()
    gateway, trust_engine, subscriber = _build_base_components()
    app = create_federation_app(
        gateway,
        trust_engine,
        subscriber,
        server_id="org-alpha",
        request_verifier={"org-beta": client_key.public_key_pem},
    )
    transport = httpx.ASGITransport(app=app)
    signer = FederationRequestSigner(key=client_key, key_id="org-beta")
    fed_client = FederationHTTPClient("http://testserver", signer=signer, timeout=5.0)

    # 1) The signing hook attaches X-MAREF-Fed-* headers to a POST.
    request = httpx.Request(
        "POST", "http://testserver/api/v1/federation/trust/report",
        json=_valid_report(),
    )
    fed_client._sign_request(request)
    assert "X-MAREF-Fed-Auth" in request.headers
    assert "X-MAREF-Fed-Body-Hash" in request.headers

    # 2) Those headers pass the server's verifier.
    verifier = FederationRequestVerifier(
        {"org-beta": client_key.public_key_pem}
    )
    ok = verifier.verify(
        method="POST",
        path="/api/v1/federation/trust/report",
        body_bytes=request.content,
        auth_header=request.headers.get("X-MAREF-Fed-Auth"),
        body_hash_header=request.headers.get("X-MAREF-Fed-Body-Hash"),
    )
    assert ok is True

    # 3) End-to-end: signed request is accepted by the configured server.
    async def _run() -> int:
        async_client = httpx.AsyncClient(transport=transport, timeout=5.0)
        signed = httpx.Request(
            "POST", "http://testserver/api/v1/federation/trust/report",
            json=_valid_report(),
        )
        fed_client._sign_request(signed)
        response = await async_client.send(signed)
        await async_client.aclose()
        return response.status_code

    assert asyncio.run(_run()) == 200


def test_auth_failed_audit_recorded_on_rejection() -> None:
    """Rejected unsigned requests are recorded in the auth-failed audit log."""
    from maref.federation.federation_http import (
        _AUTH_FAILED_LOG,
        get_auth_failed_log,
    )

    _AUTH_FAILED_LOG.clear()
    key = ReportSigningKey.generate()
    client = _build_app(request_verifier={"org-alpha": key.public_key_pem})
    response = client.post(TRUST_REPORT_PATH, json=_valid_report())
    assert response.status_code == 401

    log = get_auth_failed_log()
    assert len(log) == 1
    entry = log[0]
    assert entry["reason"] == "auth_failed"
    assert entry["path"] == TRUST_REPORT_PATH
    assert entry["method"] == "POST"


def test_auth_failed_audit_captures_key_id() -> None:
    """A malformed/unknown signer key is captured in the audit entry."""
    from maref.federation.federation_http import (
        _AUTH_FAILED_LOG,
        get_auth_failed_log,
    )

    _AUTH_FAILED_LOG.clear()
    server_key = ReportSigningKey.generate()
    client = _build_app(request_verifier={"org-alpha": server_key.public_key_pem})
    body_bytes = _report_body_bytes()
    headers = _signed_headers(
        ReportSigningKey.generate(), "org-unknown", "POST", TRUST_REPORT_PATH, body_bytes
    )
    response = client.post(TRUST_REPORT_PATH, content=body_bytes, headers=_json_headers(headers))
    assert response.status_code == 401

    log = get_auth_failed_log()
    assert len(log) == 1
    assert log[0]["key_id"] == "org-unknown"

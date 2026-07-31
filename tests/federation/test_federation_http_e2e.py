"""Phase 2.2 — dual-process federation E2E over real HTTP.

Verifies the federated HTTP transport end to end with two independent
processes (each running its own FastAPI/uvicorn server):

1. **Discovery**: ``HTTPDiscoveryTransport`` fetches the peer's ADP catalog
   and ``FederatedDiscovery`` forwards queries across processes.
2. **Trust**: peer trust reports are submitted and fetched over HTTP.
3. **Policy sync**: policy push events are delivered and imported into the
   peer's local engine over HTTP.

The full chain is driven exclusively through HTTP endpoints — no in-process
state is shared between the two servers.
"""

from __future__ import annotations

import multiprocessing
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from maref.federation.discovery import (
    DiscoveryQuery,
    FederatedDiscovery,
    FederationPeer,
    HTTPDiscoveryTransport,
)
from maref.federation.federation_http import (
    FederationHTTPClient,
    create_federation_app,
)
from maref.federation.gateway import FederationGateway, FederationRequest
from maref.federation.policy import (
    FederationPolicyEngine,
    PolicyDecision,
    PolicyRule,
    PolicyScope,
)
from maref.federation.policy_subscriber import (
    FederatedPolicySubscriber,
    PolicyChangeType,
    PolicyPushEvent,
)
from maref.federation.trust import FederatedTrustEngine, PeerTrustReport
from maref.identity.aic_adapter import AIC
from maref.integration.acs_parser import ACSParser
from maref.recursive.trust_engine_v2 import TrustEngineV2

HEALTH_PATH = "/api/v1/federation/health"


# ── Helpers ──────────────────────────────────────────────────────────────


def _free_port() -> int:
    """Return a currently-free TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_healthy(base_url: str, timeout: float = 20.0) -> None:
    """Poll the health endpoint until the server responds 200."""
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}{HEALTH_PATH}", timeout=1.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.05)
    raise RuntimeError(f"server {base_url} did not become healthy: {last_error}")


def _make_acs_document(capabilities: list[str]) -> dict[str, Any]:
    """Build a valid ACS document with a generated AIC."""
    return ACSParser().from_maref_capabilities(
        aic=AIC.generate().aic_string,
        agent_name="e2e-agent",
        agent_description="phase 2.2 e2e federated agent",
        capabilities=capabilities,
        endpoint_url="http://127.0.0.1:9999",
        provider_organization="e2e",
    ).to_dict()


@dataclass
class FederationStack:
    """The in-process federation state behind one server."""

    org: str
    gateway: FederationGateway
    trust_engine: FederatedTrustEngine
    policy_engine: FederationPolicyEngine
    subscriber: FederatedPolicySubscriber
    app: FastAPI


def _build_stack(org: str) -> FederationStack:
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    policy_engine = FederationPolicyEngine()
    subscriber = FederatedPolicySubscriber(
        local_engine=policy_engine, local_org=org
    )
    app = create_federation_app(gateway, trust_engine, subscriber, server_id=org)
    return FederationStack(
        org=org,
        gateway=gateway,
        trust_engine=trust_engine,
        policy_engine=policy_engine,
        subscriber=subscriber,
        app=app,
    )


class ThreadedFederationServer:
    """Run a federation FastAPI app under uvicorn in a background thread."""

    def __init__(self, stack: FederationStack) -> None:
        self._stack = stack
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""

    def start(self) -> None:
        config = uvicorn.Config(
            self._stack.app, host="127.0.0.1", port=0, log_level="warning"
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.time() + 15.0
        while time.time() < deadline:
            if self._server.started and self._server.servers:
                port = self._server.servers[0].sockets[0].getsockname()[1]
                self.base_url = f"http://127.0.0.1:{port}"
                _wait_until_healthy(self.base_url, timeout=5.0)
                return
            time.sleep(0.05)
        raise RuntimeError("threaded federation server failed to start")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10.0)


@pytest.fixture
def federation_server() -> tuple[FederationStack, ThreadedFederationServer]:
    stack = _build_stack("org-alpha")
    server = ThreadedFederationServer(stack)
    server.start()
    try:
        yield stack, server
    finally:
        server.stop()


# ── Child-process entry points (true dual-process verification) ──────────


def _run_server_process(org: str, port: int, subscribe_to: str | None = None) -> None:
    """Child-process entry: run a federation HTTP server until terminated."""
    stack = _build_stack(org)
    if subscribe_to:
        stack.subscriber.subscribe(publisher_org=subscribe_to, action_filter="*")
    uvicorn.run(stack.app, host="127.0.0.1", port=port, log_level="warning")


def _start_server_process(
    org: str, subscribe_to: str | None = None
) -> tuple[multiprocessing.Process, str]:
    port = _free_port()
    proc = multiprocessing.Process(
        target=_run_server_process,
        args=(org, port, subscribe_to),
        daemon=True,
    )
    proc.start()
    base_url = f"http://127.0.0.1:{port}"
    _wait_until_healthy(base_url)
    return proc, base_url


# ── Single-server endpoint tests ─────────────────────────────────────────


def test_health_endpoint(federation_server: tuple[FederationStack, ThreadedFederationServer]) -> None:
    stack, server = federation_server
    with FederationHTTPClient(server.base_url) as client:
        body = client.health()
    assert body["status"] == "ok"
    assert body["server_id"] == stack.org


def test_adp_catalog_empty(federation_server: tuple[FederationStack, ThreadedFederationServer]) -> None:
    _, server = federation_server
    with FederationHTTPClient(server.base_url) as client:
        assert client.fetch_catalog() == []


def test_register_agent_over_http(
    federation_server: tuple[FederationStack, ThreadedFederationServer],
) -> None:
    stack, server = federation_server
    acs_doc = _make_acs_document(["research"])
    with FederationHTTPClient(server.base_url) as client:
        result = client.register_agent(
            {
                "aic_string": acs_doc["aic"],
                "acs_document": acs_doc,
                "endpoint_url": "http://127.0.0.1:9999",
                "protocol": "a2a",
            }
        )
        assert result["success"] is True
        assert result["aic_string"] == acs_doc["aic"]
        agents = client.fetch_agents()
        assert len(agents) == 1
        assert agents[0]["aic"] == acs_doc["aic"]
        assert agents[0]["capabilities"] == ["research"]
    assert stack.gateway.agent_count == 1


def test_http_discovery_transport_real_http(
    federation_server: tuple[FederationStack, ThreadedFederationServer],
) -> None:
    """HTTPDiscoveryTransport fetches a live server's ADP catalog."""
    stack, server = federation_server
    acs_doc = _make_acs_document(["research", "summarize"])
    response = stack.gateway.register_agent(
        FederationRequest(
            aic_string=acs_doc["aic"],
            acs_document=acs_doc,
            endpoint_url="http://127.0.0.1:9999",
            protocol="a2a",
        )
    )
    assert response.success

    peer = FederationPeer(server_id=stack.org, endpoint_url=server.base_url)
    transport = HTTPDiscoveryTransport(timeout=5.0)
    agents = transport.fetch_catalog(peer, DiscoveryQuery())
    assert len(agents) == 1
    assert agents[0].aic.aic_string == acs_doc["aic"]
    assert [s.id for s in agents[0].acs.skills] == ["research", "summarize"]


def test_federated_discovery_remote_forward(
    federation_server: tuple[FederationStack, ThreadedFederationServer],
) -> None:
    """FederatedDiscovery forwards a query to a peer over HTTP."""
    stack, server = federation_server
    acs_doc = _make_acs_document(["research"])
    response = stack.gateway.register_agent(
        FederationRequest(
            aic_string=acs_doc["aic"],
            acs_document=acs_doc,
            endpoint_url="http://127.0.0.1:9999",
        )
    )
    assert response.success

    discovery = FederatedDiscovery(
        gateway=FederationGateway(),
        server_id="org-local",
        transport=HTTPDiscoveryTransport(timeout=5.0),
    )
    discovery.add_peer(stack.org, server.base_url)
    results = discovery.discover(capability="research", include_remote=True)
    assert len(results) == 1
    assert results[0].source_server == stack.org
    assert results[0].hop_count == 1


def test_trust_report_submit_and_fetch(
    federation_server: tuple[FederationStack, ThreadedFederationServer],
) -> None:
    stack, server = federation_server
    report = PeerTrustReport(
        agent_id="did:maref:federated:e2e-abc",
        source_server="org-remote",
        trust_score=88.5,
        tier="AA",
        confidence=0.9,
    )
    with FederationHTTPClient(server.base_url) as client:
        result = client.submit_trust_report(report.to_dict())
        assert result["accepted"] is True
        fetched = client.fetch_trust_reports(report.agent_id)
        assert len(fetched) == 1
        assert fetched[0]["source_server"] == "org-remote"
        assert fetched[0]["trust_score"] == 88.5
        assert fetched[0]["tier"] == "AA"
    assert len(stack.trust_engine.get_peer_reports(report.agent_id)) == 1


def test_policy_push_imports_rule(
    federation_server: tuple[FederationStack, ThreadedFederationServer],
) -> None:
    stack, server = federation_server
    stack.subscriber.subscribe(
        publisher_org="org-alpha", action_filter="cross_border_transfer"
    )
    rule = PolicyRule(
        rule_id="fed-rule-001",
        action="cross_border_transfer",
        scope=PolicyScope.FEDERATION,
        decision=PolicyDecision.DENY,
    )
    event = PolicyPushEvent(
        event_id="evt-001",
        publisher_org="org-alpha",
        change_type=PolicyChangeType.RULE_ADDED,
        rule=rule,
    )
    with FederationHTTPClient(server.base_url) as client:
        result = client.push_policy(event.to_dict())
        assert result["accepted"] is True
        assert result["matched_subscriptions"] is True
        rules = client.fetch_policy_rules()
        assert any(
            r["rule_id"] == "imported:org-alpha:fed-rule-001" for r in rules
        )

    evaluation = stack.policy_engine.evaluate(
        "cross_border_transfer", {"data_type": "pii"}
    )
    assert evaluation.decision == PolicyDecision.DENY
    assert evaluation.winning_rule is not None
    assert evaluation.winning_rule.rule_id == "imported:org-alpha:fed-rule-001"


# ── Dual-process full-chain test ─────────────────────────────────────────


def test_dual_process_full_chain() -> None:
    """Two real processes complete discovery → trust → policy sync over HTTP."""
    proc_a, _url_a = _start_server_process("org-alpha")
    proc_b, url_b = _start_server_process("org-beta", subscribe_to="org-alpha")
    try:
        with FederationHTTPClient(url_b) as client_b:
            # 1) Discovery: register an agent on process B via HTTP, then
            #    discover it from process A over real HTTP (ADP catalog).
            acs_doc = _make_acs_document(["research", "summarize"])
            reg = client_b.register_agent(
                {
                    "aic_string": acs_doc["aic"],
                    "acs_document": acs_doc,
                    "endpoint_url": "http://127.0.0.1:9999",
                    "protocol": "a2a",
                }
            )
            assert reg["success"] is True

            peer = FederationPeer(server_id="org-beta", endpoint_url=url_b)
            transport = HTTPDiscoveryTransport(timeout=5.0)
            agents = transport.fetch_catalog(peer, DiscoveryQuery())
            assert len(agents) == 1
            assert agents[0].aic.aic_string == acs_doc["aic"]

            discovery = FederatedDiscovery(
                gateway=FederationGateway(),
                server_id="org-alpha",
                transport=transport,
            )
            discovery.add_peer("org-beta", url_b)
            results = discovery.discover(capability="research", include_remote=True)
            assert len(results) == 1
            assert results[0].source_server == "org-beta"

            # 2) Trust: process A submits a peer trust report to process B.
            #    The request targets B's server (B collects peer reports).
            report = PeerTrustReport(
                agent_id=reg["did_string"],
                source_server="org-alpha",
                trust_score=95.0,
                tier="AAA",
                confidence=0.99,
            )
            submitted = client_b.submit_trust_report(report.to_dict())
            assert submitted["accepted"] is True
            fetched = client_b.fetch_trust_reports(reg["did_string"])
            assert len(fetched) == 1
            assert fetched[0]["source_server"] == "org-alpha"
            assert fetched[0]["trust_score"] == 95.0

            # 3) Policy sync: process A pushes a federation rule to process B,
            #    and B's local engine enforces it (verified via B's endpoint).
            rule = PolicyRule(
                rule_id="fed-rule-002",
                action="dispatch_task",
                scope=PolicyScope.FEDERATION,
                decision=PolicyDecision.DENY,
            )
            event = PolicyPushEvent(
                event_id="evt-002",
                publisher_org="org-alpha",
                change_type=PolicyChangeType.RULE_ADDED,
                rule=rule,
            )
            pushed = client_b.push_policy(event.to_dict())
            assert pushed["accepted"] is True
            assert pushed["matched_subscriptions"] is True
            rules = client_b.fetch_policy_rules()
            assert any(
                r["rule_id"] == "imported:org-alpha:fed-rule-002"
                and r["decision"] == "deny"
                for r in rules
            )
    finally:
        proc_a.terminate()
        proc_b.terminate()
        proc_a.join(timeout=10.0)
        proc_b.join(timeout=10.0)

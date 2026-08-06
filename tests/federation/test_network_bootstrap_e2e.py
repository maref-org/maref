"""Phase 3.1 — cross-server discovery network: bootstrap + heartbeat + distributed catalog.

Covers the three sub-goals of task 3.1:

1. **Bootstrap protocol** — :class:`BootstrapClient` joins a server to a
   federation network through seed nodes (plus DNS-SRV seed parsing).
2. **Node heartbeat + membership** — :class:`MembershipManager` keeps the
   member table alive over HTTP, reusing :class:`FederationHealthMonitor`
   (silence → suspicion; unknown peers are auto-registered).
3. **Distributed catalog** — the ADP catalog endpoint forwards queries to
   its own peers (multi-hop), and :class:`HTTPDiscoveryTransport` flattens
   the response tree into ``(agent, source_server, hop_count)``.

The E2E test boots **three real processes** (seed / org-alpha / org-beta)
and drives bootstrap → heartbeat → membership → cross-server capability
query exclusively through HTTP.
"""

from __future__ import annotations

import multiprocessing
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI

from maref.federation.bootstrap import (
    BootstrapClient,
    BootstrapSeed,
    parse_srv_seeds,
)
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
from maref.federation.health_monitor import FederationHealthMonitor
from maref.federation.membership import HeartbeatMessage, MembershipManager
from maref.federation.policy import FederationPolicyEngine
from maref.federation.policy_subscriber import FederatedPolicySubscriber
from maref.federation.trust import FederatedTrustEngine
from maref.identity.aic_adapter import AIC
from maref.integration.acs_parser import ACSParser
from maref.recursive.trust_engine_v2 import TrustEngineV2

HEALTH_PATH = "/api/v1/federation/health"


# ── Shared helpers ───────────────────────────────────────────────────────


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
    return (
        ACSParser()
        .from_maref_capabilities(
            aic=AIC.generate().aic_string,
            agent_name="e2e-agent",
            agent_description="phase 3.1 federated agent",
            capabilities=capabilities,
            endpoint_url="http://127.0.0.1:9999",
            provider_organization="e2e",
        )
        .to_dict()
    )


@dataclass
class FederationStack:
    """The in-process federation state behind one threaded server."""

    org: str
    gateway: FederationGateway
    app: FastAPI


def _build_stack(org: str) -> FederationStack:
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    subscriber = FederatedPolicySubscriber(local_engine=FederationPolicyEngine(), local_org=org)
    app = create_federation_app(gateway, trust_engine, subscriber, server_id=org)
    return FederationStack(org=org, gateway=gateway, app=app)


def _build_app_with_discovery(
    org: str,
    discovery: FederatedDiscovery | None = None,
    membership: Any | None = None,
) -> FastAPI:
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    subscriber = FederatedPolicySubscriber(local_engine=FederationPolicyEngine(), local_org=org)
    return create_federation_app(
        gateway,
        trust_engine,
        subscriber,
        server_id=org,
        discovery=discovery,
        membership=membership,
    )


class ThreadedFederationServer:
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
                _wait_until_healthy(self.base_url, timeout=5.0)
                return
            time.sleep(0.05)
        raise RuntimeError("threaded federation server failed to start")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10.0)


def _fetch_peers(base_url: str) -> list[dict[str, Any]]:
    body = httpx.get(f"{base_url}/api/v1/federation/network/peers", timeout=5.0).json()
    return body.get("peers", [])


# ── Component tests ──────────────────────────────────────────────────────


def test_parse_srv_seeds() -> None:
    seeds = parse_srv_seeds(
        [
            {"target": "node1.example.com.", "port": 9100, "priority": 10},
            {"target": "node2.example.com", "port": 9200},
            {"target": "", "port": 9999},  # invalid, skipped
            "not-a-dict",  # invalid, skipped
        ]
    )
    assert len(seeds) == 2
    assert seeds[0].server_id == "seed:node1.example.com:9100"
    assert seeds[0].endpoint_url == "http://node1.example.com:9100"
    assert seeds[1].server_id == "seed:node2.example.com:9200"


def test_heartbeat_message_roundtrip() -> None:
    message = HeartbeatMessage(
        server_id="org-alpha",
        endpoint_url="http://127.0.0.1:9100",
        generation=3,
    )
    restored = HeartbeatMessage.from_dict(message.to_dict())
    assert restored == message
    assert restored.generation == 3


def test_membership_silence_suspicion_and_recovery() -> None:
    monitor = FederationHealthMonitor(silence_timeout=0.05)
    membership = MembershipManager(
        server_id="org-alpha",
        endpoint_url="http://127.0.0.1:1",
        health_monitor=monitor,
    )

    # Heartbeat registers the member as active.
    assert (
        membership.receive_heartbeat(
            HeartbeatMessage(server_id="org-beta", endpoint_url="http://127.0.0.1:2")
        )
        is True
    )
    assert membership.member_count == 1
    assert "org-beta" in membership.members_summary()

    # Silence → suspected.
    time.sleep(0.15)
    result = membership.run_check()
    assert result.suspected == 1
    assert membership.members_summary()["org-beta"]["suspected"] is True

    # Recovery heartbeat clears suspicion.
    membership.receive_heartbeat(
        HeartbeatMessage(server_id="org-beta", endpoint_url="http://127.0.0.1:2")
    )
    assert membership.members_summary()["org-beta"]["suspected"] is False


def test_membership_ignores_self_echo() -> None:
    monitor = FederationHealthMonitor()
    membership = MembershipManager(
        server_id="org-alpha",
        endpoint_url="http://127.0.0.1:1",
        health_monitor=monitor,
    )
    assert (
        membership.receive_heartbeat(
            HeartbeatMessage(server_id="org-alpha", endpoint_url="http://127.0.0.1:1")
        )
        is False
    )
    assert membership.member_count == 0


def test_membership_auto_registers_unknown_peer() -> None:
    discovery = FederatedDiscovery(gateway=FederationGateway(), server_id="org-alpha")
    monitor = FederationHealthMonitor()
    membership = MembershipManager(
        server_id="org-alpha",
        endpoint_url="http://127.0.0.1:1",
        health_monitor=monitor,
        discovery=discovery,
    )
    assert discovery.peer_count == 0
    membership.receive_heartbeat(
        HeartbeatMessage(server_id="org-beta", endpoint_url="http://127.0.0.1:2")
    )
    assert discovery.peer_count == 1
    peer = discovery.list_peers()[0]
    assert peer.server_id == "org-beta"
    assert peer.endpoint_url == "http://127.0.0.1:2"


def test_bootstrap_idempotent_and_loop_protected() -> None:
    """Bootstrap via a threaded seed; repeated runs never duplicate peers."""
    # Seed server knows itself + one extra peer (org-friend).
    seed_discovery = FederatedDiscovery(gateway=FederationGateway(), server_id="org-seed")
    seed_discovery.add_peer("org-friend", "http://127.0.0.1:9999")
    seed_app = _build_app_with_discovery("org-seed", discovery=seed_discovery)
    server = ThreadedFederationServer(seed_app)
    server.start()
    try:
        client = FederatedDiscovery(gateway=FederationGateway(), server_id="org-local")
        bootstrap = BootstrapClient(
            client,
            [BootstrapSeed(server_id="org-seed", endpoint_url=server.base_url)],
        )
        first = bootstrap.bootstrap()
        second = bootstrap.bootstrap()

        peer_ids = [p.server_id for p in client.list_peers()]
        assert first[0].server_id == "org-seed"
        assert peer_ids.count("org-seed") == 1
        assert "org-friend" in peer_ids
        assert second == []  # already known → nothing newly added
    finally:
        server.stop()


def test_http_multi_hop_catalog_forwarding() -> None:
    """A→S→B: the catalog endpoint forwards queries to its own peers."""
    # Server B holds the agent.
    stack_b = _build_stack("org-beta")
    acs_doc = _make_acs_document(["research"])
    response = stack_b.gateway.register_agent(
        FederationRequest(
            aic_string=acs_doc["aic"],
            acs_document=acs_doc,
            endpoint_url="http://127.0.0.1:9999",
            protocol="a2a",
        )
    )
    assert response.success
    server_b = ThreadedFederationServer(stack_b.app)
    server_b.start()

    # Server S knows B as a peer (and forwards queries to it).
    discovery_s = FederatedDiscovery(gateway=FederationGateway(), server_id="org-seed")
    discovery_s.add_peer("org-beta", server_b.base_url)
    server_s = ThreadedFederationServer(
        _build_app_with_discovery("org-seed", discovery=discovery_s)
    )
    server_s.start()
    try:
        transport = HTTPDiscoveryTransport(timeout=5.0)
        peer = FederationPeer(server_id="org-seed", endpoint_url=server_s.base_url)
        query = DiscoveryQuery(capability="research", max_depth=2)
        results = transport.fetch_catalog_with_sources(peer, query)

        hits = [r for r in results if r[1] == "org-beta"]
        assert len(hits) == 1
        agent, source, hop = hits[0]
        assert source == "org-beta"
        assert hop == 2  # query went S → B
        assert [s.id for s in agent.acs.skills] == ["research"]
    finally:
        server_s.stop()
        server_b.stop()


# ── Three-process E2E ────────────────────────────────────────────────────


def _build_network_node(
    org: str,
    port: int,
    workdir: Path,
    seed_url: str = "",
) -> FastAPI:
    """Build a Phase 3.1 network node (federation + discovery + membership)."""
    from maref.federation import create_default_federation
    from maref.governance.audit import AuditLogger

    audit_logger = AuditLogger(workdir / org / "audit.jsonl", hmac_key=b"e2e-key")
    platform = create_default_federation(server_id=org, audit_logger=audit_logger)
    platform.discovery = FederatedDiscovery(
        gateway=platform.gateway,
        server_id=org,
        transport=HTTPDiscoveryTransport(timeout=5.0),
    )
    endpoint_url = f"http://127.0.0.1:{port}"
    monitor = FederationHealthMonitor(
        audit_logger=audit_logger,
        silence_timeout=60.0,
    )
    membership = MembershipManager(
        server_id=org,
        endpoint_url=endpoint_url,
        health_monitor=monitor,
        discovery=platform.discovery,
    )
    subscriber = FederatedPolicySubscriber(local_engine=platform.policy_engine, local_org=org)
    app = create_federation_app(
        platform.gateway,
        platform.trust_engine,
        subscriber,
        server_id=org,
        discovery=platform.discovery,
        membership=membership,
    )
    if seed_url:
        BootstrapClient(
            platform.discovery,
            [BootstrapSeed(server_id="org-seed", endpoint_url=seed_url)],
        ).bootstrap()
        membership.announce_to_all()
    return app


def _run_node_process(
    org: str,
    port: int,
    workdir: Path,
    seed_url: str = "",
) -> None:
    """Child-process entry: a Phase 3.1 network node (bootstrap + heartbeat)."""
    app = _build_network_node(org, port, workdir, seed_url=seed_url)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _start_node_process(
    org: str,
    workdir: Path,
    seed_url: str = "",
) -> tuple[multiprocessing.Process, str]:
    port = _free_port()
    proc = multiprocessing.Process(
        target=_run_node_process,
        args=(org, port, workdir, seed_url),
        daemon=True,
    )
    proc.start()
    base_url = f"http://127.0.0.1:{port}"
    _wait_until_healthy(base_url)
    return proc, base_url


def test_three_process_bootstrap_heartbeat_discovery(tmp_path: Path) -> None:
    """Seed + 2 servers: bootstrap, heartbeat membership, cross-server discovery."""
    # 1) Seed first (empty network).
    seed_proc, seed_url = _start_node_process("org-seed", tmp_path)

    # 2) org-alpha joins via the seed → learns the seed.
    alpha_proc, alpha_url = _start_node_process("org-alpha", tmp_path, seed_url=seed_url)

    # 3) org-beta joins via the seed → learns seed + alpha.
    beta_proc, beta_url = _start_node_process("org-beta", tmp_path, seed_url=seed_url)
    try:
        # 4) Register an agent on org-beta over HTTP.
        with FederationHTTPClient(beta_url) as client_b:
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

        # 5) Bootstrap outcome: the seed's peer table now holds both servers
        #    (their startup heartbeats auto-registered them).
        seed_peers = _fetch_peers(seed_url)
        assert {p["server_id"] for p in seed_peers} == {"org-alpha", "org-beta"}

        # 6) Membership: seed's member table contains both servers.
        body = httpx.get(f"{seed_url}/api/v1/federation/network/members", timeout=5.0).json()
        assert set(body["members"].keys()) == {"org-alpha", "org-beta"}

        # 7) Multi-hop distributed catalog: query the seed directly and find
        #    org-beta's agent two hops away (caller → seed → beta).
        transport = HTTPDiscoveryTransport(timeout=5.0)
        peer = FederationPeer(server_id="org-seed", endpoint_url=seed_url)
        results = transport.fetch_catalog_with_sources(
            peer, DiscoveryQuery(capability="research", max_depth=3)
        )
        hits = [r for r in results if r[1] == "org-beta"]
        assert len(hits) >= 1
        # 同一 agent 可能经多条路径返回（seed→beta 直达 / seed→alpha→beta）；
        # 最短路径必须是 2 跳（caller → seed → beta）。
        shortest = min(hits, key=lambda r: r[2])
        assert shortest[2] == 2
        assert shortest[0].aic.aic_string == acs_doc["aic"]

        # 8) org-alpha's discovery peer table includes the seed (bootstrap)
        #    and org-beta (auto-registered when org-beta announced its
        #    heartbeat) — cross-server reachability over real HTTP.
        alpha_peers = _fetch_peers(alpha_url)
        peer_ids = {p["server_id"] for p in alpha_peers}
        assert "org-beta" in peer_ids
        assert "org-seed" in peer_ids
    finally:
        seed_proc.terminate()
        alpha_proc.terminate()
        beta_proc.terminate()
        seed_proc.join(timeout=10.0)
        alpha_proc.join(timeout=10.0)
        beta_proc.join(timeout=10.0)

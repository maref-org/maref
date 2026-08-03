"""Federated HTTP transport — real-network federation for discovery, trust, and policy sync.

Provides the server and client halves of MAREF's cross-process federation
transport, so multiple independent processes can interoperate over real
HTTP (replacing in-process simulation):

Server (FastAPI app via :func:`create_federation_app`):
    - ``GET /.well-known/adp/catalog``  — ADP v2.00 catalog (consumed by
      :class:`~maref.federation.discovery.HTTPDiscoveryTransport`). Since
      Phase 3.1 the endpoint forwards the query to its own peers when
      ``visited`` / ``maxDepth`` are supplied (distributed catalog).
    - ``POST /api/v1/federation/gateway/register`` — register an agent
      from a remote process.
    - ``GET /api/v1/federation/gateway/agents`` — list local agents.
    - ``POST /api/v1/federation/policy/push`` — receive a policy push
      event (published by a remote process).
    - ``POST /api/v1/federation/trust/report`` — receive a peer trust report.
    - ``GET /api/v1/federation/trust/report/{agent_id}`` — list peer trust
      reports for an agent.
    - ``GET /api/v1/federation/health`` — liveness probe.
    - ``GET /api/v1/federation/network/peers`` — known peers (bootstrap).
    - ``POST /api/v1/federation/network/heartbeat`` — node heartbeat.
    - ``GET /api/v1/federation/network/members`` — membership table.
    - ``GET /api/v1/federation/settlement/summary`` — settlement summary.
    - ``GET /api/v1/federation/settlement/root`` — settlement Merkle root.
    - ``GET /api/v1/federation/settlement/ledger`` — ledger snapshot.
    - ``POST /api/v1/federation/settlement/reconcile`` — reconcile against a peer.

Client (:class:`FederationHTTPClient`, httpx):
    - mirror methods for each endpoint above.

The end-to-end flow (2+ processes over HTTP):
    bootstrap → heartbeat → discovery → trust → policy sync → settlement
    reconciliation.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Query

from maref.eivl.federated_merkle import FederatedMerkleAggregator
from maref.federation.bootstrap import PEERS_ENDPOINT_PATH
from maref.federation.gateway import FederatedAgent, FederationRequest
from maref.federation.identity_service import IdentityService
from maref.federation.membership import (
    HEARTBEAT_ENDPOINT_PATH,
    HeartbeatMessage,
)
from maref.federation.policy import PolicyDecision, PolicyRule, PolicyScope
from maref.federation.policy_subscriber import (
    FederatedPolicySubscriber,
    PolicyChangeType,
    PolicyPushEvent,
)
from maref.federation.settlement_reconciler import SettlementReconciler
from maref.federation.trust import FederatedTrustEngine, PeerTrustReport
from maref.governance.verifiable_governance_credential import (
    GovernanceCredentialStore,
    VerifiableGovernanceCredential,
)
from maref.signing.signing_key import ReportSigningKey

_ADP_CATALOG_PATH = "/.well-known/adp/catalog"
_NETWORK_MEMBERS_PATH = "/api/v1/federation/network/members"
_SETTLEMENT_LEDGER_PATH = "/api/v1/federation/settlement/ledger"


# ── Serialization helpers ────────────────────────────────────────────────


def agent_to_catalog_dict(agent: FederatedAgent) -> dict[str, Any]:
    """Serialize a :class:`FederatedAgent` to ADP catalog JSON."""
    return {
        "aic": agent.aic.aic_string,
        "did": agent.did.did_string,
        "name": agent.acs.name,
        "description": agent.acs.description,
        "capabilities": [s.id for s in agent.acs.skills],
        "endpoint": agent.endpoint_url,
        "protocol": agent.protocol,
        "registered_at": agent.registered_at,
    }


def _rule_from_dict(data: dict[str, Any]) -> PolicyRule:
    return PolicyRule(
        rule_id=data["rule_id"],
        action=data["action"],
        scope=PolicyScope(data["scope"]),
        decision=PolicyDecision(data["decision"]),
        priority=data.get("priority", 0),
        conditions=dict(data.get("conditions", {})),
        description=data.get("description", ""),
        created_at=data.get("created_at", 0.0),
    )


def _push_event_from_dict(data: dict[str, Any]) -> PolicyPushEvent:
    rule = _rule_from_dict(data["rule"]) if data.get("rule") else None
    prev = _rule_from_dict(data["previous_rule"]) if data.get("previous_rule") else None
    return PolicyPushEvent(
        event_id=data["event_id"],
        publisher_org=data["publisher_org"],
        change_type=PolicyChangeType(data["change_type"]),
        rule=rule,
        previous_rule=prev,
        timestamp=data.get("timestamp", 0.0),
        signature=data.get("signature", ""),
    )


def _report_from_dict(data: dict[str, Any]) -> PeerTrustReport:
    return PeerTrustReport(
        agent_id=data["agent_id"],
        source_server=data["source_server"],
        trust_score=data["trust_score"],
        tier=data.get("tier", "B"),
        timestamp=data.get("timestamp", 0.0),
        confidence=data.get("confidence", 1.0),
    )


# ── Server ───────────────────────────────────────────────────────────────


def create_federation_app(
    gateway: Any,
    trust_engine: FederatedTrustEngine,
    policy_subscriber: FederatedPolicySubscriber,
    server_id: str = "maref-federation",
    discovery: Any | None = None,
    membership: Any | None = None,
    settlement: Any | None = None,
    identity_service: IdentityService | None = None,
    jurisdiction_router: Any | None = None,
    governance_credentials: GovernanceCredentialStore | None = None,
    credential_signing_key: ReportSigningKey | None = None,
    merkle_aggregator: FederatedMerkleAggregator | None = None,
) -> FastAPI:
    """Build a FastAPI app exposing the federated HTTP endpoints.

    Args:
        gateway: A :class:`~maref.federation.gateway.FederationGateway`.
        trust_engine: A :class:`~maref.federation.trust.FederatedTrustEngine`.
        policy_subscriber: A :class:`FederatedPolicySubscriber`.
        server_id: Identifier of this federation server.
        discovery: Optional :class:`~maref.federation.discovery.FederatedDiscovery`
            — enables multi-hop ADP catalog forwarding and the peer-list
            (bootstrap) endpoint.
        membership: Optional :class:`~maref.federation.membership.MembershipManager`
            — enables the heartbeat + membership-table endpoints.
        settlement: Optional :class:`~maref.federation.settlement.FederatedSettlement`
            — enables the settlement Merkle-root, ledger and reconciliation
            endpoints (Phase 3.2).
        identity_service: Optional :class:`~maref.federation.identity_service.IdentityService`
            — enables the DID / AIC identity endpoints (Phase 3.4).
        jurisdiction_router: Optional :class:`~maref.federation.jurisdiction_router.JurisdictionPolicyRouter`
            — enables the regulatory compliance endpoints (Phase 3.5).

    Returns:
        A configured :class:`fastapi.FastAPI` application.
    """
    app = FastAPI(title=f"MAREF Federation {server_id}", version="0.1.0")
    router = APIRouter()

    @router.get("/api/v1/federation/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "server_id": server_id}

    def _filter_agents(
        capability: str | None,
        aic_prefix: str | None,
        protocol: str | None,
    ) -> list[FederatedAgent]:
        """Filter the local gateway's agents by the ADP query filters."""
        agents = gateway.list_agents()
        if protocol is not None:
            agents = [a for a in agents if a.protocol == protocol]
        if aic_prefix is not None:
            agents = [a for a in agents if a.aic.aic_string.startswith(aic_prefix)]
        if capability is not None:
            agents = [a for a in agents if any(s.id == capability for s in a.acs.skills)]
        return agents

    @router.get(_ADP_CATALOG_PATH)
    def adp_catalog(
        capability: str | None = None,
        aic_prefix: str | None = Query(default=None, alias="aicPrefix"),
        protocol: str | None = None,
        max_results: int = Query(default=50, alias="maxResults"),
        visited: str | None = None,
        max_depth: int = Query(default=1, alias="maxDepth"),
        base_hop: int = Query(default=1, alias="_base_hop"),
    ) -> dict[str, Any]:
        """ADP v2.00 catalog endpoint consumed by HTTPDiscoveryTransport.

        When ``visited`` / ``maxDepth`` are supplied, the query is
        forwarded to this server's peers (multi-hop distributed catalog,
        Phase 3.1): each response node carries ``server_id``, ``_hop``
        (hops from the original caller), local ``agents``, and nested
        ``forwarded`` children.
        """
        visited_set = set(visited.split(",")) if visited else set()
        visited_set.add(server_id)

        local_agents = [
            agent_to_catalog_dict(a) for a in _filter_agents(capability, aic_prefix, protocol)
        ]

        forwarded: list[dict[str, Any]] = []
        if max_depth > 1 and discovery is not None:
            for peer in discovery.list_peers():
                if peer.server_id in visited_set or not peer.healthy:
                    continue
                params: dict[str, Any] = {
                    "visited": ",".join(sorted(visited_set)),
                    "maxDepth": max_depth - 1,
                    "_base_hop": base_hop + 1,
                    "maxResults": max_results,
                }
                if capability is not None:
                    params["capability"] = capability
                if aic_prefix is not None:
                    params["aicPrefix"] = aic_prefix
                if protocol is not None:
                    params["protocol"] = protocol
                try:
                    response = httpx.get(
                        f"{peer.endpoint_url.rstrip('/')}{_ADP_CATALOG_PATH}",
                        params=params,
                        timeout=5.0,
                    )
                    response.raise_for_status()
                    child = response.json()
                except (httpx.HTTPError, ValueError):
                    continue
                if not isinstance(child, dict):
                    continue
                peer.last_contact = time.time()
                peer.healthy = True
                forwarded.append(
                    {
                        "server_id": peer.server_id,
                        "_hop": base_hop + 1,
                        "agents": child.get("agents", []),
                        "forwarded": child.get("forwarded", []),
                    }
                )

        return {
            "server_id": server_id,
            "_hop": base_hop,
            "agents": local_agents,
            "forwarded": forwarded,
        }

    @router.get(PEERS_ENDPOINT_PATH)
    def network_peers() -> dict[str, Any]:
        """List the peers this server knows (consumed by BootstrapClient)."""
        if discovery is None:
            return {"server_id": server_id, "peers": []}
        return {
            "server_id": server_id,
            "peers": [p.to_dict() for p in discovery.list_peers()],
        }

    @router.post(HEARTBEAT_ENDPOINT_PATH)
    def network_heartbeat(body: dict[str, Any]) -> dict[str, Any]:
        """Receive a node heartbeat (liveness + membership auto-registration)."""
        if membership is None:
            return {
                "accepted": True,
                "server_id": server_id,
                "member_count": 0,
            }
        try:
            message = HeartbeatMessage.from_dict(body)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid heartbeat: {exc}") from exc
        accepted = membership.receive_heartbeat(message)
        return {
            "accepted": accepted,
            "server_id": server_id,
            "member_count": membership.member_count,
        }

    @router.get(_NETWORK_MEMBERS_PATH)
    def network_members() -> dict[str, Any]:
        """List the tracked member table (heartbeat-tracked servers)."""
        if membership is None:
            return {"server_id": server_id, "members": {}}
        return {
            "server_id": server_id,
            "members": membership.members_summary(),
        }

    # ── Settlement reconciliation (Phase 3.2) ──────────────────────

    @router.get("/api/v1/federation/settlement/summary")
    def settlement_summary_endpoint() -> dict[str, Any]:
        """Return the local settlement engine summary."""
        if settlement is None:
            return {"server_id": server_id, "settlement": None}
        return {"server_id": server_id, "settlement": settlement.settlement_summary()}

    @router.get("/api/v1/federation/settlement/root")
    def settlement_root() -> dict[str, Any]:
        """Return the local settlement Merkle root (reconciliation digest)."""
        if settlement is None:
            return {"server_id": server_id, "root_hash": None, "tree_size": 0}
        return {"server_id": server_id, **settlement.compute_settlement_root()}

    @router.get(_SETTLEMENT_LEDGER_PATH)
    def settlement_ledger() -> dict[str, Any]:
        """Export the local ledger snapshot for cross-server reconciliation."""
        if settlement is None:
            return {
                "server_id": server_id,
                "root_hash": None,
                "tree_size": 0,
                "entries": [],
            }
        return {"server_id": server_id, **settlement.ledger_snapshot()}

    @router.post("/api/v1/federation/settlement/reconcile")
    def settlement_reconcile(body: dict[str, Any]) -> dict[str, Any]:
        """Pull a peer's ledger and reconcile against the local ledger.

        Body: ``{"peer_url": str, "arbitrate": bool}``.  When
        ``arbitrate`` is true and the comparison finds conflicts, the
        discrepancies are arbitrated against the authoritative metering
        source.
        """
        if settlement is None:
            raise HTTPException(status_code=503, detail="settlement not configured")
        peer_url = body.get("peer_url")
        if not peer_url:
            raise HTTPException(status_code=400, detail="peer_url is required")
        timeout = body.get("timeout", 10.0)
        try:
            with httpx.Client(base_url=str(peer_url).rstrip("/"), timeout=timeout) as client:
                peer = client.get(_SETTLEMENT_LEDGER_PATH).json()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"failed to fetch peer ledger: {exc}"
            ) from exc

        own = {"server_id": server_id, **settlement.ledger_snapshot()}
        reconciler = SettlementReconciler()
        report = reconciler.reconcile(own, peer)
        if body.get("arbitrate") and not report.is_consistent:
            reconciler.arbitrate(
                report,
                {"server_id": server_id, **settlement.authoritative_snapshot()},
            )
        return report.to_dict()

    # ── Identity service (Phase 3.4) ────────────────────────────────

    def _identity() -> IdentityService:
        if identity_service is None:
            raise HTTPException(status_code=503, detail="identity service not configured")
        return identity_service

    @router.post("/api/v1/federation/identity/create")
    def identity_create(body: dict[str, Any]) -> dict[str, Any]:
        """Create a ``did:maref:`` identity with a derived AIC."""
        try:
            result = _identity().create_did(
                namespace=body.get("namespace", "default"),
                roles=body.get("roles"),
                ed25519_public_key_pem=body.get("ed25519_public_key_pem", ""),
                service_endpoints=body.get("service_endpoints"),
                aic=body.get("aic"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.to_dict()

    @router.get("/api/v1/federation/identity/resolve/{did}")
    def identity_resolve(did: str) -> dict[str, Any]:
        """Resolve a DID to a W3C DID Document (DID Resolution result)."""
        return _identity().resolve_did(did)

    @router.post("/api/v1/federation/identity/deactivate")
    def identity_deactivate(body: dict[str, Any]) -> dict[str, Any]:
        """Soft-deactivate a DID (resolution then reports ``deactivated``)."""
        did = body.get("did")
        if not did:
            raise HTTPException(status_code=400, detail="did is required")
        try:
            return _identity().deactivate_did(did)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/v1/federation/identity/aic/verify/{aic_string}")
    def identity_verify_aic(aic_string: str) -> dict[str, Any]:
        """Verify an AIC string (CRC-16 checksum) and its DID binding."""
        return _identity().verify_aic(aic_string)

    @router.get("/api/v1/federation/identity/did/{did}/aic")
    def identity_did_to_aic(did: str) -> dict[str, Any]:
        """Translate a DID to its bound AIC string."""
        try:
            return {"did": did, "aic": _identity().did_to_aic(did)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/v1/federation/identity/aic/{aic_string}/did")
    def identity_aic_to_did(aic_string: str) -> dict[str, Any]:
        """Translate an AIC string to its bound DID."""
        try:
            return {"aic": aic_string, "did": _identity().aic_to_did(aic_string)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/v1/federation/identity/list")
    def identity_list() -> dict[str, Any]:
        """List all registered identities with their status."""
        return {
            "server_id": server_id,
            "identities": _identity().list_identities(),
        }

    @router.get("/api/v1/federation/identity/summary")
    def identity_summary() -> dict[str, Any]:
        """Identity service operational summary."""
        return {"server_id": server_id, **_identity().summary()}

    # ── Regulatory compliance (Phase 3.5) ────────────────────────────

    def _jurisdiction_router() -> Any:
        if jurisdiction_router is None:
            raise HTTPException(status_code=503, detail="compliance service not configured")
        return jurisdiction_router

    @router.post("/api/v1/federation/compliance/evaluate")
    def compliance_evaluate(body: dict[str, Any]) -> dict[str, Any]:
        """Evaluate an action across all registered regulatory jurisdictions."""
        trigram = body.get("trigram")
        action = body.get("action")
        if not trigram or not action:
            raise HTTPException(status_code=400, detail="trigram and action are required")
        result = _jurisdiction_router().route_action(
            trigram=trigram,
            action=action,
            context=body.get("context"),
        )
        return result.to_dict()

    @router.get("/api/v1/federation/compliance/report")
    def compliance_report() -> dict[str, Any]:
        """Generate the cross-jurisdiction compliance report (audit trail)."""
        return _jurisdiction_router().compliance_report()

    @router.get("/api/v1/federation/compliance/decisions")
    def compliance_decisions() -> dict[str, Any]:
        """Return the raw decision audit trail."""
        return {
            "server_id": server_id,
            "decisions": _jurisdiction_router().decision_log(),
        }

    @router.get("/api/v1/federation/compliance/summary")
    def compliance_summary() -> dict[str, Any]:
        """Return the rule-library summary for all jurisdictions."""
        return {"server_id": server_id, **_jurisdiction_router().router_summary()}

    @router.post("/api/v1/federation/gateway/register")
    def register_agent(body: dict[str, Any]) -> dict[str, Any]:
        """Register an agent from a remote process."""
        try:
            request = FederationRequest(
                aic_string=body["aic_string"],
                acs_document=body.get("acs_document", {}),
                endpoint_url=body.get("endpoint_url", ""),
                protocol=body.get("protocol", "aip"),
                did_namespace=body.get("did_namespace", "federated"),
                acs_signature=body.get("acs_signature", ""),
                acs_public_key_pem=body.get("acs_public_key_pem", ""),
            )
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc}") from exc
        response = gateway.register_agent(request)
        if not response.success:
            raise HTTPException(status_code=400, detail=response.error)
        return {
            "success": True,
            "did_string": response.did_string,
            "aic_string": response.aic_string,
        }

    @router.get("/api/v1/federation/gateway/agents")
    def list_agents() -> dict[str, Any]:
        return {
            "server_id": server_id,
            "agents": [agent_to_catalog_dict(a) for a in gateway.list_agents()],
        }

    @router.post("/api/v1/federation/policy/push")
    def policy_push(body: dict[str, Any]) -> dict[str, Any]:
        """Receive a policy push event from a remote process."""
        try:
            event = _push_event_from_dict(body)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid event: {exc}") from exc
        matched = policy_subscriber.process_push_event(event)
        return {
            "accepted": True,
            "matched_subscriptions": matched,
            "server_id": server_id,
        }

    @router.get("/api/v1/federation/policy/rules")
    def list_policy_rules() -> dict[str, Any]:
        """List locally enforced policy rules (observability for sync verification)."""
        return {
            "server_id": server_id,
            "rules": [r.to_dict() for r in policy_subscriber.local_engine.list_rules()],
        }

    @router.post("/api/v1/federation/trust/report")
    def trust_report(body: dict[str, Any]) -> dict[str, Any]:
        """Receive a peer trust report from a remote process."""
        try:
            report = _report_from_dict(body)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid report: {exc}") from exc
        trust_engine.submit_peer_report(report)
        return {"accepted": True, "agent_id": report.agent_id}

    @router.get("/api/v1/federation/trust/report/{agent_id}")
    def get_trust_reports(agent_id: str) -> dict[str, Any]:
        reports = trust_engine.get_peer_reports(agent_id)
        return {
            "agent_id": agent_id,
            "reports": [r.to_dict() for r in reports],
        }

    # ── Verifiable Governance Credential (Phase: Agent-Internet) ────────

    def _governance_credentials() -> GovernanceCredentialStore:
        if governance_credentials is None:
            raise HTTPException(status_code=503, detail="governance credential store not configured")
        return governance_credentials

    def _credential_signing_key() -> ReportSigningKey:
        if credential_signing_key is None:
            raise HTTPException(status_code=503, detail="credential signing key not configured")
        return credential_signing_key

    @router.post("/api/v1/federation/governance/credential/issue")
    def governance_credential_issue(body: dict[str, Any]) -> dict[str, Any]:
        """签发可验证治理凭证。

        body: {subject_did, issuer_did, scope[], ttl_seconds?, org_id?+root_hash?+tree_size? 或 merkle_proof?}
        """
        subject_did = body.get("subject_did")
        issuer_did = body.get("issuer_did")
        scope = body.get("scope")
        if scope is None:
            scope = ["audit"]
        if not isinstance(scope, list) or not scope or not all(
            isinstance(s, str) for s in scope
        ):
            raise HTTPException(
                status_code=400, detail="scope must be a non-empty list of strings"
            )
        if not subject_did or not issuer_did:
            raise HTTPException(status_code=400, detail="subject_did and issuer_did are required")
        merkle_proof = body.get("merkle_proof") or {}
        if not merkle_proof and body.get("org_id") and body.get("root_hash"):
            if merkle_aggregator is None:
                raise HTTPException(status_code=503, detail="merkle aggregator not configured")
            org_id = body["org_id"]
            merkle_aggregator.submit_root(
                org_id,
                body["root_hash"],
                tree_size=body.get("tree_size", 0),
            )
            proof = merkle_aggregator.generate_proof(org_id)
            merkle_proof = proof.to_dict() if proof else {}
        try:
            cred = VerifiableGovernanceCredential.issue(
                subject_did=subject_did,
                issuer_did=issuer_did,
                scope=scope,
                merkle_proof=merkle_proof,
                signing_key=_credential_signing_key(),
                ttl_seconds=float(body.get("ttl_seconds", 86400)),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _governance_credentials().store(cred)
        return {"credential": cred.to_dict(), "verification": cred.verify()}

    @router.get("/api/v1/federation/governance/credential/revocation-list")
    def governance_credential_revocation_list() -> dict[str, Any]:
        """导出吊销列表；配置签名密钥时返回带 Ed25519 签名的版本防篡改。

        未配置签名密钥时降级为未签名列表（store 缺失仍 503）。
        """
        store = _governance_credentials()
        if credential_signing_key is not None:
            return store.build_signed_revocation_list(
                credential_signing_key, server_id=server_id
            )
        return {"server_id": server_id, "revoked": store.revocation_list()}

    @router.get("/api/v1/federation/governance/credential/{credential_id}")
    def governance_credential_get(credential_id: str) -> dict[str, Any]:
        """查询凭证并返回离线验证结果（监管/审计方 GET 即可核验）。"""
        store = _governance_credentials()
        cred = store.get(credential_id)
        if cred is None:
            raise HTTPException(status_code=404, detail=f"credential {credential_id} not found")
        return {
            "credential": cred.to_dict(),
            "verification": cred.verify(revoked=store.is_revoked(credential_id)),
        }

    @router.post("/api/v1/federation/governance/credential/{credential_id}/revoke")
    def governance_credential_revoke(credential_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """吊销凭证（保留历史，记录原因与来源）。"""
        try:
            _governance_credentials().revoke(
                credential_id,
                reason=body.get("reason", "unspecified"),
                source=body.get("source", ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"revoked": True, "credential_id": credential_id}

    app.include_router(router)
    return app


# ── Client ───────────────────────────────────────────────────────────────


class FederationHTTPClient:
    """httpx-based client for the federated HTTP transport.

    Usage::

        client = FederationHTTPClient("http://127.0.0.1:9100")
        catalog = client.fetch_catalog()
        client.push_policy(event_dict)
        client.submit_trust_report(report_dict)
    """

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FederationHTTPClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ── Endpoint wrappers ────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        response = self._client.get("/api/v1/federation/health")
        response.raise_for_status()
        return response.json()

    def fetch_catalog(self, **params: Any) -> list[dict[str, Any]]:
        """Fetch the peer's ADP catalog (matches HTTPDiscoveryTransport)."""
        query = {k: v for k, v in params.items() if v is not None}
        response = self._client.get(_ADP_CATALOG_PATH, params=query)
        response.raise_for_status()
        return response.json().get("agents", [])

    def register_agent(self, body: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post("/api/v1/federation/gateway/register", json=body)
        response.raise_for_status()
        return response.json()

    def fetch_agents(self) -> list[dict[str, Any]]:
        response = self._client.get("/api/v1/federation/gateway/agents")
        response.raise_for_status()
        return response.json().get("agents", [])

    def push_policy(self, event: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post("/api/v1/federation/policy/push", json=event)
        response.raise_for_status()
        return response.json()

    def fetch_policy_rules(self) -> list[dict[str, Any]]:
        response = self._client.get("/api/v1/federation/policy/rules")
        response.raise_for_status()
        return response.json().get("rules", [])

    def submit_trust_report(self, report: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post("/api/v1/federation/trust/report", json=report)
        response.raise_for_status()
        return response.json()

    def fetch_trust_reports(self, agent_id: str) -> list[dict[str, Any]]:
        response = self._client.get(f"/api/v1/federation/trust/report/{agent_id}")
        response.raise_for_status()
        return response.json().get("reports", [])

    def fetch_network_peers(self) -> list[dict[str, Any]]:
        """Fetch the server's known peers (bootstrap discovery)."""
        response = self._client.get(PEERS_ENDPOINT_PATH)
        response.raise_for_status()
        return response.json().get("peers", [])

    def send_heartbeat(
        self,
        server_id: str,
        endpoint_url: str,
        generation: int = 0,
    ) -> dict[str, Any]:
        """Send a node heartbeat to the server."""
        message = HeartbeatMessage(
            server_id=server_id,
            endpoint_url=endpoint_url,
            generation=generation,
        )
        response = self._client.post(HEARTBEAT_ENDPOINT_PATH, json=message.to_dict())
        response.raise_for_status()
        return response.json()

    def fetch_network_members(self) -> dict[str, Any]:
        """Fetch the server's membership table."""
        response = self._client.get(_NETWORK_MEMBERS_PATH)
        response.raise_for_status()
        return response.json()

    # ── Settlement reconciliation (Phase 3.2) ──────────────────────

    def fetch_settlement_summary(self) -> dict[str, Any]:
        """Fetch the server's settlement summary."""
        response = self._client.get("/api/v1/federation/settlement/summary")
        response.raise_for_status()
        return response.json()

    def fetch_settlement_root(self) -> dict[str, Any]:
        """Fetch the server's settlement Merkle root."""
        response = self._client.get("/api/v1/federation/settlement/root")
        response.raise_for_status()
        return response.json()

    def fetch_settlement_ledger(self) -> dict[str, Any]:
        """Fetch the server's ledger snapshot (reconciliation input)."""
        response = self._client.get(_SETTLEMENT_LEDGER_PATH)
        response.raise_for_status()
        return response.json()

    def run_settlement_reconcile(
        self,
        peer_url: str,
        arbitrate: bool = False,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """Ask the server to reconcile its ledger against ``peer_url``.

        When ``arbitrate`` is true, conflicts are arbitrated against the
        server's authoritative metering source.
        """
        response = self._client.post(
            "/api/v1/federation/settlement/reconcile",
            json={"peer_url": peer_url, "arbitrate": arbitrate, "timeout": timeout},
        )
        response.raise_for_status()
        return response.json()

    # ── Identity service (Phase 3.4) ─────────────────────────────────

    def create_identity(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a ``did:maref:`` identity with a derived AIC."""
        response = self._client.post("/api/v1/federation/identity/create", json=body)
        response.raise_for_status()
        return response.json()

    def resolve_identity(self, did_string: str) -> dict[str, Any]:
        """Resolve a DID to a W3C DID Document."""
        response = self._client.get(
            f"/api/v1/federation/identity/resolve/{did_string}"
        )
        response.raise_for_status()
        return response.json()

    def deactivate_identity(self, did_string: str) -> dict[str, Any]:
        """Soft-deactivate a DID."""
        response = self._client.post(
            "/api/v1/federation/identity/deactivate",
            json={"did": did_string},
        )
        response.raise_for_status()
        return response.json()

    def verify_aic(self, aic_string: str) -> dict[str, Any]:
        """Verify an AIC string (CRC-16 checksum) and its DID binding."""
        response = self._client.get(
            f"/api/v1/federation/identity/aic/verify/{aic_string}"
        )
        response.raise_for_status()
        return response.json()

    def identity_did_to_aic(self, did_string: str) -> dict[str, Any]:
        """Translate a DID to its bound AIC string."""
        response = self._client.get(f"/api/v1/federation/identity/did/{did_string}/aic")
        response.raise_for_status()
        return response.json()

    def identity_aic_to_did(self, aic_string: str) -> dict[str, Any]:
        """Translate an AIC string to its bound DID."""
        response = self._client.get(f"/api/v1/federation/identity/aic/{aic_string}/did")
        response.raise_for_status()
        return response.json()

    def fetch_identities(self) -> list[dict[str, Any]]:
        """List all registered identities."""
        response = self._client.get("/api/v1/federation/identity/list")
        response.raise_for_status()
        return response.json().get("identities", [])

    def fetch_identity_summary(self) -> dict[str, Any]:
        """Fetch the identity service operational summary."""
        response = self._client.get("/api/v1/federation/identity/summary")
        response.raise_for_status()
        return response.json()

    # ── Regulatory compliance (Phase 3.5) ─────────────────────────────

    def evaluate_compliance(
        self,
        trigram: str,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate an action across all registered jurisdictions."""
        response = self._client.post(
            "/api/v1/federation/compliance/evaluate",
            json={"trigram": trigram, "action": action, "context": context or {}},
        )
        response.raise_for_status()
        return response.json()

    def compliance_report(self) -> dict[str, Any]:
        """Fetch the cross-jurisdiction compliance report."""
        response = self._client.get("/api/v1/federation/compliance/report")
        response.raise_for_status()
        return response.json()

    def compliance_decisions(self) -> list[dict[str, Any]]:
        """Fetch the raw decision audit trail."""
        response = self._client.get("/api/v1/federation/compliance/decisions")
        response.raise_for_status()
        return response.json().get("decisions", [])

    def compliance_summary(self) -> dict[str, Any]:
        """Fetch the rule-library summary."""
        response = self._client.get("/api/v1/federation/compliance/summary")
        response.raise_for_status()
        return response.json()


__all__ = [
    "FederationHTTPClient",
    "agent_to_catalog_dict",
    "create_federation_app",
]

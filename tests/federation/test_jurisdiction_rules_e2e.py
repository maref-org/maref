"""Phase 3.5 — regulatory compliance mapping.

Covers the two sub-goals of task 3.5:

1. **Real rule books** — GDPR (EU 2016/679), China CSL/DSL/Gen-AI measures,
   and the CISA/Five-Eyes Agentic AI Security Guidance are installed onto
   :class:`JurisdictionPolicyRouter` via :mod:`jurisdiction_rules`. The
   same action is evaluated against each jurisdiction's law.
2. **Compliance report generation** — every decision is appended to an
   audit trail (optionally HMAC-signed via :class:`AuditLogger`) and a
   cross-jurisdiction report is generated for regulatory review.

Acceptance: the same operation yields **different compliance decisions in
2+ jurisdictions**, and the decision is **auditable** (trace back to the
winning rule and its legal article).
"""

from __future__ import annotations

import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from maref.federation.federation_http import (
    FederationHTTPClient,
    create_federation_app,
)
from maref.federation.gateway import FederationGateway
from maref.federation.jurisdiction_router import (
    JurisdictionPolicyRouter,
)
from maref.federation.jurisdiction_rules import (
    create_regulatory_router,
    install_regulatory_rules,
)
from maref.federation.policy import FederationPolicyEngine, PolicyDecision
from maref.federation.policy_subscriber import FederatedPolicySubscriber
from maref.federation.trust import FederatedTrustEngine
from maref.governance.audit import AuditLogger
from maref.recursive.trust_engine_v2 import TrustEngineV2

HEALTH_PATH = "/api/v1/federation/health"


def _router() -> JurisdictionPolicyRouter:
    return create_regulatory_router()


def _build_compliance_app(router: JurisdictionPolicyRouter) -> FastAPI:
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    subscriber = FederatedPolicySubscriber(
        local_engine=FederationPolicyEngine(),
        local_org="compliance-server",
    )
    return create_federation_app(
        gateway,
        trust_engine,
        subscriber,
        server_id="compliance-server",
        jurisdiction_router=router,
    )


class ThreadedComplianceServer:
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
        raise RuntimeError("threaded compliance server failed to start")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10.0)


# ── Rule-library structure ───────────────────────────────────────────────


def test_rule_library_installed_three_jurisdictions() -> None:
    router = _router()
    assert router.jurisdiction_count() == 3
    summary = router.router_summary()
    names = {j["name"] for j in summary["jurisdictions"]}
    assert names == {"gdpr", "china_csl", "five_eyes"}
    # Every jurisdiction carries a legal reference and real rules.
    for j in summary["jurisdictions"]:
        assert j["rule_count"] > 0


def test_rule_library_installed_ids() -> None:
    router = JurisdictionPolicyRouter()
    installed = install_regulatory_rules(router)
    assert len(installed) > 15
    assert "gdpr-art44-transfer-deny" in installed
    assert "fiveeyes-ho1-high-risk-defer" in installed


# ── Acceptance: same operation → different decisions in 2+ jurisdictions ─


def test_acceptance_cross_border_transfer_differs_across_jurisdictions() -> None:
    """The same operation yields different compliance decisions in 2+ states."""
    router = _router()
    result = router.route_action("dui", "cross_border_transfer", {"data_type": "pii"})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    # GDPR: no adequacy/SCC → DENY. China CSL: no CAC assessment → DENY.
    # Five Eyes: no cross-border constraint → ALLOW (open by default).
    assert decisions["gdpr"] == PolicyDecision.DENY
    assert decisions["china_csl"] == PolicyDecision.DENY
    assert decisions["five_eyes"] == PolicyDecision.ALLOW
    assert len(set(decisions.values())) >= 2
    # MOST_RESTRICTIVE resolution → final DENY, conflict flagged.
    assert result.conflict_detected is True
    assert result.final_decision == PolicyDecision.DENY
    # Audit trail records the per-jurisdiction split.
    entry = router.decision_log()[-1]
    assert entry["action"] == "cross_border_transfer"
    assert entry["jurisdictions"]["gdpr"]["decision"] == "deny"
    assert entry["jurisdictions"]["five_eyes"]["decision"] == "allow"


def test_acceptance_auditable_to_legal_article() -> None:
    """Decisions trace back to the winning rule and its legal article."""
    router = _router()
    router.route_action("dui", "cross_border_transfer", {"data_type": "pii"})
    entry = router.decision_log()[-1]
    gdpr = entry["jurisdictions"]["gdpr"]
    assert gdpr["winning_rule"] == "gdpr-art44-transfer-deny"
    assert gdpr["regulation_ref"] == "Regulation (EU) 2016/679"
    china = entry["jurisdictions"]["china_csl"]
    assert china["winning_rule"] == "csl-art37-transfer-deny"
    assert "Cybersecurity Law" in china["regulation_ref"]
    # The winning rule is present in the live rule set.
    rules = router.get_jurisdiction("gdpr").policy_engine.list_rules()
    assert any(r.rule_id == "gdpr-art44-transfer-deny" for r in rules)


# ── Per-jurisdiction semantics ───────────────────────────────────────────


def test_gdpr_transfer_allowed_with_adequacy() -> None:
    router = _router()
    result = router.route_action(
        "dui", "cross_border_transfer", {"transfer_basis": "adequacy"}
    )
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["gdpr"] == PolicyDecision.ALLOW
    assert decisions["china_csl"] == PolicyDecision.DENY  # still unassessed


def test_gdpr_automated_decision_tiers() -> None:
    router = _router()
    # High impact → DEFER (Art. 22(3) human review).
    result = router.route_action("li", "automated_decision_making", {"high_impact": True})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["gdpr"] == PolicyDecision.DEFER
    # No high impact → ALLOW.
    result = router.route_action("li", "automated_decision_making", {"high_impact": False})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["gdpr"] == PolicyDecision.ALLOW
    # Missing context key → fallback DENY.
    result = router.route_action("li", "automated_decision_making", {})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["gdpr"] == PolicyDecision.DENY


def test_gdpr_processing_requires_legal_basis() -> None:
    router = _router()
    result = router.route_action("kun", "personal_data_processing", {})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["gdpr"] == PolicyDecision.DENY
    result = router.route_action(
        "kun", "personal_data_processing", {"legal_basis": "consent"}
    )
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["gdpr"] == PolicyDecision.ALLOW


def test_china_genai_requires_registration() -> None:
    router = _router()
    result = router.route_action("dui", "ai_content_generation", {})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["china_csl"] == PolicyDecision.DENY
    result = router.route_action("dui", "ai_content_generation", {"registration": "filed"})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["china_csl"] == PolicyDecision.ALLOW


def test_china_important_data_localization_defer() -> None:
    router = _router()
    result = router.route_action("kan", "data_localization", {"data_category": "important"})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["china_csl"] == PolicyDecision.DEFER
    result = router.route_action("kan", "data_localization", {"data_category": "general"})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["china_csl"] == PolicyDecision.ALLOW


def test_five_eyes_delegation_bounded() -> None:
    router = _router()
    # Default: delegation denied (capability bound).
    result = router.route_action("li", "delegation", {})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["five_eyes"] == PolicyDecision.DENY
    # Within bounds → allowed.
    result = router.route_action(
        "li",
        "delegation",
        {"chain_depth": 3, "within_capability": True},
    )
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["five_eyes"] == PolicyDecision.ALLOW
    # Depth 7 (> 5) → denied.
    result = router.route_action(
        "li",
        "delegation",
        {"chain_depth": 7, "within_capability": True},
    )
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["five_eyes"] == PolicyDecision.DENY


def test_five_eyes_injection_and_hitl() -> None:
    router = _router()
    # Injection blocked.
    result = router.route_action("dui", "agent_message", {"injection_risk": "high"})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["five_eyes"] == PolicyDecision.DENY
    # High-risk action: pending approval → DEFER; granted → ALLOW; none → DENY.
    result = router.route_action("zhen", "high_risk_action", {"human_approval": "required"})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["five_eyes"] == PolicyDecision.DEFER
    result = router.route_action("zhen", "high_risk_action", {"human_approval": "granted"})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["five_eyes"] == PolicyDecision.ALLOW
    result = router.route_action("zhen", "high_risk_action", {})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["five_eyes"] == PolicyDecision.DENY


def test_five_eyes_audit_logging_mandatory() -> None:
    router = _router()
    result = router.route_action("li", "audit_logging", {"audit_enabled": False})
    decisions = {jr.jurisdiction: jr.decision for jr in result.jurisdiction_results}
    assert decisions["five_eyes"] == PolicyDecision.DENY


# ── Compliance report + audit trail ──────────────────────────────────────


def test_compliance_report_generated() -> None:
    router = _router()
    router.route_action("dui", "cross_border_transfer", {"data_type": "pii"})
    router.route_action("li", "delegation", {"chain_depth": 3, "within_capability": True})
    report = router.compliance_report()
    assert report["total_decisions"] == 2
    assert report["conflicts_detected"] == 1
    assert report["jurisdictions"]["gdpr"]["regulation_ref"] == "Regulation (EU) 2016/679"
    assert report["jurisdictions"]["gdpr"]["deny"] >= 1
    assert report["jurisdictions"]["five_eyes"]["allow"] >= 1
    assert len(report["recent_decisions"]) == 2


def test_decision_log_limits() -> None:
    router = _router()
    for _ in range(5):
        router.route_action("dui", "agent_message", {"injection_risk": "none"})
    assert len(router.decision_log()) == 5
    assert len(router.decision_log(limit=2)) == 2


def test_decision_auditable_via_hmac_audit_logger() -> None:
    """Decisions are also written to the HMAC-signed audit logger."""
    logger = AuditLogger(hmac_key="test-hmac-key-3.5")
    router = JurisdictionPolicyRouter(audit_logger=logger)
    install_regulatory_rules(router)
    router.route_action("dui", "cross_border_transfer", {})
    entries = logger.read_all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.event_type == "compliance_decision"
    assert entry.action == "cross_border_transfer"
    assert entry.metadata["final_decision"] == "deny"
    verification = logger.verify_integrity()
    assert verification["integrity_intact"] is True


# ── HTTP E2E ─────────────────────────────────────────────────────────────


def test_compliance_http_e2e() -> None:
    """Cross-jurisdiction evaluation + audit report over real HTTP."""
    router = _router()
    server = ThreadedComplianceServer(_build_compliance_app(router))
    server.start()
    try:
        with FederationHTTPClient(server.base_url) as client:
            # Evaluate the same action once.
            result = client.evaluate_compliance(
                "dui", "cross_border_transfer", {"data_type": "pii"}
            )
            assert result["final_decision"] == "deny"
            assert result["conflict_detected"] is True
            jr = {j["jurisdiction"]: j["decision"] for j in result["jurisdiction_results"]}
            assert jr["gdpr"] == "deny"
            assert jr["china_csl"] == "deny"
            assert jr["five_eyes"] == "allow"

            # Audit endpoints.
            decisions = client.compliance_decisions()
            assert len(decisions) == 1
            assert decisions[0]["jurisdictions"]["gdpr"]["winning_rule"] == (
                "gdpr-art44-transfer-deny"
            )

            report = client.compliance_report()
            assert report["total_decisions"] == 1
            assert report["jurisdictions"]["gdpr"]["regulation_ref"]

            summary = client.compliance_summary()
            assert summary["jurisdiction_count"] == 3
    finally:
        server.stop()


def test_compliance_unconfigured_returns_503() -> None:
    """Without a jurisdiction router the endpoints answer 503."""
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    subscriber = FederatedPolicySubscriber(
        local_engine=FederationPolicyEngine(),
        local_org="plain",
    )
    app = create_federation_app(gateway, trust_engine, subscriber, server_id="plain")
    server = ThreadedComplianceServer(app)
    server.start()
    try:
        with (
            FederationHTTPClient(server.base_url) as client,
            pytest.raises(httpx.HTTPStatusError),
        ):
            client.evaluate_compliance("dui", "cross_border_transfer")
    finally:
        server.stop()

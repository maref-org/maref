"""v0.49 P7 — Organization governance API: consensus + task preflight routes.

The sidecar app assembles a GovernedPipeline (v0.48 W2); these tests drive the
new ``/api/v1/federation/consensus/*`` and ``/api/v1/federation/preflight``
routes through that pipeline, closing the W-track wiring gap.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sidecar.server import create_app


@pytest.fixture()
def client() -> Any:
    from sidecar.collector import MockAgentAdapter, ObservationCollector
    from sidecar.monitor import CompositeMonitor

    app = create_app(
        collector=ObservationCollector(MockAgentAdapter()),
        monitor=CompositeMonitor(),
        allow_unauthenticated=True,
    )
    return TestClient(app)


class TestConsensusAPI:
    def test_summary(self, client: Any) -> None:
        resp = client.get("/api/v1/federation/consensus/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert "member_count" in body
        assert "quorum_size" in body
        assert "topology" in body

    def test_membership(self, client: Any) -> None:
        resp = client.get("/api/v1/federation/consensus/membership")
        assert resp.status_code == 200
        assert resp.json()["membership_enforced"] is False

    def test_propose_then_vote_and_get(self, client: Any) -> None:
        propose = client.post(
            "/api/v1/federation/consensus/propose",
            json={
                "proposer_id": "org-acme",
                "topic": "add-agent",
                "payload": {"agent_id": "a1"},
            },
        )
        assert propose.status_code == 200
        proposal_id = propose.json()["proposal_id"]

        # reject with invalid choice → 400
        bad = client.post(
            f"/api/v1/federation/consensus/{proposal_id}/vote",
            json={"voter_id": "org-b", "choice": "maybe"},
        )
        assert bad.status_code == 400

        # valid vote
        vote = client.post(
            f"/api/v1/federation/consensus/{proposal_id}/vote",
            json={"voter_id": "org-b", "choice": "approve", "reason": "ok"},
        )
        assert vote.status_code == 200
        assert vote.json()["accepted"] is True

        detail = client.get(f"/api/v1/federation/consensus/{proposal_id}")
        assert detail.status_code == 200
        assert detail.json()["proposal_id"] == proposal_id
        assert detail.json()["approve_count"] == 1

    def test_vote_missing_proposal_404(self, client: Any) -> None:
        resp = client.post(
            "/api/v1/federation/consensus/nope/vote",
            json={"voter_id": "org-b", "choice": "approve"},
        )
        assert resp.status_code == 404

    def test_list_proposals(self, client: Any) -> None:
        client.post(
            "/api/v1/federation/consensus/propose",
            json={"proposer_id": "org-acme", "topic": "policy-change"},
        )
        resp = client.get("/api/v1/federation/consensus/proposals")
        assert resp.status_code == 200
        assert len(resp.json()["proposals"]) == 1
        assert resp.json()["proposals"][0]["topic"] == "policy-change"


class TestPreflightAPI:
    def test_status(self, client: Any) -> None:
        resp = client.get("/api/v1/federation/preflight/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] > 0
        assert isinstance(body["checks"], list)

    def test_run_preflight(self, client: Any) -> None:
        resp = client.post(
            "/api/v1/federation/preflight",
            json={"context": {"agent_id": "agent-1", "task_description": "refactor"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "passed" in body
        assert "checks" in body


class TestFailClosed:
    def test_503_when_pipeline_absent(self) -> None:
        """If the sidecar did not assemble a GovernedPipeline, endpoints 503."""
        from fastapi import FastAPI

        from sidecar.org_governance_router import router

        app = FastAPI()
        app.include_router(router)  # no app.state.governed
        tc = TestClient(app)
        resp = tc.get("/api/v1/federation/consensus/summary")
        assert resp.status_code == 503


class TestScopeEnforcement:
    def test_federation_scopes_registered(self) -> None:
        """Review regression: @require_auth must sit *below* @router.* so the
        scope marker lands on the registered endpoint (FastAPI's router
        decorator registers the function and returns it unchanged; putting
        @require_auth above it silently drops the scope)."""
        from sidecar.api_auth import _SCOPE_MAP

        expected = {
            "/api/v1/federation/consensus/propose": "federation:write",
            "/api/v1/federation/consensus/{proposal_id}/vote": "federation:write",
            "/api/v1/federation/preflight": "federation:execute",
            "/api/v1/federation/consensus/summary": "federation:read",
        }
        for path, scope in expected.items():
            assert _SCOPE_MAP.get(path) == scope, f"{path} missing scope {scope}"

    def test_authenticated_app_requires_token(self) -> None:
        """Fail-closed: without the dev bypass, unauthenticated federation
        requests are rejected before reaching the handlers."""
        from sidecar.collector import MockAgentAdapter, ObservationCollector
        from sidecar.monitor import CompositeMonitor

        app = create_app(
            collector=ObservationCollector(MockAgentAdapter()),
            monitor=CompositeMonitor(),
            allow_unauthenticated=False,
        )
        tc = TestClient(app)
        resp = tc.get("/api/v1/federation/consensus/summary")
        assert resp.status_code == 401

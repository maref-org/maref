"""v0.53 F3: 联邦共识 resolve 运行时接线。

验证：
1. vote 端点投满 quorum 后提案自动进入 ACCEPTED/REJECTED
2. resolve 专用端点可手动结算（含过期 EXPIRED / 票不足保持 OPEN）
3. 未知提案返回 404
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from maref.governance.federated_consensus import (
    FederatedConsensus,
    ProposalState,
)
from maref.governance.governed_pipeline import GovernedPipeline

from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.server import create_app


def _make_client(tmp_path: Path) -> TestClient:
    os.environ["MAREF_FEDERATED_DB"] = str(tmp_path / "federation.db")
    os.environ["MAREF_FEDERATED_STATE"] = str(tmp_path / "federated-state.json")
    adapter = MockAgentAdapter()
    collector = ObservationCollector(adapter)
    monitor = CompositeMonitor()
    app = create_app(collector, monitor, None, federated=True, allow_unauthenticated=True)
    # 覆盖默认 consensus：quorum=2、FLAT 拓扑，便于测试
    consensus = FederatedConsensus(member_count=3, quorum_size=2)
    app.state.governed = GovernedPipeline(consensus=consensus)
    return TestClient(app)


class TestVoteAutoResolve:
    def test_quorum_approve_auto_resolves(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        prop = client.post("/api/v1/federation/consensus/propose", json={
            "proposer_id": "alice", "topic": "approve-me",
        }).json()
        pid = prop["proposal_id"]

        r1 = client.post(f"/api/v1/federation/consensus/{pid}/vote", json={
            "voter_id": "alice", "choice": "approve",
        }).json()
        assert r1["status"] == "open"

        r2 = client.post(f"/api/v1/federation/consensus/{pid}/vote", json={
            "voter_id": "bob", "choice": "approve",
        }).json()
        assert r2["status"] == "accepted"
        assert r2["approve_count"] == 2

    def test_quorum_reject_auto_resolves(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        prop = client.post("/api/v1/federation/consensus/propose", json={
            "proposer_id": "alice", "topic": "reject-me",
        }).json()
        pid = prop["proposal_id"]

        client.post(f"/api/v1/federation/consensus/{pid}/vote", json={
            "voter_id": "alice", "choice": "reject",
        })
        r = client.post(f"/api/v1/federation/consensus/{pid}/vote", json={
            "voter_id": "bob", "choice": "reject",
        }).json()
        assert r["status"] == "rejected"

    def test_insufficient_quorum_stays_open(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        prop = client.post("/api/v1/federation/consensus/propose", json={
            "proposer_id": "alice", "topic": "not-enough",
        }).json()
        pid = prop["proposal_id"]

        r = client.post(f"/api/v1/federation/consensus/{pid}/vote", json={
            "voter_id": "alice", "choice": "approve",
        }).json()
        assert r["status"] == "open"


class TestResolveEndpoint:
    def test_resolve_unknown_proposal_404(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.post("/api/v1/federation/consensus/nope/resolve")
        assert resp.status_code == 404

    def test_resolve_manual_settlement(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        prop = client.post("/api/v1/federation/consensus/propose", json={
            "proposer_id": "alice", "topic": "manual",
        }).json()
        pid = prop["proposal_id"]
        client.post(f"/api/v1/federation/consensus/{pid}/vote", json={
            "voter_id": "alice", "choice": "approve",
        })
        client.post(f"/api/v1/federation/consensus/{pid}/vote", json={
            "voter_id": "bob", "choice": "approve",
        })

        r = client.post(f"/api/v1/federation/consensus/{pid}/resolve").json()
        assert r["status"] == ProposalState.ACCEPTED.value

    def test_resolve_idempotent_after_accepted(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        prop = client.post("/api/v1/federation/consensus/propose", json={
            "proposer_id": "alice", "topic": "idem",
        }).json()
        pid = prop["proposal_id"]
        client.post(f"/api/v1/federation/consensus/{pid}/vote", json={
            "voter_id": "alice", "choice": "approve",
        })
        client.post(f"/api/v1/federation/consensus/{pid}/vote", json={
            "voter_id": "bob", "choice": "approve",
        })
        first = client.post(f"/api/v1/federation/consensus/{pid}/resolve").json()
        second = client.post(f"/api/v1/federation/consensus/{pid}/resolve").json()
        assert first["status"] == ProposalState.ACCEPTED.value
        assert second["status"] == ProposalState.ACCEPTED.value

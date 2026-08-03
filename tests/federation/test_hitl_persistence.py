"""v0.47 F4 — CrossOrgHITL SQLite persistence + restart recovery."""

from __future__ import annotations

from pathlib import Path

from maref.federation.hitl import CrossOrgApprovalStatus, CrossOrgHITL


def _hitl(db_path: Path | None = None) -> CrossOrgHITL:
    return CrossOrgHITL(db_path=db_path)


def _request(hitl: CrossOrgHITL) -> str:
    req = hitl.request_approval(
        action="payment:transfer",
        description="cross-org transfer",
        requesting_org="Acme",
        reviewing_org="BetaLabs",
        agent_did="did:1",
        task_id="t1",
    )
    return req.request_id


class TestCrossOrgHITLPersistence:
    def test_request_recovered_after_reload(self, tmp_path: Path) -> None:
        db = tmp_path / "hitl.db"
        hitl = _hitl(db)
        req_id = _request(hitl)

        reloaded = _hitl(db)
        req = reloaded.get_request(req_id)
        assert req is not None
        assert req.action == "payment:transfer"
        assert req.reviewing_org == "BetaLabs"

    def test_status_recovered(self, tmp_path: Path) -> None:
        db = tmp_path / "hitl.db"
        hitl = _hitl(db)
        req_id = _request(hitl)
        hitl.approve(req_id, reviewer="human-1")

        reloaded = _hitl(db)
        req = reloaded.get_request(req_id)
        assert req is not None
        assert req.status == CrossOrgApprovalStatus.APPROVED
        assert req.reviewer == "human-1"

    def test_no_db_path_in_memory(self) -> None:
        hitl = _hitl()
        req_id = _request(hitl)
        assert hitl.get_request(req_id) is not None

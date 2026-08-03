"""v0.47 F4 — JurisdictionPolicyRouter decision log persistence."""

from __future__ import annotations

from pathlib import Path

from maref.federation.jurisdiction_router import JurisdictionPolicyRouter
from maref.federation.jurisdiction_rules import install_regulatory_rules


def _router(db_path: Path | None = None) -> JurisdictionPolicyRouter:
    router = JurisdictionPolicyRouter(db_path=db_path)
    install_regulatory_rules(router)
    return router


class TestJurisdictionDecisionPersistence:
    def test_decision_log_recovered_after_reload(self, tmp_path: Path) -> None:
        db = tmp_path / "juris.db"
        router = _router(db)
        router.route_action("dui", "cross_border_transfer", {"data_type": "pii"})

        reloaded = _router(db)
        log = reloaded.decision_log()
        assert len(log) == 1
        assert log[0]["action"] == "cross_border_transfer"

    def test_no_db_path_in_memory(self) -> None:
        router = _router()
        router.route_action("dui", "cross_border_transfer", {"data_type": "pii"})
        assert len(router.decision_log()) == 1

from __future__ import annotations

from maref.integration.percv.hypothesis_bridge import PERCVHypothesisBridge


def test_high_confidence_card_becomes_optimizer_hypothesis() -> None:
    card = {
        "id": "S-1",
        "type": "research_signal",
        "content": "coverage gaps in self_executor reduce safety",
        "metadata": {"confidence": 0.9, "verification_status": "verified"},
    }
    bridge = PERCVHypothesisBridge(min_confidence=0.8)

    hypotheses = bridge.cards_to_hypotheses([card])

    assert len(hypotheses) == 1
    assert hypotheses[0].source == "percv"
    assert "self_executor" in hypotheses[0].description


def test_low_confidence_card_is_ignored() -> None:
    card = {
        "id": "S-2",
        "type": "research_signal",
        "content": "weak signal",
        "metadata": {"confidence": 0.3, "verification_status": "verified"},
    }
    bridge = PERCVHypothesisBridge(min_confidence=0.8)

    assert bridge.cards_to_hypotheses([card]) == []


def test_unverified_card_is_ignored() -> None:
    card = {
        "id": "S-3",
        "type": "research_signal",
        "content": "unverified signal",
        "metadata": {"confidence": 0.9, "verification_status": "draft"},
    }
    bridge = PERCVHypothesisBridge(min_confidence=0.8)

    assert bridge.cards_to_hypotheses([card]) == []

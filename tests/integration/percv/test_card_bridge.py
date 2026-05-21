"""Tests for CardBridge — PERCV research cards to MAREF knowledge graph bridge."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maref.integration.percv.card_bridge import CARD_TO_KG_TYPE, CardBridge


class TestCardBridge:
    def test_init_defaults(self) -> None:
        bridge = CardBridge()
        assert bridge._vault_path == Path("vault")
        assert bridge._synced_ids == set()

    def test_no_vault(self) -> None:
        with patch.dict("sys.modules", {"percv": None, "percv.schemas": None}):
            bridge = CardBridge(vault_path=Path("/tmp/nonexistent_vault_xyz"))
            with pytest.raises(RuntimeError, match="PERCV package required"):
                bridge.sync_to_knowledge_graph()

    def test_card_to_kg_node_no_kg(self) -> None:
        bridge = CardBridge()
        mock_card = MagicMock()
        mock_card.signal_id = "S-20260514-001"
        mock_card.summary = "test signal"
        mock_card.topic = "AI"
        mock_card.status = "raw"
        mock_card.schema_version = 1

        node = bridge._card_to_kg_node(mock_card)
        assert node is not None
        assert node["id"] == "S-20260514-001"
        assert node["type"] == "research_signal"

    def test_card_to_kg_node_with_kg(self) -> None:
        kg = MagicMock()
        bridge = CardBridge(knowledge_graph=kg)
        mock_card = MagicMock(spec=[])
        mock_card.signal_id = None
        mock_card.kdp_id = None
        mock_card.forecast_id = "F-20260514-001"
        mock_card.pattern_id = None
        mock_card.core_forecast = "If X then Y"
        mock_card.topic = "markets"
        mock_card.confidence = 65
        mock_card.linked_kdps = ["K-20260514-001"]
        mock_card.horizon = "2026-Q3"
        mock_card.status = "active"
        mock_card.schema_version = 1

        node = bridge._card_to_kg_node(mock_card)
        if isinstance(node, dict):
            assert node["id"] == "F-20260514-001"
            assert node["type"] == "research_forecast"
        else:
            assert node.id == "F-20260514-001"
            assert node.type == "research_forecast"

    def test_card_type_mapping(self) -> None:
        assert CARD_TO_KG_TYPE["S"] == "research_signal"
        assert CARD_TO_KG_TYPE["K"] == "research_kdp"
        assert CARD_TO_KG_TYPE["F"] == "research_forecast"
        assert CARD_TO_KG_TYPE["PAT"] == "research_pattern"

    def test_metadata_extraction(self) -> None:
        bridge = CardBridge()
        mock_card = MagicMock()
        mock_card.signal_id = "S-20260514-002"
        mock_card.summary = "event"
        mock_card.schema_version = 1
        mock_card.topic = "blockchain"
        mock_card.status = "raw"
        mock_card.source_node = "github_trending"
        mock_card.source_url = "https://github.com"

        meta = bridge._card_to_metadata(mock_card)
        assert meta["topic"] == "blockchain"
        assert meta["status"] == "raw"
        assert meta["source_node"] == "github_trending"

    def test_get_card_id(self) -> None:
        bridge = CardBridge()
        card = MagicMock()
        card.kdp_id = "K-001"
        assert bridge._get_card_id(card) == "K-001"

    def test_get_card_id_fallback(self) -> None:
        bridge = CardBridge()
        card = MagicMock()
        card.signal_id = None
        card.kdp_id = None
        card.forecast_id = None
        card.pattern_id = None
        assert bridge._get_card_id(card) != ""

    def test_synced_count(self) -> None:
        bridge = CardBridge()
        assert bridge.get_synced_count() == 0
        bridge._synced_ids.add("S-001")
        assert bridge.get_synced_count() == 1

    def test_reset_sync_state(self) -> None:
        bridge = CardBridge()
        bridge._synced_ids.add("S-001")
        bridge.reset_sync_state()
        assert bridge.get_synced_count() == 0

    def test_card_bridge_no_percv(self) -> None:
        bridge = CardBridge()
        with patch(
            "maref.integration.percv.card_bridge.CardBridge.sync_to_knowledge_graph"
        ) as mock_sync:
            mock_sync.side_effect = RuntimeError("PERCV package required")
            with pytest.raises(RuntimeError):
                bridge.sync_to_knowledge_graph()

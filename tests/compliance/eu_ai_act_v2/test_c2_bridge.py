"""Tests for C2 bridge: Art.12-14 compliance wiring + Merkle chain."""

from __future__ import annotations

from unittest.mock import MagicMock

from maref.compliance.eu_ai_act_v2.engine import EUAIComplianceEngineV2
from maref.compliance.eu_ai_act_v2.human_oversight import (
    HumanOversightBridge,
    OversightMode,
)
from maref.compliance.eu_ai_act_v2.record_keeping import (
    AIActLogEntry,
    AIActLogger,
    _AIActToAuditAdapter,
)
from maref.compliance.eu_ai_act_v2.risk_classifier import (
    AnnexIIICategory,
    RiskLevel,
)
from maref.compliance.eu_ai_act_v2.transparency import TransparencyManager


# ------------------------------------------------------------------ #
# Art.12 — Record-Keeping + Merkle Chain Bridge
# ------------------------------------------------------------------ #

class TestArt12MerkleBridge:
    def test_log_event_with_chain_integrator(self) -> None:
        mock_chain = MagicMock()
        mock_chain.record_audit_entry.return_value = "abc123"
        logger = AIActLogger("test-sys", chain_integrator=mock_chain)
        entry = logger.log_event(
            session_id="s1",
            use_period_start="2026-01-01T00:00:00",
            use_period_end="2026-01-01T01:00:00",
            input_data="test input",
        )
        assert logger.get_merkle_hash(entry.entry_id) == "abc123"
        mock_chain.record_audit_entry.assert_called_once()

    def test_log_event_without_chain_integrator(self) -> None:
        logger = AIActLogger("test-sys")
        entry = logger.log_event(
            session_id="s1",
            use_period_start="2026-01-01T00:00:00",
            use_period_end="2026-01-01T01:00:00",
            input_data="test input",
        )
        assert logger.get_merkle_hash(entry.entry_id) is None

    def test_chain_integrator_not_called_on_error(self) -> None:
        mock_chain = MagicMock()
        mock_chain.record_audit_entry.side_effect = TypeError("bad type")
        logger = AIActLogger("test-sys", chain_integrator=mock_chain)
        entry = logger.log_event(
            session_id="s1",
            use_period_start="2026-01-01T00:00:00",
            use_period_end="2026-01-01T01:00:00",
            input_data="test",
        )
        assert entry is not None
        assert logger.get_merkle_hash(entry.entry_id) is None

    def test_retention_status_shows_merkle_when_configured(self) -> None:
        mock_chain = MagicMock()
        mock_chain.record_audit_entry.return_value = "hash1"
        logger = AIActLogger("test-sys", chain_integrator=mock_chain)
        logger.log_event("s1", "2026-01-01T00:00:00", "2026-01-01T01:00:00", "data")
        status = logger.get_retention_status()
        assert status["merkle_chain_enabled"] is True
        assert status["merkle_anchored_events"] == 1

    def test_retention_status_no_merkle_by_default(self) -> None:
        logger = AIActLogger("test-sys")
        status = logger.get_retention_status()
        assert "merkle_chain_enabled" not in status

    def test_adapter_maps_core_fields(self) -> None:
        entry = AIActLogEntry(
            entry_id="e1",
            system_id="sys1",
            system_version="1.0",
            session_id="s1",
            event_timestamp_utc="2026-01-01T00:00:00+00:00",
            use_period_start="2026-01-01T00:00:00",
            use_period_end="2026-01-01T01:00:00",
            input_data_hash="hash",
            decision_type="approve",
            confidence_score=0.95,
            risk_event=True,
            anomaly_flag=False,
        )
        adapter = _AIActToAuditAdapter(entry, "sys1")
        assert adapter.id == "e1"
        assert adapter.actor == "sys1"
        assert adapter.event_type == "ai_act_log"
        assert adapter.action == "approve"
        assert "Session s1" in adapter.details
        assert adapter.metadata["risk_event"] is True
        assert adapter.signature_type == "unsigned"


# ------------------------------------------------------------------ #
# Art.12 — AIActLogger integration in engine
# ------------------------------------------------------------------ #

class TestArt12InEngine:
    def test_engine_recorder_is_aiact_logger(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        assert hasattr(engine, "recorder")
        assert engine.recorder.count_events() == 0

    def test_engine_summary_includes_record_count(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        summary = engine.generate_summary(categories=[])
        assert summary.record_keeping_enabled
        assert summary.record_keeping_count >= 0


# ------------------------------------------------------------------ #
# Art.13 — Transparency integration in engine
# ------------------------------------------------------------------ #

class TestArt13Transparency:
    def test_engine_has_transparency_manager(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        assert hasattr(engine, "transparency_mgr")
        assert isinstance(engine.transparency_mgr, TransparencyManager)

    def test_engine_summary_includes_transparency(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        summary = engine.generate_summary(categories=[])
        assert summary.transparency_complete is not None
        assert isinstance(summary.transparency_missing_obligations, list)


# ------------------------------------------------------------------ #
# Art.14 — Human Oversight integration in engine
# ------------------------------------------------------------------ #

class TestArt14Oversight:
    def test_engine_summary_includes_oversight(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        summary = engine.generate_summary(categories=["biometrics"])
        assert summary.oversight_assessment is not None
        assert summary.oversight_assessment.overall_score > 0

    def test_oversight_auto_populates_section_5(self) -> None:
        engine = EUAIComplianceEngineV2("test", "1.0.0")
        engine.auto_populate_documentation(categories=["biometrics"])
        doc = engine.technical_docs.generate()
        s5 = doc["section_5_human_oversight"]
        assert "mode" in s5
        assert "gap" not in s5.get("mode", "")

    def test_oversight_mode_recommended_by_risk(self) -> None:
        bridge = HumanOversightBridge("test", RiskLevel.HIGH)
        mode = bridge.recommend_oversight_mode()
        assert mode == OversightMode.HITL

    def test_oversight_lower_risk_lower_mode(self) -> None:
        bridge = HumanOversightBridge("test", RiskLevel.LIMITED)
        mode = bridge.recommend_oversight_mode()
        assert mode == OversightMode.HATL

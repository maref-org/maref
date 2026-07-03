from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from maref.integration.percv.meta_ratchet import (
    MetaRatchet,
    ProtocolChange,
    StagnationDiagnosis,
)
from maref.integration.percv.multi_target_ratchet import ImprovementTarget
from maref.integration.percv.ratchet_bridge import RatchetIterationRecord


class TestMetaRatchetRecursionHardening:
    def test_self_modification_blocked(self) -> None:
        meta = MetaRatchet()
        for method_name in list(meta.CONFIGURATIONAL_IMMUTABLES)[:5]:
            assert meta._check_self_modification(method_name) is True

    def test_allowed_non_self_modification(self) -> None:
        meta = MetaRatchet()
        assert meta._check_self_modification("max_consecutive_discards") is False
        assert meta._check_self_modification("metric_direction") is False
        assert meta._check_self_modification("evaluation_command") is False
        assert meta._check_self_modification("unknown_key") is False

    def test_immutables_defined(self) -> None:
        meta = MetaRatchet()
        immutables = meta.CONFIGURATIONAL_IMMUTABLES
        assert isinstance(immutables, frozenset)
        assert len(immutables) > 0
        assert "CONFIGURATIONAL_IMMUTABLES" in immutables
        assert "propose_protocol_change" in immutables
        assert "_check_self_modification" in immutables

    def test_self_modification_protected_flag(self) -> None:
        change = ProtocolChange(
            config_key="test_key",
            old_value=1,
            new_value=2,
            rationale="test",
        )
        assert change.self_modification_protected is True

    def test_logging_on_block(self, caplog: pytest.LogCaptureFixture) -> None:
        meta = MetaRatchet()
        bridge = MagicMock()
        bridge.get_history.return_value = [
            RatchetIterationRecord(
                iteration=i,
                score=0.5,
                approved=False,
                best_score=0.5,
                best_iteration=None,
                duration_s=1.0,
                status="discard",
                target=ImprovementTarget.PROMPT_DISTILL.value,
            )
            for i in range(5)
        ]
        bridge.check_redlines.return_value = []
        meta._ratchet_bridge = bridge

        immutables_with_key = meta.CONFIGURATIONAL_IMMUTABLES | {"max_consecutive_discards"}

        with patch.object(meta, "CONFIGURATIONAL_IMMUTABLES", immutables_with_key):
            with caplog.at_level(logging.WARNING):
                diagnosis = StagnationDiagnosis(
                    diagnosis_type="consecutive_discards",
                    severity="high",
                    details="test consecutive discards",
                    affected_target=ImprovementTarget.PROMPT_DISTILL,
                )
                result = meta.propose_protocol_change(diagnosis)

            assert result is None
            assert "Self-modification blocked" in caplog.text
            assert "max_consecutive_discards" in caplog.text

from __future__ import annotations

from unittest.mock import MagicMock

from maref.integration.percv.meta_ratchet import MetaRatchet
from maref.integration.percv.multi_target_ratchet import ImprovementTarget
from maref.integration.percv.ratchet_bridge import RatchetIterationRecord


class TestMetaRatchet:
    def test_init_defaults(self) -> None:
        meta = MetaRatchet()
        assert meta.diagnosis_history == []
        assert meta.CONSTITUTIONAL_IMMUTABLES == ["branch_prefix"]

    def test_check_triggers_no_bridge(self) -> None:
        meta = MetaRatchet()
        triggers = meta.check_triggers(ImprovementTarget.PROMPT_DISTILL)
        assert triggers == []

    def test_check_triggers_consecutive_discards(self) -> None:
        bridge = MagicMock()
        bridge.get_history.return_value = [
            RatchetIterationRecord(iteration=i, score=0.5, approved=False, best_score=0.5, best_iteration=None, duration_s=1.0, status="discard", target=ImprovementTarget.PROMPT_DISTILL.value)
            for i in range(5)
        ]
        meta = MetaRatchet(ratchet_bridge=bridge)
        triggers = meta.check_triggers(ImprovementTarget.PROMPT_DISTILL)
        assert "consecutive_discards" in triggers

    def test_check_triggers_no_match(self) -> None:
        bridge = MagicMock()
        bridge.get_history.return_value = [
            RatchetIterationRecord(iteration=i, score=0.8, approved=True, best_score=0.8, best_iteration=0, duration_s=1.0, status="keep", target=ImprovementTarget.PROMPT_DISTILL.value)
            for i in range(3)
        ]
        meta = MetaRatchet(ratchet_bridge=bridge)
        triggers = meta.check_triggers(ImprovementTarget.PROMPT_DISTILL)
        assert triggers == []

    def test_check_triggers_oscillation(self) -> None:
        bridge = MagicMock()
        statuses = ["keep", "discard"] * 5
        bridge.get_history.return_value = [
            RatchetIterationRecord(iteration=i, score=0.7, approved=s == "keep", best_score=0.7, best_iteration=0, duration_s=1.0, status=s, target=ImprovementTarget.PROMPT_DISTILL.value)
            for i, s in enumerate(statuses)
        ]
        meta = MetaRatchet(ratchet_bridge=bridge)
        triggers = meta.check_triggers(ImprovementTarget.PROMPT_DISTILL)
        assert "oscillation" in triggers

    def test_diagnose_stagnation_low_severity(self) -> None:
        bridge = MagicMock()
        bridge.get_history.return_value = []
        meta = MetaRatchet(ratchet_bridge=bridge)
        diag = meta.diagnose_stagnation(ImprovementTarget.PROMPT_DISTILL)
        assert diag.severity == "low"
        assert diag.diagnosis_type == "saturation"

    def test_diagnose_stagnation_high_severity(self) -> None:
        bridge = MagicMock()
        bridge.get_history.return_value = [
            RatchetIterationRecord(iteration=i, score=0.5, approved=False, best_score=0.5, best_iteration=None, duration_s=1.0, status="discard", target=ImprovementTarget.PROMPT_DISTILL.value)
            for i in range(5)
        ]
        meta = MetaRatchet(ratchet_bridge=bridge)
        diag = meta.diagnose_stagnation(ImprovementTarget.PROMPT_DISTILL)
        assert diag.severity == "high"
        assert diag.diagnosis_type == "consecutive_discards"

    def test_propose_protocol_change_low_severity_returns_none(self) -> None:
        meta = MetaRatchet()
        from maref.integration.percv.meta_ratchet import StagnationDiagnosis
        diag = StagnationDiagnosis(
            diagnosis_type="saturation", severity="low",
            details="nothing wrong",
        )
        change = meta.propose_protocol_change(diag)
        assert change is None

    def test_propose_protocol_change_consecutive_discards(self) -> None:
        bridge = MagicMock()
        meta = MetaRatchet(ratchet_bridge=bridge)
        from maref.integration.percv.meta_ratchet import StagnationDiagnosis
        diag = StagnationDiagnosis(
            diagnosis_type="consecutive_discards", severity="high",
            details="5 consecutive discards",
            affected_target=ImprovementTarget.PROMPT_DISTILL,
        )
        change = meta.propose_protocol_change(diag)
        assert change is not None
        assert change.config_key == "max_consecutive_discards"

    def test_sandbox_test_rejects_insufficient_rounds(self) -> None:
        meta = MetaRatchet()
        from maref.integration.percv.meta_ratchet import ProtocolChange
        change = ProtocolChange(
            config_key="max_consecutive_discards",
            old_value=5, new_value=4, rationale="test",
        )
        result = meta.sandbox_test(change, n_rounds=5)
        assert result.adopted is False
        assert result.improvement == 0

    def test_sandbox_test_adequate_rounds(self) -> None:
        meta = MetaRatchet()
        from maref.integration.percv.meta_ratchet import ProtocolChange
        change = ProtocolChange(
            config_key="max_consecutive_discards",
            old_value=5, new_value=4, rationale="test",
        )
        result = meta.sandbox_test(change, n_rounds=10)
        assert isinstance(result.adopted, bool)
        assert result.old_avg_score > 0
        assert result.new_avg_score > 0

    def test_sandbox_test_with_custom_evaluator(self) -> None:
        meta = MetaRatchet()
        from maref.integration.percv.meta_ratchet import ProtocolChange
        change = ProtocolChange(
            config_key="max_consecutive_discards",
            old_value=5, new_value=3, rationale="test",
        )
        call_count: list[int] = [0]
        def evaluator(val: object) -> float:
            call_count[0] += 1
            base = 0.9 if val == 3 else 0.6
            return base + (call_count[0] % 3) * 0.01
        result = meta.sandbox_test(change, n_rounds=10, evaluator_fn=evaluator)
        assert result.adopted is True
        assert result.new_avg_score > result.old_avg_score

    def test_sandbox_test_custom_evaluator_no_improvement(self) -> None:
        meta = MetaRatchet()
        from maref.integration.percv.meta_ratchet import ProtocolChange
        change = ProtocolChange(
            config_key="max_consecutive_discards",
            old_value=5, new_value=7, rationale="test",
        )
        call_count: list[int] = [0]
        def evaluator(val: object) -> float:
            call_count[0] += 1
            return 0.5 + (call_count[0] % 3) * 0.01
        result = meta.sandbox_test(change, n_rounds=10, evaluator_fn=evaluator)
        assert result.adopted is False

    def test_diagnosis_history_recorded(self) -> None:
        bridge = MagicMock()
        bridge.get_history.return_value = []
        meta = MetaRatchet(ratchet_bridge=bridge)
        meta.diagnose_stagnation(ImprovementTarget.PROMPT_DISTILL)
        assert len(meta.diagnosis_history) == 1

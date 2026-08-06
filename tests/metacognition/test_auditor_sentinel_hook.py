from __future__ import annotations

import time

from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.metacognition.auditor import MetaCognitiveAuditor
from maref.metacognition.models import SelfReflectionRecord
from maref.sentinel.event import AttackType, ObservationEvent, Severity


def _make_critical_event() -> ObservationEvent:
    return ObservationEvent(
        source="env_probe",
        severity=Severity.CRITICAL,
        subject="agent-evil",
        attack_type=AttackType.ENV_EXFIL,
        evidence={"leaked_keys": ["AWS_KEY", "DB_PASS"], "pid": 4242},
    )


class TestSentinelHook:
    def test_sentinel_hook_produces_record(self) -> None:
        auditor = MetaCognitiveAuditor()
        event = _make_critical_event()

        record = auditor.sentinel_hook(event)

        assert isinstance(record, SelfReflectionRecord)
        assert record.record_id
        assert record.agent_id == "agent-evil"
        assert "CRITICAL" in record.trigger_event
        assert "env_exfil" in record.trigger_event
        assert record.reflection_summary
        assert record.recommended_action

    def test_sentinel_hook_latency_under_5s(self) -> None:
        auditor = MetaCognitiveAuditor()
        event = _make_critical_event()

        start = time.time()
        record = auditor.sentinel_hook(event)
        elapsed = time.time() - start

        assert elapsed < 5.0
        assert isinstance(record, SelfReflectionRecord)

    def test_sentinel_hook_with_governance(self) -> None:
        sm = GovernanceStateMachine()
        cb = CircuitBreaker()
        auditor = MetaCognitiveAuditor(state_machine=sm, circuit_breaker=cb)
        event = _make_critical_event()

        record = auditor.sentinel_hook(event)

        assert isinstance(record, SelfReflectionRecord)
        assert record.recommended_action == "halt"

    def test_sentinel_hook_unknown_subject(self) -> None:
        auditor = MetaCognitiveAuditor()
        event = ObservationEvent(
            source="network_probe",
            severity=Severity.CRITICAL,
            subject="",
            attack_type=AttackType.PIXEL_TRACKING,
            evidence={},
        )

        record = auditor.sentinel_hook(event)

        assert record.agent_id == "unknown"
        assert "pixel_tracking" in record.trigger_event

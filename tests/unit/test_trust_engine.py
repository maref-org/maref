from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.identity.did_registry import AgentDID
from maref.identity.trust_engine import DEFAULT_WEIGHTS, TrustEngine


@pytest.fixture
def audit_path() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        return Path(f.name)


@pytest.fixture
def audit_logger(audit_path: Path) -> AuditLogger:
    return AuditLogger(audit_path)


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    return CircuitBreaker()


@pytest.fixture
def trust_engine(
    circuit_breaker: CircuitBreaker, audit_logger: AuditLogger
) -> TrustEngine:
    return TrustEngine(circuit_breaker=circuit_breaker, audit_logger=audit_logger)


class TestTrustScoreEvaluation:
    def test_evaluate_new_agent_default_score(
        self, trust_engine: TrustEngine
    ) -> None:
        did = AgentDID.generate()
        score = trust_engine.evaluate(did)
        assert 0.0 <= score.value <= 1.0
        assert score.confidence <= 1.0

    def test_record_event_improves_confidence(
        self, trust_engine: TrustEngine
    ) -> None:
        did = AgentDID.generate()
        score1 = trust_engine.evaluate(did)
        for _ in range(50):
            trust_engine.record_event(did, "good_action", {"delta": 0.01})
        score2 = trust_engine.evaluate(did)
        assert score2.confidence >= score1.confidence

    def test_multiple_failures_lower_score(
        self, trust_engine: TrustEngine, audit_logger: AuditLogger
    ) -> None:
        did = AgentDID.generate()
        for i in range(5):
            audit_logger.log(
                event_type="halt_event",
                actor=did.did_string,
                action="task_failed",
                details=f"Failure {i}",
                metadata={"agent_did": did.did_string},
            )
        score = trust_engine.evaluate(did)
        assert score.value < 0.8


class TestTrustToCircuitBreakerSync:
    def test_low_trust_sets_open(
        self, trust_engine: TrustEngine, circuit_breaker: CircuitBreaker, audit_logger: AuditLogger
    ) -> None:
        did = AgentDID.generate()
        for _ in range(20):
            audit_logger.log(
                event_type="halt_detected",
                actor=did.did_string,
                action="task_failed",
                details="Repeated failure",
                metadata={"agent_did": did.did_string},
            )
        for _ in range(20):
            circuit_breaker.check_depth(depth=10)
        state = trust_engine.sync_to_circuit_breaker(did)
        assert state in (BreakerState.OPEN, BreakerState.HALF_OPEN, BreakerState.CLOSED)

    def test_high_trust_sets_closed(
        self, trust_engine: TrustEngine, circuit_breaker: CircuitBreaker, audit_logger: AuditLogger
    ) -> None:
        did = AgentDID.generate()
        for _ in range(10):
            audit_logger.log(
                event_type="task_completed",
                actor=did.did_string,
                action="task_completed",
                details="Success",
                metadata={"agent_did": did.did_string},
            )
        circuit_breaker._state = BreakerState.CLOSED
        state = trust_engine.sync_to_circuit_breaker(did)
        assert state in (BreakerState.CLOSED, BreakerState.HALF_OPEN, BreakerState.OPEN)

    def test_sync_produces_audit_entry(
        self, trust_engine: TrustEngine, audit_logger: AuditLogger
    ) -> None:
        did = AgentDID.generate()
        before = len(audit_logger.read_all())
        trust_engine.sync_to_circuit_breaker(did)
        after = len(audit_logger.read_all())
        assert after > before


class TestTrustRecovery:
    def test_trust_can_recover(
        self, trust_engine: TrustEngine, audit_logger: AuditLogger
    ) -> None:
        did = AgentDID.generate()
        for _ in range(5):
            audit_logger.log(
                event_type="halt_detected",
                actor=did.did_string,
                action="task_failed",
                details="Bad behavior",
                metadata={"agent_did": did.did_string},
            )
        score_bad = trust_engine.evaluate(did)
        for _ in range(20):
            audit_logger.log(
                event_type="task_completed",
                actor=did.did_string,
                action="task_completed",
                details="Good behavior",
                metadata={"agent_did": did.did_string},
            )
        score_good = trust_engine.evaluate(did)
        assert score_good.value > score_bad.value


class TestTrustScoreStorage:
    def test_get_score_returns_last_evaluated(
        self, trust_engine: TrustEngine
    ) -> None:
        did = AgentDID.generate()
        assert trust_engine.get_score(did) is None
        score = trust_engine.evaluate(did)
        stored = trust_engine.get_score(did)
        assert stored is not None
        assert stored.value == score.value
        assert stored.confidence == score.confidence


class TestCustomWeights:
    def test_custom_weights_applied(
        self, circuit_breaker: CircuitBreaker, audit_logger: AuditLogger
    ) -> None:
        weights = {
            "behavior_consistency": 0.5,
            "cb_trigger_frequency": 0.2,
            "halt_avoidance": 0.1,
            "task_completion": 0.1,
            "vc_validity": 0.1,
        }
        engine = TrustEngine(circuit_breaker, audit_logger, weights=weights)
        did = AgentDID.generate()
        score = engine.evaluate(did)
        assert 0.0 <= score.value <= 1.0

    def test_invalid_weights_raises(
        self, circuit_breaker: CircuitBreaker, audit_logger: AuditLogger
    ) -> None:
        bad_weights = {"behavior_consistency": 0.3, "task_completion": 0.2}
        with pytest.raises(ValueError):
            TrustEngine(circuit_breaker, audit_logger, weights=bad_weights)


class TestDefaultWeights:
    def test_default_weights_sum_to_one(self) -> None:
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

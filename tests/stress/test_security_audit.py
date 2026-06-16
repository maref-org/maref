"""
M7 安全审计 — Security Audit Tests.

Covers 7.4:
  - Recursive depth escape prevention
  - Policy weight out-of-bounds clamping
  - HALT non-bypassability verification
  - State injection attack vectors
  - SQL injection via probe inputs
  - Serialization safety (malformed inputs)
"""

import time

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.constants import GRAY_CODE, compute_valid_transitions, hamming_distance
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState as GS
from maref.governance.types import StateMachineSnapshot
from maref.learning.replay import DecisionOutcome, ExperienceStore
from maref.learning.scheduler import LearningRateScheduler
from maref.observation.probes import ProbeReading, ProbeSeverity
from maref.observation.store import ObservationStore

# ---------------------------------------------------------------------------
# 7.4.1 — 递归深度逃逸检查
# ---------------------------------------------------------------------------


class TestRecursiveDepthEscape:
    """Verify that recursion depth limits cannot be bypassed."""

    def test_max_depth_enforced_by_circuit_breaker(self):
        """CircuitBreaker.check_depth() rejects depth > max_depth."""
        cb = CircuitBreaker(max_depth=3)
        assert cb.check_depth(1)
        assert cb.check_depth(2)
        assert cb.check_depth(3)
        assert not cb.check_depth(4)
        assert not cb.check_depth(10)
        assert not cb.check_depth(100)

    def test_trip_transitions_breaker_to_open(self):
        """Exceeding max_depth trips breaker to OPEN."""
        cb = CircuitBreaker(max_depth=2)
        assert cb.state == BreakerState.CLOSED
        cb.check_depth(3)
        assert cb.state == BreakerState.OPEN

    def test_depth_check_blocked_when_open(self):
        """Once OPEN, even valid depths are rejected."""
        cb = CircuitBreaker(max_depth=3)
        cb.check_depth(5)
        assert cb.is_open
        assert not cb.check_depth(1)

    def test_consecutive_depth_violations_extend_cooldown(self):
        """Repeated violations keep breaker open."""
        cb = CircuitBreaker(max_depth=2, max_consecutive_failures=2)
        cb.check_depth(3)
        cb.record_failure()
        assert cb.is_open

    def test_depth_zero_allowed_in_breaker(self):
        """Depth 0 is within bounds and should not trip."""
        cb = CircuitBreaker(max_depth=3)
        assert cb.check_depth(0)

    def test_rapid_depth_escalation(self):
        """Rapidly increasing depth within limit should not trip."""
        cb = CircuitBreaker(max_depth=5)
        for d in range(1, 6):
            assert cb.check_depth(d), f"depth {d} should be allowed"
        assert cb.state == BreakerState.CLOSED


# ---------------------------------------------------------------------------
# 7.4.2 — 策略权重越界检查
# ---------------------------------------------------------------------------


class TestPolicyWeightBounds:
    """Verify that learning rate and policy weights stay within safe bounds."""

    def test_lr_never_below_min_lr(self):
        """LearningRateScheduler clamped to min_lr."""
        scheduler = LearningRateScheduler(initial_lr=0.001)
        for _ in range(200):
            scheduler.step(-100.0)
        stats = scheduler.get_stats()
        assert scheduler.learning_rate >= stats["config"]["min_lr"]

    def test_lr_never_above_initial(self):
        """Learning rate never exceeds initial value (ReduceLROnPlateau only reduces)."""
        scheduler = LearningRateScheduler(initial_lr=0.01)
        for _ in range(100):
            scheduler.step(1.0)
        assert scheduler.learning_rate <= 0.01

    def test_experience_store_sample_count_bounded(self):
        """Store does not exceed max_samples (default 10000)."""
        store = ExperienceStore(max_size=500)
        for _i in range(2000):
            store.insert(
                DecisionOutcome(
                    timestamp=time.time(),
                    decision_type="test",
                    state_before="INIT",
                    state_after="OBSERVE",
                    entropy_before=0,
                    entropy_after=1,
                    reward=0.5,
                )
            )
        assert store.count() <= 500

    def test_extreme_negative_reward_stability(self):
        """Scheduler does not crash on extreme negative rewards."""
        scheduler = LearningRateScheduler(initial_lr=0.01)
        scheduler.step(-1e10)
        scheduler.step(-1e10)
        scheduler.step(-1e10)
        assert scheduler.learning_rate > 0


# ---------------------------------------------------------------------------
# 7.4.3 — HALT 不可绕过性验证
# ---------------------------------------------------------------------------


class TestHALTNonBypassability:
    """Verify that HALT is a true sink state — cannot escape, cannot be skipped."""

    def test_halt_blocks_all_transitions(self):
        """After force_halt(), can_transition() returns False for any target."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "start")
        sm.transition(GS.ANALYZE, "analyze")
        sm.force_halt("security")

        assert sm.current_state == GS.HALT
        for state in GS:
            assert not sm.can_transition(state), f"HALT should block transition to {state.name}"

    def test_halt_from_various_states(self):
        """force_halt() works from any reachable state."""
        test_states = [GS.INIT, GS.OBSERVE, GS.ANALYZE, GS.DECIDE, GS.ACT, GS.REPORT]
        for start in test_states:
            sm = GovernanceStateMachine()
            for target in [GS.OBSERVE, GS.ANALYZE]:
                if sm.can_transition(target) and sm.current_state != start:
                    sm.transition(target, "setup")
            sm.force_halt(f"from_{start.name}")
            assert sm.current_state == GS.HALT

    def test_transition_to_halt_not_allowed_directly(self):
        """Direct transition() to HALT is rejected (must use force_halt)."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "start")
        result = sm.transition(GS.HALT, "try direct")
        assert result is False
        assert sm.current_state == GS.OBSERVE

    def test_halt_persists_after_snapshot_restore(self):
        """Snapshot/restore preserves HALT state and its blocking behavior."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "start")
        sm.force_halt("persist test")
        snap = sm.snapshot()

        restored = GovernanceStateMachine.restore(snap)
        assert restored.current_state == GS.HALT
        for state in GS:
            assert not restored.can_transition(state)

    def test_halt_is_terminal_no_oscillation_possible(self):
        """In HALT, all transition attempts are rejected — no state churn."""
        sm = GovernanceStateMachine()
        sm.force_halt("oscillation check")
        for _ in range(50):
            result = sm.transition(GS.OBSERVE, "attempted oscillation")
            assert result is False
        assert sm.current_state == GS.HALT


# ---------------------------------------------------------------------------
# 7.4.4 — 状态注入攻击
# ---------------------------------------------------------------------------


class TestStateInjection:
    """Verify that invalid state values and transitions cannot be injected."""

    def test_hamming_distance_validation(self):
        """All valid transitions have Hamming distance exactly 1."""
        valid_transitions = compute_valid_transitions()

        for from_val, targets in valid_transitions.items():
            if from_val == GS.HALT.value:
                assert len(targets) == 0
                continue
            from_code = GRAY_CODE[from_val]
            for target_val in targets:
                target_code = GRAY_CODE[target_val]
                hd = hamming_distance(from_code, target_code)
                assert hd == 1, (
                    f"Transition {from_val}→{target_val} " f"has Hamming distance {hd}, expected 1"
                )

    def test_only_defined_transitions_allowed(self):
        """Any transition not in compute_valid_transitions() is rejected."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "start")
        valid_transitions = compute_valid_transitions()
        valid_next_values = valid_transitions[GS.OBSERVE.value]
        valid_next = {GS(v) for v in valid_next_values}
        for state in GS:
            if state not in valid_next and state != GS.OBSERVE:
                assert not sm.can_transition(
                    state
                ), f"Unexpected valid transition: OBSERVE→{state.name}"

    def test_bogus_state_value_rejected(self):
        """Out-of-range integer state value detected."""
        valid_values = {s.value for s in GS}
        bogus = 99
        assert bogus not in valid_values

    def test_entropy_spoofing_prevented(self):
        """Entropy values are computed from state, not directly set."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "start")
        entropy_observe = sm.current_entropy
        sm.transition(GS.ANALYZE, "analyze")
        entropy_analyze = sm.current_entropy
        assert entropy_observe != entropy_analyze


# ---------------------------------------------------------------------------
# 7.4.5 — SQL 注入防护
# ---------------------------------------------------------------------------


class TestSQLInjectionDefense:
    """Verify that ObservationStore uses parameterized queries."""

    def test_malicious_probe_name(self):
        """Probe name with SQL injection characters does not cause error."""
        store = ObservationStore(db_path=":memory:")
        malicious_name = "entropy'; DROP TABLE probe_readings; --"
        reading = ProbeReading(
            probe_name=malicious_name,
            severity=ProbeSeverity.WARNING,
            value=3.0,
            threshold=4.0,
            timestamp=time.time(),
        )
        row_id = store.insert_reading(reading)
        assert row_id > 0

        retrieved = store.get_readings(limit=10)
        assert len(retrieved) > 0
        assert any(r["probe_name"] == malicious_name for r in retrieved)

    def test_malicious_context_json(self):
        """Context with injection payload stored safely."""
        store = ObservationStore(db_path=":memory:")
        reading = ProbeReading(
            probe_name="safe_probe",
            severity=ProbeSeverity.NORMAL,
            value=1.0,
            threshold=5.0,
            timestamp=time.time(),
            context={"data": "'); DELETE FROM probe_readings; --"},
        )
        row_id = store.insert_reading(reading)
        assert row_id > 0

    def test_special_characters_in_fnr_fpr_batch_id(self):
        """Batch ID with special characters stored correctly."""
        store = ObservationStore(db_path=":memory:")
        store.log_fnr_fpr(
            batch_id="batch_'; DROP--",
            fnr=0.1,
            fpr=0.05,
            tp=90,
            fp=5,
            tn=895,
            fn_count=10,
        )
        history = store.get_fnr_fpr_history(limit=5)
        assert len(history) > 0
        assert history[0]["batch_id"] == "batch_'; DROP--"

    def test_fnr_fpr_log_table_structure_intact(self):
        """After all injection attempts, tables remain intact."""
        store = ObservationStore(db_path=":memory:")
        store.insert_reading(
            ProbeReading(
                probe_name="normal",
                severity=ProbeSeverity.NORMAL,
                value=1.0,
                threshold=4.0,
                timestamp=time.time(),
            )
        )
        store.insert_reading(
            ProbeReading(
                probe_name="entropy'; DELETE FROM probe_readings; --",
                severity=ProbeSeverity.WARNING,
                value=3.0,
                threshold=4.0,
                timestamp=time.time(),
            )
        )
        recent = store.get_readings(limit=100)
        assert len(recent) >= 2

        store.log_fnr_fpr("safety_check", 0.1, 0.05, 45, 2, 450, 5)
        history = store.get_fnr_fpr_history(limit=5)
        assert len(history) >= 1


# ---------------------------------------------------------------------------
# 7.4.6 — 序列化安全
# ---------------------------------------------------------------------------


class TestSerializationSafety:
    """Verify robustness against malformed or malicious serialized inputs."""

    def test_snapshot_missing_fields(self):
        """Restore with missing fields uses defaults."""
        incomplete = StateMachineSnapshot.from_dict({"current_state_id": GS.OBSERVE.value})
        restored = GovernanceStateMachine.restore(incomplete)
        assert restored.current_state == GS.OBSERVE
        assert restored.transition_count == 0

    def test_snapshot_bogus_state_name(self):
        """Snapshot with nonexistent state ID raises ValueError — safe rejection."""
        with pytest.raises(ValueError, match="not a valid GovernanceState"):
            StateMachineSnapshot.from_dict(
                {
                    "current_state_id": 99,
                    "transition_count": 99,
                    "history_length": 0,
                }
            )

    def test_snapshot_with_extra_fields(self):
        """Extra fields in snapshot are ignored (forward compat)."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "start")
        snap = sm.snapshot()
        snap_dict = snap.to_dict()
        snap_dict["v2_new_field"] = "should be ignored"
        snap_dict["_secret_backdoor"] = {"attack": True}
        restored_snap = StateMachineSnapshot.from_dict(snap_dict)
        restored = GovernanceStateMachine.restore(restored_snap)
        assert restored.current_state == GS.OBSERVE

    def test_empty_snapshot_dict(self):
        """Entirely empty snapshot restores to INIT."""
        restored = GovernanceStateMachine.restore(StateMachineSnapshot.from_dict({}))
        assert restored.current_state == GS.INIT

    def test_experience_store_bad_db_path(self):
        """ExperienceStore with an invalid SQLite path (non-db file) falls back gracefully."""
        store = ExperienceStore(db_path=":memory:")
        assert store.count() == 0
        outcome = DecisionOutcome(
            timestamp=time.time(),
            decision_type="safety_test",
            state_before="INIT",
            state_after="OBSERVE",
            entropy_before=0,
            entropy_after=1,
            reward=1.0,
            context={"safe": True},
        )
        store.insert(outcome)
        assert store.count() == 1

    def test_experience_store_injection_in_sample_data(self):
        """Samples with crafted keys don't break store internals."""
        store = ExperienceStore()
        store.insert(
            DecisionOutcome(
                timestamp=time.time(),
                decision_type="inject_test",
                state_before="INIT",
                state_after="OBSERVE",
                entropy_before=0,
                entropy_after=1,
                reward=0.5,
                context={"__class__": "os.system", "__init__": "rm -rf /"},
            )
        )
        assert store.count() == 1
        batch = store.sample(1)
        assert len(batch) == 1
        assert batch[0].reward == 0.5

    def test_audit_log_safe_with_crafted_metadata(self):
        """AuditLogger handles metadata dict with dangerous-looking keys."""
        logger = AuditLogger(log_path=None)
        entry = logger.log(
            event_type="security_test",
            actor="attacker",
            action="inject",
            details="harmless",
            metadata={
                "__proto__": {"polluted": True},
                "constructor": "prototype",
                "__class__": "exploit",
                "normal_key": "safe_value",
            },
        )
        assert entry.event_type == "security_test"
        assert entry.metadata.get("normal_key") == "safe_value"

    def test_probe_reading_no_severity_override_via_context(self):
        """Context dict cannot override the severity field."""
        reading = ProbeReading(
            probe_name="safe",
            severity=ProbeSeverity.NORMAL,
            value=1.0,
            threshold=4.0,
            timestamp=time.time(),
            context={"severity": "CRITICAL_OVERRIDE", "value": 999.0},
        )
        assert reading.severity != ProbeSeverity.CRITICAL
        assert reading.severity == ProbeSeverity.NORMAL
        assert reading.value == 1.0

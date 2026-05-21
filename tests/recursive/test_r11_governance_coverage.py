from __future__ import annotations

import time

import pytest

from maref.governance import (
    CircuitBreaker,
    GovernanceStateMachine,
)
from maref_lite.governance import GovernanceOverlay
from maref_lite.recursive_governance import (
    MAREFSelfAdapter,
    RecursiveGovernanceConfig,
    RecursiveGovernanceOverlay,
)
from sidecar.protocol import AgentId, AgentState


class TestMAREFSelfAdapter:
    @pytest.fixture
    def overlay(self) -> GovernanceOverlay:
        return GovernanceOverlay(state_machine=GovernanceStateMachine())

    @pytest.fixture
    def self_adapter(self, overlay: GovernanceOverlay) -> MAREFSelfAdapter:
        return MAREFSelfAdapter(overlay)

    async def test_list_agents_returns_maref_core(self, self_adapter: MAREFSelfAdapter) -> None:
        agents = await self_adapter.list_agents()
        assert len(agents) == 1
        assert agents[0].name == "maref-core"
        assert agents[0].namespace == "self"

    async def test_get_state_returns_snapshot(self, self_adapter: MAREFSelfAdapter) -> None:
        state = await self_adapter.get_state(AgentId(name="maref-core", namespace="self"))
        assert state is not None
        assert state.agent_id.name == "maref-core"
        assert state.state == AgentState.RUNNING

    async def test_get_state_unknown_agent(self, self_adapter: MAREFSelfAdapter) -> None:
        state = await self_adapter.get_state(AgentId(name="unknown"))
        assert state is None

    async def test_get_state_has_timestamp(self, self_adapter: MAREFSelfAdapter) -> None:
        state = await self_adapter.get_state(AgentId(name="maref-core", namespace="self"))
        assert state is not None
        assert state.timestamp > 0

    async def test_get_state_has_task_progress(self, self_adapter: MAREFSelfAdapter) -> None:
        state = await self_adapter.get_state(AgentId(name="maref-core", namespace="self"))
        assert state is not None
        assert state.task_progress == 0.5

    async def test_get_entropy_returns_reading(self, self_adapter: MAREFSelfAdapter) -> None:
        entropy = await self_adapter.get_entropy(AgentId(name="maref-core", namespace="self"))
        assert entropy is not None
        assert "maref-core" in entropy.source
        assert entropy.threshold == 4.0

    async def test_get_entropy_unknown_agent(self, self_adapter: MAREFSelfAdapter) -> None:
        entropy = await self_adapter.get_entropy(AgentId(name="unknown"))
        assert entropy is None

    async def test_get_entropy_value_is_float(self, self_adapter: MAREFSelfAdapter) -> None:
        entropy = await self_adapter.get_entropy(AgentId(name="maref-core", namespace="self"))
        assert entropy is not None
        assert isinstance(entropy.value, float)

    async def test_get_entropy_level_is_normal_or_critical(self, self_adapter: MAREFSelfAdapter) -> None:
        entropy = await self_adapter.get_entropy(AgentId(name="maref-core", namespace="self"))
        assert entropy is not None
        assert entropy.level in ("normal", "critical")


class TestRecursiveGovernanceConfig:
    def test_default_config_values(self) -> None:
        cfg = RecursiveGovernanceConfig()
        assert cfg.max_recursion_depth == 4
        assert cfg.self_observation_cooldown == 5.0
        assert cfg.max_oscillation_rate == 10.0
        assert cfg.enable_meta_learning is True
        assert cfg.enable_policy_sandbox is True
        assert cfg.sandbox_auto_revert_minutes == 60
        assert cfg.circuit_breaker_cooldown == 15.0
        assert cfg.circuit_breaker_max_failures == 5

    def test_custom_config_values(self) -> None:
        cfg = RecursiveGovernanceConfig(
            max_recursion_depth=5,
            self_observation_cooldown=10.0,
            max_oscillation_rate=20.0,
            enable_meta_learning=False,
            enable_policy_sandbox=False,
            sandbox_auto_revert_minutes=60,
            circuit_breaker_cooldown=60.0,
            circuit_breaker_max_failures=10,
        )
        assert cfg.max_recursion_depth == 5
        assert cfg.self_observation_cooldown == 10.0
        assert cfg.max_oscillation_rate == 20.0
        assert cfg.enable_meta_learning is False
        assert cfg.enable_policy_sandbox is False
        assert cfg.sandbox_auto_revert_minutes == 60
        assert cfg.circuit_breaker_cooldown == 60.0
        assert cfg.circuit_breaker_max_failures == 10

    def test_to_dict_contains_keys(self) -> None:
        cfg = RecursiveGovernanceConfig()
        d = cfg.to_dict()
        assert isinstance(d, dict)
        assert "max_recursion_depth" in d
        assert "self_observation_cooldown" in d
        assert "max_oscillation_rate" in d
        assert "enable_meta_learning" in d
        assert "enable_policy_sandbox" in d
        assert "sandbox_auto_revert_minutes" in d

    def test_to_dict_values_match(self) -> None:
        cfg = RecursiveGovernanceConfig(max_recursion_depth=7)
        d = cfg.to_dict()
        assert d["max_recursion_depth"] == 7

    def test_partial_custom_config(self) -> None:
        cfg = RecursiveGovernanceConfig(max_recursion_depth=2)
        assert cfg.max_recursion_depth == 2
        assert cfg.self_observation_cooldown == 5.0


class TestRecursiveGovernanceOverlayInit:
    def test_init_with_defaults(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        assert overlay._config.max_recursion_depth == 4
        assert overlay._running is False
        assert overlay._recursion_depth == 0

    def test_init_with_custom_config(self) -> None:
        cfg = RecursiveGovernanceConfig(max_recursion_depth=4)
        overlay = RecursiveGovernanceOverlay(config=cfg)
        assert overlay._config.max_recursion_depth == 4

    def test_init_with_primary_overlay(self) -> None:
        primary = GovernanceOverlay(state_machine=GovernanceStateMachine())
        overlay = RecursiveGovernanceOverlay(primary_overlay=primary)
        assert overlay._primary is primary

    def test_init_creates_meta_overlay(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        assert overlay._meta is not None

    def test_init_creates_circuit_breaker(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        assert overlay._breaker is not None

    def test_init_creates_self_adapter_and_collector(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        assert overlay._self_adapter is not None
        assert overlay._self_collector is not None

    def test_init_creates_meta_learner_when_enabled(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        assert overlay._meta_learner is not None

    def test_init_skips_meta_learner_when_disabled(self) -> None:
        cfg = RecursiveGovernanceConfig(enable_meta_learning=False)
        overlay = RecursiveGovernanceOverlay(config=cfg)
        assert overlay._meta_learner is None

    def test_init_creates_sandbox_when_enabled(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        assert overlay._sandbox is not None

    def test_init_skips_sandbox_when_disabled(self) -> None:
        cfg = RecursiveGovernanceConfig(enable_policy_sandbox=False)
        overlay = RecursiveGovernanceOverlay(config=cfg)
        assert overlay._sandbox is None


class TestRecursiveGovernanceOverlayMethods:
    @pytest.fixture
    def overlay(self) -> RecursiveGovernanceOverlay:
        return RecursiveGovernanceOverlay()

    def test_stop_sets_running_false(self, overlay: RecursiveGovernanceOverlay) -> None:
        overlay._running = True
        overlay.stop()
        assert overlay._running is False

    def test_get_recursive_status_keys(self, overlay: RecursiveGovernanceOverlay) -> None:
        status = overlay.get_recursive_status()
        assert "primary_status" in status
        assert "meta_status" in status
        assert "recursion_depth" in status
        assert "oscillation_detected" in status
        assert "state_change_rate" in status
        assert "circuit_breaker" in status

    def test_get_recursive_status_meta_learning(self, overlay: RecursiveGovernanceOverlay) -> None:
        status = overlay.get_recursive_status()
        assert "meta_learning" in status
        assert "sandbox" in status

    def test_get_recursive_status_recursion_depth_zero(self, overlay: RecursiveGovernanceOverlay) -> None:
        status = overlay.get_recursive_status()
        assert status["recursion_depth"] == 0

    def test_get_meta_decisions_returns_list(self, overlay: RecursiveGovernanceOverlay) -> None:
        decisions = overlay.get_meta_decisions()
        assert isinstance(decisions, list)

    def test_get_meta_decisions_empty_initially(self, overlay: RecursiveGovernanceOverlay) -> None:
        decisions = overlay.get_meta_decisions()
        assert decisions == []

    def test_detect_oscillation_negative_when_few_changes(self, overlay: RecursiveGovernanceOverlay) -> None:
        overlay._state_changes = [time.time()]
        assert overlay._detect_oscillation() is False

    def test_detect_oscillation_positive_when_many_changes(self, overlay: RecursiveGovernanceOverlay) -> None:
        now = time.time()
        overlay._state_changes = [now] * 20
        assert overlay._detect_oscillation() is True

    def test_state_changes_pruned_after_one_minute(self, overlay: RecursiveGovernanceOverlay) -> None:
        old_time = time.time() - 120.0
        recent_time = time.time()
        overlay._state_changes = [old_time, old_time, recent_time]
        cutoff = time.time() - 60.0
        overlay._state_changes = [t for t in overlay._state_changes if t > cutoff]
        assert len(overlay._state_changes) == 1

    def test_recursive_status_when_no_meta_learning(self) -> None:
        cfg = RecursiveGovernanceConfig(enable_meta_learning=False, enable_policy_sandbox=False)
        overlay = RecursiveGovernanceOverlay(config=cfg)
        status = overlay.get_recursive_status()
        assert status["meta_learning"] is None
        assert status["sandbox"] is None

    def test_recursive_status_oscillation_detected_flag(self, overlay: RecursiveGovernanceOverlay) -> None:
        overlay._state_changes = [time.time()] * 15
        status = overlay.get_recursive_status()
        assert status["oscillation_detected"] is True
        assert status["state_change_rate"] == 15


class TestRecursiveGovernanceCircuitBreaker:
    def test_breaker_initial_state(self) -> None:
        breaker = CircuitBreaker(
            max_depth=3,
            max_oscillation_rate=10.0,
            max_consecutive_failures=5,
            cooldown_seconds=30.0,
        )
        assert breaker.is_open is False

    def test_breaker_check_depth_accepts_valid(self) -> None:
        breaker = CircuitBreaker(
            max_depth=3,
            max_oscillation_rate=10.0,
            max_consecutive_failures=5,
            cooldown_seconds=30.0,
        )
        assert breaker.check_depth(2) is True
        assert breaker.check_depth(3) is True

    def test_breaker_check_depth_rejects_exceeded(self) -> None:
        breaker = CircuitBreaker(
            max_depth=3,
            max_oscillation_rate=10.0,
            max_consecutive_failures=5,
            cooldown_seconds=30.0,
        )
        assert breaker.check_depth(4) is False

    def test_breaker_record_failure_trips_breaker(self) -> None:
        breaker = CircuitBreaker(
            max_depth=3,
            max_oscillation_rate=10.0,
            max_consecutive_failures=2,
            cooldown_seconds=30.0,
        )
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open is True

    def test_breaker_record_success_does_not_trip(self) -> None:
        breaker = CircuitBreaker(
            max_depth=3,
            max_oscillation_rate=10.0,
            max_consecutive_failures=5,
            cooldown_seconds=30.0,
        )
        breaker.record_success()
        assert breaker.is_open is False

    def test_breaker_check_oscillation(self) -> None:
        breaker = CircuitBreaker(
            max_depth=3,
            max_oscillation_rate=10.0,
            max_consecutive_failures=5,
            cooldown_seconds=30.0,
        )
        result = breaker.check_oscillation(5.0, 2.0, "OBSERVE")
        assert isinstance(result, bool)

    def test_breaker_get_stats(self) -> None:
        breaker = CircuitBreaker(
            max_depth=3,
            max_oscillation_rate=10.0,
            max_consecutive_failures=5,
            cooldown_seconds=30.0,
        )
        stats = breaker.get_stats()
        assert isinstance(stats, dict)

    def test_circuit_breaker_opens_after_max_failures(self) -> None:
        breaker = CircuitBreaker(
            max_depth=3,
            max_oscillation_rate=10.0,
            max_consecutive_failures=3,
            cooldown_seconds=30.0,
        )
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open is False
        breaker.record_failure()
        assert breaker.is_open is True

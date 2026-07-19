"""
MAREF Multi-Agent Evolution Engine

Extends the recursive evolution engine with multi-agent collaborative
governance optimization. Each governance agent role operates independently
with role-specific rewards, policy updates, and safety constraints.

Key components:
- MultiAgentEvolutionConfig: Configuration for multi-agent evolution
- MultiAgentEvolutionEngine: Main orchestrator for multi-agent evolution
- MultiAgentEvolutionResult: Result data structure
- ConstitutionGuard: Safety layer enforcing governance invariants

Architecture:
  MultiAgentEvolutionEngine
  ├── AgentRegistry (roles & groups)
  ├── MultiGranularityRewardAssembler (role/round/cycle rewards)
  ├── GroupPolicyOptimizer per group (PPO-style updates)
  ├── ConstitutionGuard (safety invariants)
  └── ExperienceStore (persistent experience buffer)

Backward compatibility:
  If no multi-agent configuration is provided, the engine falls back
  to single-strategy mode (equivalent to RecursiveEvolutionEngine).
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any

from maref.evolution.agents import (
    GovernanceAgentConfig,
    ShareGroup,
)
from maref.evolution.constitution_guard import (
    ConstitutionGuard,
)
from maref.evolution.engine import (
    CANONICAL_PATH,
    ROUND_SEED,
    EvolutionConfig,
)
from maref.evolution.metrics import (
    CycleResult,
    CycleSpec,
    EvolutionMetrics,
    EvolutionResult,
)
from maref.evolution.registry import AgentRegistry
from maref.governance import (
    BreakerState,
    CircuitBreaker,
    GovernanceState,
    GovernanceStateMachine,
)
from maref.learning.group_optimizer import GroupPolicyOptimizer, OptimizerConfig
from maref.learning.replay import DecisionOutcome, ExperienceStore
from maref.learning.rewards import (
    MultiGranularityRewardAssembler,
    create_role_reward_fn,
)


@dataclass
class MultiAgentEvolutionConfig:
    """Configuration for multi-agent evolution."""

    # Base evolution config
    base_config: EvolutionConfig = field(default_factory=EvolutionConfig)

    # Multi-agent specific
    agent_configs: list[GovernanceAgentConfig] = field(default_factory=list)
    optimizer_config: OptimizerConfig = field(default_factory=OptimizerConfig)

    # Reward assembly
    reward_update_interval: int = 5
    """How often (in rounds) to compute and apply multi-granularity rewards."""

    # Fallback behavior
    fallback_to_single_strategy: bool = True
    """If no agents are configured, fall back to single-strategy mode."""

    # Constitution guard
    constitution_guard_enabled: bool = True
    """Enable constitution safety checks on all policy updates."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_config": self.base_config.to_dict(),
            "agent_configs": [c.to_dict() for c in self.agent_configs],
            "optimizer_config": self.optimizer_config.to_dict(),
            "reward_update_interval": self.reward_update_interval,
            "fallback_to_single_strategy": self.fallback_to_single_strategy,
            "constitution_guard_enabled": self.constitution_guard_enabled,
        }

    @classmethod
    def with_default_agents(cls, **kwargs) -> MultiAgentEvolutionConfig:
        """Create config with standard 5-role governance agents."""
        registry = AgentRegistry()
        config = cls(**kwargs)
        config.agent_configs = registry.get_default_agent_configs()
        return config


@dataclass
class MultiAgentRoundSnapshot:
    """Snapshot of a single multi-agent evolution round."""

    round_num: int
    cycle_id: str
    role_rewards: list[dict[str, Any]] = field(default_factory=list)
    round_reward: float = 0.0
    policy_updates: dict[str, dict[str, float]] = field(default_factory=dict)
    constitution_violations: int = 0
    # Inherit standard fields
    fnr: float = 0.0
    fpr: float = 0.0
    final_entropy: int = 0
    transition_count: int = 0
    failed_transitions: int = 0
    halt_reason: str = ""
    final_state: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_num": self.round_num,
            "cycle_id": self.cycle_id,
            "role_rewards": self.role_rewards,
            "round_reward": self.round_reward,
            "policy_updates": self.policy_updates,
            "constitution_violations": self.constitution_violations,
            "fnr": self.fnr,
            "fpr": self.fpr,
            "final_entropy": self.final_entropy,
            "transition_count": self.transition_count,
        }


@dataclass
class MultiAgentEvolutionResult:
    """Result of a multi-agent evolution run."""

    evolution_result: EvolutionResult
    agent_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    group_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    reward_history: list[float] = field(default_factory=list)
    constitution_violations_total: int = 0

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "MAREF Multi-Agent Evolution — Final Result",
            f"Stop reason: {self.evolution_result.stop_reason}",
            f"Total rounds: {self.evolution_result.total_rounds}",
            f"Overall: {'PASSED' if self.evolution_result.all_passed else 'FAILED'}",
            f"Agents: {len(self.agent_stats)}",
            f"Groups: {len(self.group_stats)}",
            f"Constitution violations: {self.constitution_violations_total}",
            "=" * 60,
        ]
        for agent_id, stats in self.agent_stats.items():
            lines.append(f"  {agent_id}: reward={stats.get('total_reward', 0):.3f}")
        return "\n".join(lines)


class MultiAgentEvolutionEngine:
    """
    Orchestrates multi-agent collaborative governance evolution.

    Responsibilities:
    1. Register and manage governance agent roles
    2. Compute multi-granularity rewards (role → round → cycle)
    3. Execute PPO-style policy updates per agent group
    4. Enforce constitution invariants on all updates
    5. Maintain persistent experience buffer with role-level tracking

    Backward compatibility:
      If no agent_configs are provided and fallback_to_single_strategy=True,
      the engine operates in single-strategy mode, equivalent to the
      RecursiveEvolutionEngine.

    Usage:
        config = MultiAgentEvolutionConfig.with_default_agents()
        engine = MultiAgentEvolutionEngine(config)
        result = await engine.run()
    """

    def __init__(
        self,
        config: MultiAgentEvolutionConfig | None = None,
        seed: int | None = None,
    ) -> None:
        self._config = config or MultiAgentEvolutionConfig()
        self._rng = random.Random(seed if seed is not None else ROUND_SEED)
        self._running = False
        self._total_rounds = 0

        # Core components
        self._registry = AgentRegistry()
        self._reward_assembler = MultiGranularityRewardAssembler()
        self._experience_store = ExperienceStore(":memory:")
        self._constitution_guard = ConstitutionGuard(
            enabled=self._config.constitution_guard_enabled,
        )

        # Groups and optimizers
        self._groups: dict[str, ShareGroup] = {}
        self._optimizers: dict[str, GroupPolicyOptimizer] = {}

        # Safety components
        self._breaker = CircuitBreaker(
            max_depth=3,
            max_consecutive_failures=5,
            cooldown_seconds=30.0,
        )

        # Register agents
        self._initialize_agents()

    def _initialize_agents(self) -> None:
        """Register agents and create groups/optimizers."""
        if not self._config.agent_configs:
            return

        for agent_config in self._config.agent_configs:
            agent = self._registry.register_agent(agent_config)

            # Register with ConstitutionGuard (RL-001)
            self._constitution_guard.register_agent(agent.agent_id)

            reward_fn = create_role_reward_fn(
                agent.agent_id,
                agent.role,
                weight=agent.reward_weight,
            )
            self._reward_assembler.register_reward_fn(reward_fn)

        # Create groups and optimizers
        for group in self._registry.list_groups():
            self._groups[group.group_id] = group
            self._optimizers[group.group_id] = GroupPolicyOptimizer(
                group,
                config=self._config.optimizer_config,
            )

    @property
    def is_multi_agent(self) -> bool:
        return self._registry.agent_count > 0

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    async def run(self) -> MultiAgentEvolutionResult:
        self._running = True
        cycle_results: list[CycleResult] = []
        stop_reason = "unknown"
        self._total_rounds = 0

        cycle_order = ["c1", "c2", "c3"]
        base = self._config.base_config

        for cycle_id in cycle_order:
            if base.dry_run:
                cycle_spec = CycleSpec(
                    name="DRY RUN",
                    rounds=1,
                    description="Single-round pipeline validation",
                )
            else:
                cycle_spec = base.cycles.get(
                    cycle_id,
                    CycleSpec(name=cycle_id, rounds=50, description=""),
                )

            cycle_metrics = EvolutionMetrics()
            total_rounds = 1 if base.dry_run else cycle_spec.rounds

            for round_num in range(total_rounds):
                if not self._running:
                    stop_reason = "manual_stop"
                    break
                if self._total_rounds >= base.max_total_rounds:
                    stop_reason = "timeout"
                    break

                try:
                    snapshot = await self._run_one_round(cycle_id, round_num, cycle_spec)
                    self._collect_round_metrics(cycle_metrics, snapshot)

                    if (
                        self.is_multi_agent
                        and round_num > 0
                        and round_num % self._config.reward_update_interval == 0
                    ):
                        await self._run_policy_update_cycle(
                            cycle_id, round_num, cycle_metrics, snapshot
                        )

                    stop = self._check_stop_conditions(cycle_metrics, cycle_id)
                    if stop:
                        stop_reason = stop
                        break

                except asyncio.CancelledError:
                    stop_reason = "manual_stop"
                    break

                self._total_rounds += 1

            acceptance = cycle_metrics.assess_acceptance(base.acceptance_criteria, cycle_id)

            actual_rounds = self._total_rounds
            cycle_result = CycleResult(
                cycle_id=cycle_id,
                name=cycle_spec.name,
                rounds_completed=min(actual_rounds, total_rounds),
                rounds_total=total_rounds,
                metrics=cycle_metrics,
                acceptance=acceptance,
                passed=all(acceptance.values()) if acceptance else True,
            )
            cycle_results.append(cycle_result)

            if base.dry_run:
                stop_reason = "dry_run_complete"
                break

            if stop_reason != "unknown":
                break

        if stop_reason == "unknown":
            stop_reason = "normal_completion"

        evolution_result = EvolutionResult(
            cycles=cycle_results,
            stop_reason=stop_reason,
            total_rounds=self._total_rounds,
            all_passed=all(c.passed for c in cycle_results),
        )

        agent_stats = {agent.agent_id: agent.get_stats() for agent in self._registry.list_agents()}
        group_stats = {gid: group.get_group_stats() for gid, group in self._groups.items()}
        reward_history = self._reward_assembler.get_cycle_history()

        return MultiAgentEvolutionResult(
            evolution_result=evolution_result,
            agent_stats=agent_stats,
            group_stats=group_stats,
            reward_history=reward_history,
            constitution_violations_total=self._constitution_guard.violation_count,
        )

    async def _run_one_round(
        self,
        cycle_id: str,
        round_num: int,
        cycle_spec: CycleSpec,
    ) -> MultiAgentRoundSnapshot:
        """Execute a single evolution round with multi-agent support."""
        sm = GovernanceStateMachine()
        failed_transitions = 0
        halt_reason = ""

        for target in CANONICAL_PATH:
            if not self._running:
                break

            if sm.can_transition(target):
                sm.transition(target, f"{cycle_id}_r{round_num}")
            else:
                failed_transitions += 1
                if target == GovernanceState.HALT:
                    sm.force_halt("normal_completion")
                    halt_reason = "normal_completion"
                    break

            await asyncio.sleep(0.0001)

        if sm.current_state == GovernanceState.HALT:
            halt_reason = halt_reason or "normal_path_completion"
        elif sm.current_state != GovernanceState.HALT:
            sm.force_halt("round_end")
            halt_reason = "round_end_force"

        fnr, fpr = self._collect_detector_metrics(round_num)

        snapshot = MultiAgentRoundSnapshot(
            round_num=round_num,
            cycle_id=cycle_id,
            fnr=fnr,
            fpr=fpr,
            final_entropy=sm.current_entropy,
            transition_count=sm.transition_count,
            failed_transitions=failed_transitions,
            halt_reason=halt_reason,
            final_state=sm.current_state.name,
        )

        if self.is_multi_agent:
            self._compute_and_store_rewards(snapshot)

        return snapshot

    def _collect_detector_metrics(self, round_num: int) -> tuple[float, float]:
        if self._config.base_config.metrics_mode == "real":
            try:
                from maref.evolution.real_metrics import RealMetricsCollector
                collector = RealMetricsCollector()
                metrics = collector.collect_incremental()
                return metrics.fnr, metrics.fpr
            except Exception:
                pass
        return self._simulate_detector_metrics(round_num)

    def _simulate_detector_metrics(self, round_num: int) -> tuple[float, float]:
        base_fnr = 0.10 + self._rng.uniform(-0.05, 0.03)
        base_fpr = 0.06 + self._rng.uniform(-0.03, 0.02)
        noise_fnr = self._rng.gauss(0, 0.02)
        noise_fpr = self._rng.gauss(0, 0.01)
        fnr = max(0.0, min(0.30, base_fnr + noise_fnr))
        fpr = max(0.0, min(0.20, base_fpr + noise_fpr))
        return fnr, fpr

    def _compute_and_store_rewards(
        self,
        snapshot: MultiAgentRoundSnapshot,
    ) -> None:
        """Compute role-level rewards and store as experiences."""
        round_data = {
            "fnr": snapshot.fnr,
            "fpr": snapshot.fpr,
            "final_entropy": snapshot.final_entropy,
            "transition_count": snapshot.transition_count,
        }

        summary = self._reward_assembler.assemble_round_rewards(
            round_num=snapshot.round_num,
            round_snapshot=round_data,
        )

        snapshot.round_reward = summary.round_reward
        snapshot.role_rewards = [r.to_dict() for r in summary.role_rewards]

        for role_reward in summary.role_rewards:
            outcome = DecisionOutcome(
                timestamp=time.time(),
                decision_type="multi_agent_evolution_round",
                state_before="ANALYZE",
                state_after="STABILIZE",
                entropy_before=2,
                entropy_after=1,
                reward=role_reward.role_reward,
                role_id=role_reward.agent_id,
                context=role_reward.context,
            )
            self._experience_store.insert(outcome)

    async def _run_policy_update_cycle(
        self,
        cycle_id: str,
        round_num: int,
        cycle_metrics: EvolutionMetrics,
        snapshot: MultiAgentRoundSnapshot,
    ) -> None:
        """Execute policy update for all agent groups."""
        if not self._optimizers:
            return

        for group_id, optimizer in self._optimizers.items():
            group_agents = self._registry.get_agents_by_group(group_id)
            if not group_agents:
                continue

            rewards = [agent.total_reward for agent in group_agents]
            baselines = [agent.total_reward * 0.8 for agent in group_agents]

            if not rewards:
                continue

            result = optimizer.policy_gradient_step(
                rewards=rewards,
                baselines=baselines,
            )

            for agent in group_agents:
                if agent.agent_id in result.agent_updates:
                    updated = result.agent_updates[agent.agent_id]
                    validation = self._constitution_guard.validate_action(
                        agent.agent_id,
                        updated,
                    )
                    if validation.allowed:
                        pass
                    else:
                        constrained = self._constitution_guard.constrain_weights(updated)
                        snapshot.policy_updates[agent.agent_id] = constrained
                        snapshot.constitution_violations += len(validation.violations)

    def _collect_round_metrics(
        self,
        metrics: EvolutionMetrics,
        snapshot: MultiAgentRoundSnapshot,
    ) -> None:
        metrics.fnr_series.append(snapshot.fnr)
        metrics.fpr_series.append(snapshot.fpr)
        metrics.entropy_series.append(snapshot.final_entropy)
        metrics.transition_count_series.append(snapshot.transition_count)
        metrics.halt_reasons.append(snapshot.halt_reason)

        if self.is_multi_agent and self._registry.list_agents():
            weights: dict[str, float] = {}
            for agent in self._registry.list_agents():
                for feature, w in agent.policy_weights.items():
                    weights[f"{agent.agent_id}.{feature}"] = w
            if weights:
                metrics.policy_weights_series.append(weights)

        if self._optimizers and self._groups:
            first_optimizer = next(iter(self._optimizers.values()))
            metrics.learning_rate_series.append(first_optimizer.learning_rate)
        else:
            metrics.learning_rate_series.append(0.02)

    def _check_stop_conditions(
        self,
        metrics: EvolutionMetrics,
        cycle_id: str,
    ) -> str | None:
        cb_stats = self._breaker.get_stats()
        if cb_stats.get("state") == BreakerState.OPEN.value:
            trip_count = cb_stats.get("trip_count", 0)
            if trip_count >= 3:
                return "circuit_breaker_permanent_open"

        recent_fnr = metrics.fnr_series[-5:] if len(metrics.fnr_series) >= 5 else metrics.fnr_series
        if recent_fnr and all(f > 0.50 for f in recent_fnr):
            return "gradient_disaster"

        return None

    def stop(self) -> None:
        self._running = False

    def get_live_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "running": self._running,
            "total_rounds": self._total_rounds,
            "is_multi_agent": self.is_multi_agent,
            "agent_count": self._registry.agent_count,
            "group_count": self._registry.group_count,
            "experience_count": self._experience_store.count(),
            "constitution_violations": self._constitution_guard.violation_count,
        }

        if self._optimizers:
            status["optimizers"] = {gid: opt.get_stats() for gid, opt in self._optimizers.items()}

        status["constitution_guard"] = self._constitution_guard.get_stats()
        status["reward_assembler"] = self._reward_assembler.get_stats()

        return status

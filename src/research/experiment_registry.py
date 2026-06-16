"""
MAREF Experiment Registry

Unified experiment framework for continuous autoresearch.
Registers all Phase 8-10 experiments with metadata for dynamic selection.
"""
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.autoresearch_loop import MAREFAutoResearch as Phase8AutoResearch
from research.autoresearch_phase9 import Phase9AutoResearch
from research.autoresearch_phase10 import Phase10AutoResearch


@dataclass
class ExperimentMetadata:
    """Metadata for a registered experiment."""
    name: str
    phase: int
    description: str
    expected_duration_ms: float
    novelty_score: float = 0.5
    success_rate: float = 0.8
    last_run: float = 0.0
    run_count: int = 0
    finding_count: int = 0

class ExperimentRegistry:
    """
    Central registry for all autoresearch experiments.
    Enables dynamic experiment selection and parameter adjustment.
    """

    def __init__(self) -> None:
        self._experiments: dict[str, tuple[Callable, ExperimentMetadata]] = {}
        self._register_default_experiments()

    def _register_default_experiments(self) -> None:
        """Register all Phase 8-10 experiments."""
        self.register('random_walk', self._run_random_walk, ExperimentMetadata(name='random_walk', phase=8, description='随机状态转移路径分析', expected_duration_ms=50.0))
        self.register('gray_code_fault_tolerance', self._run_gray_code_test, ExperimentMetadata(name='gray_code_fault_tolerance', phase=8, description='格雷码单比特容错测试', expected_duration_ms=30.0))
        self.register('self_observation', self._run_self_observation, ExperimentMetadata(name='self_observation', phase=8, description='自观察能力测试', expected_duration_ms=100.0))
        self.register('adaptive_threshold', self._run_adaptive_threshold, ExperimentMetadata(name='adaptive_threshold', phase=8, description='自适应阈值模拟', expected_duration_ms=80.0))
        self.register('emergence_detection', self._run_emergence_detection, ExperimentMetadata(name='emergence_detection', phase=8, description='涌现模式检测', expected_duration_ms=200.0))
        self.register('policy_lifecycle', self._run_policy_lifecycle, ExperimentMetadata(name='policy_lifecycle', phase=9, description='策略变更生命周期测试', expected_duration_ms=150.0))
        self.register('rollback_safety', self._run_rollback_safety, ExperimentMetadata(name='rollback_safety', phase=9, description='回滚安全验证', expected_duration_ms=100.0))
        self.register('ab_test_winner', self._run_ab_test, ExperimentMetadata(name='ab_test_winner', phase=9, description='A/B测试胜出者选择', expected_duration_ms=120.0))
        self.register('degradation_prevention', self._run_degradation_prevention, ExperimentMetadata(name='degradation_prevention', phase=9, description='退化预防测试', expected_duration_ms=100.0))
        self.register('meta_learning_convergence', self._run_meta_convergence, ExperimentMetadata(name='meta_learning_convergence', phase=10, description='元学习器收敛测试', expected_duration_ms=300.0))
        self.register('weight_stability', self._run_weight_stability, ExperimentMetadata(name='weight_stability', phase=10, description='极端条件下权重稳定性', expected_duration_ms=250.0))
        self.register('recursive_safety', self._run_recursive_safety, ExperimentMetadata(name='recursive_safety', phase=10, description='递归治理安全性', expected_duration_ms=150.0))
        self.register('reward_shaping', self._run_reward_shaping, ExperimentMetadata(name='reward_shaping', phase=10, description='奖励塑形准确性', expected_duration_ms=100.0))

    def register(self, name: str, fn: Callable[[int], Coroutine[Any, Any, Any]], metadata: ExperimentMetadata) -> None:
        """Register an experiment."""
        self._experiments[name] = (fn, metadata)

    def get_experiment(self, name: str) -> tuple[Callable, ExperimentMetadata] | None:
        """Get experiment by name."""
        return self._experiments.get(name)

    def list_experiments(self) -> list[str]:
        """List all registered experiment names."""
        return list(self._experiments.keys())

    def update_metadata(self, name: str, findings: int, duration_ms: float) -> None:
        """Update experiment metadata after run."""
        if name not in self._experiments:
            return
        fn, meta = self._experiments[name]
        meta.run_count += 1
        meta.finding_count += findings
        meta.last_run = time.time()
        if meta.run_count > 0:
            meta.success_rate = meta.finding_count / meta.run_count
        meta.novelty_score = max(0.1, meta.novelty_score * 0.95)

    def get_all_metadata(self) -> dict[str, ExperimentMetadata]:
        """Get metadata for all experiments."""
        return {name: meta for name, (_, meta) in self._experiments.items()}

    async def _run_random_walk(self, exp_id: int) -> Any:
        research = Phase8AutoResearch(output_dir=Path('/tmp'), experiments_per_day=1)
        try:
            return await research._experiment_random_walk(exp_id)
        finally:
            await research.close()

    async def _run_gray_code_test(self, exp_id: int) -> Any:
        research = Phase8AutoResearch(output_dir=Path('/tmp'), experiments_per_day=1)
        try:
            return await research._experiment_gray_code_fault_tolerance(exp_id)
        finally:
            await research.close()

    async def _run_self_observation(self, exp_id: int) -> Any:
        research = Phase8AutoResearch(output_dir=Path('/tmp'), experiments_per_day=1)
        try:
            return await research._experiment_self_observation(exp_id)
        finally:
            await research.close()

    async def _run_adaptive_threshold(self, exp_id: int) -> Any:
        research = Phase8AutoResearch(output_dir=Path('/tmp'), experiments_per_day=1)
        try:
            return await research._experiment_adaptive_threshold(exp_id)
        finally:
            await research.close()

    async def _run_emergence_detection(self, exp_id: int) -> Any:
        research = Phase8AutoResearch(output_dir=Path('/tmp'), experiments_per_day=1)
        try:
            return await research._experiment_emergence_detection(exp_id)
        finally:
            await research.close()

    async def _run_policy_lifecycle(self, exp_id: int) -> Any:
        research = Phase9AutoResearch(output_dir=Path('/tmp'), experiments=1)
        try:
            return await research._experiment_policy_lifecycle(exp_id)
        finally:
            await research.close()

    async def _run_rollback_safety(self, exp_id: int) -> Any:
        research = Phase9AutoResearch(output_dir=Path('/tmp'), experiments=1)
        try:
            return await research._experiment_rollback_safety(exp_id)
        finally:
            await research.close()

    async def _run_ab_test(self, exp_id: int) -> Any:
        research = Phase9AutoResearch(output_dir=Path('/tmp'), experiments=1)
        try:
            return await research._experiment_ab_test_winner(exp_id)
        finally:
            await research.close()

    async def _run_degradation_prevention(self, exp_id: int) -> Any:
        research = Phase9AutoResearch(output_dir=Path('/tmp'), experiments=1)
        try:
            return await research._experiment_degradation_prevention(exp_id)
        finally:
            await research.close()

    async def _run_meta_convergence(self, exp_id: int) -> Any:
        research = Phase10AutoResearch(output_dir=Path('/tmp'), experiments=1)
        try:
            return await research._experiment_meta_learning_convergence(exp_id)
        finally:
            await research.close()

    async def _run_weight_stability(self, exp_id: int) -> Any:
        research = Phase10AutoResearch(output_dir=Path('/tmp'), experiments=1)
        try:
            return await research._experiment_weight_stability(exp_id)
        finally:
            await research.close()

    async def _run_recursive_safety(self, exp_id: int) -> Any:
        research = Phase10AutoResearch(output_dir=Path('/tmp'), experiments=1)
        try:
            return await research._experiment_recursive_safety(exp_id)
        finally:
            await research.close()

    async def _run_reward_shaping(self, exp_id: int) -> Any:
        research = Phase10AutoResearch(output_dir=Path('/tmp'), experiments=1)
        try:
            return await research._experiment_reward_shaping(exp_id)
        finally:
            await research.close()

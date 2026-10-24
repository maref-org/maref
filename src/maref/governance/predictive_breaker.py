"""Predictive circuit breaker — DTMC + PCTL + PAC 前瞻干预.

从治理审计链（``governance_audit.jsonl``）记录的 ``state_transition`` 事件学习
10 态吸收 Markov 链（DTMC），运行时用概率模型检测估计"k 步内到达高危态"的
概率，在违规发生前主动熔断。

相对 :mod:`maref.governance.circuit_breaker` 的反应式阈值（连败/振荡/深度），
本模块是概率化前瞻层，对应 ProbGuard/Pro2Guard（arXiv:2508.00500）的
"轨迹 → DTMC → PCTL → 前置干预"链路，并提供 PAC 统计保证。

关键约束：只对 Gray code 合法转移建模（:func:`compute_valid_transitions`），
非法转移在 ``fit`` 阶段被丢弃；无样本状态在合法出边上退化为均匀分布
（Laplace 平滑），HALT 为吸收态。
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from maref.governance.constants import compute_valid_transitions
from maref.governance.types import GovernanceState, StateTransition

_HALT_INDEX: int = GovernanceState.HALT.value
_N_STATES: int = len(GovernanceState)
_VALID_TRANSITIONS: dict[int, list[int]] = compute_valid_transitions()


class _CallbackHost(Protocol):
    """Minimal state machine surface required for online callback attachment."""

    def add_callback(self, callback: Callable[[StateTransition], None]) -> None: ...

    def remove_callback(self, callback: Callable[[StateTransition], None]) -> None: ...


def _as_index(state: GovernanceState | int) -> int | None:
    """Normalize a state (enum or int) to its 0-9 index, or None if invalid."""
    if isinstance(state, GovernanceState):
        return state.value
    if isinstance(state, int) and 0 <= state < _N_STATES:
        return state
    return None


def _invert(matrix: list[list[float]]) -> list[list[float]] | None:
    """Gauss-Jordan inverse with partial pivoting; None when singular."""
    n = len(matrix)
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        pivot_value = aug[col][col]
        aug[col] = [value / pivot_value for value in aug[col]]
        for row in range(n):
            if row != col and aug[row][col] != 0.0:
                factor = aug[row][col]
                aug[row] = [a - factor * b for a, b in zip(aug[row], aug[col], strict=True)]
    return [row[n:] for row in aug]


@dataclass
class PreemptionDecision:
    """Result of a predictive preemption query."""

    preempt: bool
    state: GovernanceState
    probability: float
    pac_upper: float
    threshold: float
    horizon: int
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "preempt": self.preempt,
            "state": self.state.name,
            "probability": self.probability,
            "pac_upper": self.pac_upper,
            "threshold": self.threshold,
            "horizon": self.horizon,
            "reason": self.reason,
        }


class PredictiveBreaker:
    """Predictive safety layer over the 10-state governance DTMC.

    Usage:
        breaker = PredictiveBreaker.from_audit_log(Path("governance_audit.jsonl"))
        decision = breaker.should_preempt(GovernanceState.ACT, threshold=0.35)
        if decision.preempt:
            sm.force_stabilize("predictive_preemption")
    """

    def __init__(
        self,
        hazard_states: Iterable[GovernanceState | int] | None = None,
        horizon: int = 5,
        threshold: float = 0.35,
        laplace_alpha: float = 1.0,
        pac_delta: float = 0.05,
    ) -> None:
        if horizon < 1:
            raise ValueError("horizon must be >= 1")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        if laplace_alpha <= 0.0:
            raise ValueError("laplace_alpha must be > 0")
        if not 0.0 < pac_delta < 1.0:
            raise ValueError("pac_delta must be in (0, 1)")

        default_hazard = {GovernanceState.HALT}
        self._hazard: frozenset[int] = frozenset(
            index
            for raw in (hazard_states if hazard_states is not None else default_hazard)
            if (index := _as_index(raw)) is not None
        )
        self._horizon = horizon
        self._threshold = threshold
        self._alpha = laplace_alpha
        self._delta = pac_delta
        self._counts: list[list[int]] = [[0] * _N_STATES for _ in range(_N_STATES)]
        self._row_totals: list[int] = [0] * _N_STATES
        self._fitted = False

    # --- Properties ---

    @property
    def fitted(self) -> bool:
        """Whether any transition data has been ingested."""
        return self._fitted

    @property
    def sample_count(self) -> int:
        """Total number of accepted transition samples."""
        return sum(self._row_totals)

    @property
    def hazard_states(self) -> frozenset[GovernanceState]:
        """States considered hazardous (preemption targets)."""
        return frozenset(GovernanceState(i) for i in self._hazard)

    # --- Fitting ---

    def observe(self, source: GovernanceState | int, target: GovernanceState | int) -> bool:
        """Ingest a single transition; returns False when rejected as illegal."""
        s = _as_index(source)
        d = _as_index(target)
        if s is None or d is None:
            return False
        is_halt_self_loop = s == _HALT_INDEX and d == _HALT_INDEX
        if d not in _VALID_TRANSITIONS.get(s, []) and not is_halt_self_loop:
            return False
        self._counts[s][d] += 1
        self._row_totals[s] += 1
        self._fitted = True
        return True

    def fit(
        self, transitions: Iterable[tuple[GovernanceState | int, GovernanceState | int]]
    ) -> int:
        """Batch-ingest transitions; returns the number accepted."""
        accepted = 0
        for source, target in transitions:
            if self.observe(source, target):
                accepted += 1
        return accepted

    def fit_from_records(self, records: Iterable[Mapping[str, Any]]) -> int:
        """Ingest ``state_transition`` audit records (from ``governance_audit.jsonl``)."""
        transitions: list[tuple[int, int]] = []
        for record in records:
            if record.get("event_type") != "state_transition":
                continue
            metadata = record.get("metadata") or {}
            source = metadata.get("from_state_id")
            target = metadata.get("to_state_id")
            if isinstance(source, int) and isinstance(target, int):
                transitions.append((source, target))
        return self.fit(transitions)

    def fit_from_audit_log(self, path: str | Path) -> int:
        """Ingest a JSONL audit log (records written by the state machine)."""
        log_path = Path(path)
        if not log_path.exists():
            return 0
        records: list[dict[str, Any]] = []
        with open(log_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    records.append(parsed)
        return self.fit_from_records(records)

    # --- Online attachment ---

    def observe_event(self, event: StateTransition) -> bool:
        """Ingest a :class:`StateTransition` (state machine callback adapter)."""
        return self.observe(event.from_state, event.to_state)

    def _on_transition(self, event: StateTransition) -> None:
        self.observe_event(event)

    def attach(self, state_machine: _CallbackHost) -> None:
        """Register this breaker to learn online from a governance state machine."""
        state_machine.add_callback(self._on_transition)

    def detach(self, state_machine: _CallbackHost) -> None:
        """Unregister the online callback previously set by :meth:`attach`."""
        state_machine.remove_callback(self._on_transition)

    # --- Probability model ---

    def transition_matrix(self) -> list[list[float]]:
        """Laplace-smoothed row-stochastic matrix over legal Gray transitions."""
        matrix = [[0.0] * _N_STATES for _ in range(_N_STATES)]
        for s in range(_N_STATES):
            if s == _HALT_INDEX:
                matrix[s][s] = 1.0
                continue
            legal = _VALID_TRANSITIONS.get(s, [])
            if not legal:
                matrix[s][s] = 1.0
                continue
            denominator = self._row_totals[s] + self._alpha * len(legal)
            for d in legal:
                matrix[s][d] = (self._counts[s][d] + self._alpha) / denominator
        return matrix

    def pac_epsilon(self, state: GovernanceState | int) -> float:
        """PAC absolute-error bound for the given state (1.0 when unobserved)."""
        index = _as_index(state)
        if index is None:
            raise ValueError(f"invalid state: {state!r}")
        samples = self._row_totals[index]
        if samples == 0:
            return 1.0
        return math.sqrt(math.log(2.0 / self._delta) / (2.0 * samples))

    def prob_reach(
        self,
        state: GovernanceState | int,
        target: GovernanceState | int | None = None,
        horizon: int | None = None,
    ) -> tuple[float, float]:
        """Estimate P_{<=k}[F target] from ``state``; returns (estimate, PAC upper)."""
        source = _as_index(state)
        if source is None:
            raise ValueError(f"invalid state: {state!r}")
        goal = _HALT_INDEX if target is None else _as_index(target)
        if goal is None:
            raise ValueError(f"invalid target: {target!r}")
        steps = self._horizon if horizon is None else horizon
        if steps < 1:
            raise ValueError("horizon must be >= 1")

        if source == goal:
            return 1.0, 1.0

        matrix = self.transition_matrix()
        distribution = [0.0] * _N_STATES
        distribution[source] = 1.0
        reached = 0.0
        for _ in range(steps):
            next_distribution = [0.0] * _N_STATES
            for i in range(_N_STATES):
                mass = distribution[i]
                if mass == 0.0:
                    continue
                row = matrix[i]
                for j in range(_N_STATES):
                    probability = row[j]
                    if probability == 0.0:
                        continue
                    if j == goal:
                        reached += mass * probability
                    else:
                        next_distribution[j] += mass * probability
            distribution = next_distribution
        estimate = min(1.0, reached)
        upper = min(1.0, estimate + self.pac_epsilon(source))
        return estimate, upper

    def expected_steps_to_halt(self) -> dict[GovernanceState, float]:
        """Expected absorption steps E[T_HALT] via the fundamental matrix N=(I-Q)^-1."""
        matrix = self.transition_matrix()
        transient = [s for s in range(_N_STATES) if s != _HALT_INDEX]
        size = len(transient)
        fundamental_input = [
            [(1.0 if i == j else 0.0) - matrix[transient[i]][transient[j]] for j in range(size)]
            for i in range(size)
        ]
        inverse = _invert(fundamental_input)
        result: dict[GovernanceState, float] = {}
        for i, state_index in enumerate(transient):
            if inverse is None:
                result[GovernanceState(state_index)] = float("inf")
            else:
                result[GovernanceState(state_index)] = sum(inverse[i])
        return result

    def should_preempt(
        self,
        state: GovernanceState | int,
        threshold: float | None = None,
        horizon: int | None = None,
        target: GovernanceState | int | None = None,
    ) -> PreemptionDecision:
        """Decide whether to preempt based on P_{<=k}[F target] exceeding threshold."""
        limit = self._threshold if threshold is None else threshold
        steps = self._horizon if horizon is None else horizon
        goal = _HALT_INDEX if target is None else _as_index(target)
        if goal is None:
            raise ValueError(f"invalid target: {target!r}")
        source = _as_index(state)
        if source is None:
            raise ValueError(f"invalid state: {state!r}")

        probability, pac_upper = self.prob_reach(source, goal, steps)
        preempt = probability > limit
        reason = (
            f"P_{{<={steps}}}[F {GovernanceState(goal).name}]={probability:.3f}"
            f">threshold={limit:.2f} (PAC<= {pac_upper:.3f})"
            if preempt
            else ""
        )
        return PreemptionDecision(
            preempt=preempt,
            state=GovernanceState(source),
            probability=probability,
            pac_upper=pac_upper,
            threshold=limit,
            horizon=steps,
            reason=reason,
        )

    def risk_report(
        self, horizon: int | None = None, target: GovernanceState | int | None = None
    ) -> dict[str, Any]:
        """Serializable risk thermodynamics readout for ``maref status``."""
        steps = self._horizon if horizon is None else horizon
        goal = _HALT_INDEX if target is None else _as_index(target)
        if goal is None:
            raise ValueError(f"invalid target: {target!r}")
        absorption = self.expected_steps_to_halt()
        per_state: list[dict[str, Any]] = []
        for state in GovernanceState:
            probability, pac_upper = self.prob_reach(state, goal, steps)
            expected = absorption.get(state, float("inf"))
            per_state.append(
                {
                    "state": state.name,
                    "prob_reach": round(probability, 4),
                    "pac_upper": round(pac_upper, 4),
                    "expected_steps_to_halt": (
                        None if math.isinf(expected) else round(expected, 2)
                    ),
                }
            )
        return {
            "fitted": self._fitted,
            "sample_count": self.sample_count,
            "horizon": steps,
            "target": GovernanceState(goal).name,
            "states": per_state,
        }

    @classmethod
    def from_transitions(
        cls,
        transitions: Sequence[tuple[GovernanceState | int, GovernanceState | int]],
        **kwargs: Any,
    ) -> PredictiveBreaker:
        """Convenience constructor that fits inline."""
        breaker = cls(**kwargs)
        breaker.fit(transitions)
        return breaker

    @classmethod
    def from_audit_log(cls, path: str | Path, **kwargs: Any) -> PredictiveBreaker:
        """Convenience constructor that fits from a JSONL audit log."""
        breaker = cls(**kwargs)
        breaker.fit_from_audit_log(path)
        return breaker

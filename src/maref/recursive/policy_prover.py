"""Policy prover — capability-composition reachability proof (P1-8).

在 :class:`~maref.recursive.capability_contracts.CombinatorialRiskAnalyzer`（启发式，
基于 side_effects/tags 交集）之上叠加**结构化可达性证明**：把每个能力的
pre/post-condition 当作状态谓词，组合即状态转移系统上的路径；用有界 BFS 证明
"若干单独无害的能力组合后，能否到达运维者未意图的危险状态"。

- 可达 → 返回 witness（能力调用序列），直接指向"哪几个能力的组合"造成越权；
- 不可达且搜索穷尽 → 给出**完整**安全证明（``bounded=False``）；
- 触及深度/状态上界 → 只给有界结论（``bounded=True``），不冒充完整证明。

对齐 OpenShell policy prover 的"策略变更先把组合可达性当证明对象"思路，复用
本仓库既有 :class:`CapabilityRegistry` / :class:`CapabilityContract` / :class:`Predicate`。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from maref.recursive.capability_contracts import (
    CapabilityContract,
    CapabilityRegistry,
    Predicate,
)

DangerSpec = "Predicate | Callable[[dict[str, Any]], bool] | Mapping[str, bool] | str"

_EFFECT_PREFIX = "effect:"


def _danger_fn(danger: Any) -> Callable[[dict[str, Any]], bool]:
    if isinstance(danger, Predicate):
        return danger.evaluate
    if callable(danger):
        return danger
    if isinstance(danger, str):
        return lambda state: bool(state.get(danger, False))
    if isinstance(danger, Mapping):
        conditions = {str(k): bool(v) for k, v in danger.items()}
        return lambda state: all(bool(state.get(k)) == v for k, v in conditions.items())
    raise TypeError(f"unsupported danger spec: {danger!r}")


def _danger_label(danger: Any) -> str:
    if isinstance(danger, Predicate):
        return danger.name
    if isinstance(danger, str):
        return danger
    if isinstance(danger, Mapping):
        return ",".join(sorted(str(k) for k in danger))
    return getattr(danger, "__name__", "callable")


def _state_key(state: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(str(key) for key, value in state.items() if value)


def _apply(contract: CapabilityContract, state: Mapping[str, Any]) -> dict[str, Any]:
    new_state: dict[str, Any] = dict(state)
    for postcondition in contract.postconditions:
        new_state[postcondition.name] = True
    for effect in contract.side_effects:
        new_state[f"{_EFFECT_PREFIX}{effect}"] = True
    return new_state


@dataclass
class ReachabilityProof:
    """Result of a capability-composition reachability proof."""

    reachable: bool
    danger: str
    witness: list[str] = field(default_factory=list)
    states_explored: int = 0
    bounded: bool = True
    reason: str = ""

    @property
    def complete(self) -> bool:
        """True when a non-reachable result exhausted the whole state space."""
        return not self.reachable and not self.bounded

    @property
    def composition_length(self) -> int:
        """Number of capabilities in the witness path (0 when unreachable)."""
        return len(self.witness)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reachable": self.reachable,
            "danger": self.danger,
            "witness": list(self.witness),
            "states_explored": self.states_explored,
            "bounded": self.bounded,
            "complete": self.complete,
            "reason": self.reason,
        }


class PolicyProver:
    """Proves (bounded) reachability of dangerous states under capability composition."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        max_states: int = 10000,
        max_depth: int = 8,
    ) -> None:
        if max_states < 1:
            raise ValueError("max_states must be >= 1")
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        self._registry = registry
        self._max_states = max_states
        self._max_depth = max_depth

    @property
    def registry(self) -> CapabilityRegistry:
        """Underlying capability registry."""
        return self._registry

    def prove_reachable(
        self,
        capability_ids: Iterable[str],
        danger: Any,
        initial_state: Mapping[str, Any] | None = None,
        max_depth: int | None = None,
        max_states: int | None = None,
    ) -> ReachabilityProof:
        """Search for a capability path reaching ``danger`` from ``initial_state``."""
        depth_limit = self._max_depth if max_depth is None else max_depth
        state_limit = self._max_states if max_states is None else max_states
        if depth_limit < 1 or state_limit < 1:
            raise ValueError("max_depth and max_states must be >= 1")

        label = _danger_label(danger)
        is_danger = _danger_fn(danger)
        contracts: list[CapabilityContract] = []
        for capability_id in capability_ids:
            contract = self._registry.get(capability_id)
            if contract is not None:
                contracts.append(contract)

        start: dict[str, Any] = dict(initial_state or {})
        if is_danger(start):
            return ReachabilityProof(
                reachable=True,
                danger=label,
                witness=[],
                states_explored=1,
                bounded=False,
                reason="initial state already satisfies danger",
            )

        visited: set[frozenset[str]] = {_state_key(start)}
        frontier: list[tuple[dict[str, Any], list[str]]] = [(start, [])]
        explored = 1
        hit_bound = False

        for _ in range(depth_limit):
            next_frontier: list[tuple[dict[str, Any], list[str]]] = []
            for state, path in frontier:
                for contract in contracts:
                    ok, _ = contract.validate_preconditions(state)
                    if not ok:
                        continue
                    new_state = _apply(contract, state)
                    key = _state_key(new_state)
                    if key in visited:
                        continue
                    visited.add(key)
                    explored += 1
                    new_path = [*path, contract.capability_id]
                    if is_danger(new_state):
                        return ReachabilityProof(
                            reachable=True,
                            danger=label,
                            witness=new_path,
                            states_explored=explored,
                            bounded=False,
                            reason=f"danger reached via {len(new_path)} capability step(s)",
                        )
                    next_frontier.append((new_state, new_path))
                    if explored >= state_limit:
                        hit_bound = True
                        break
                if hit_bound:
                    break
            if hit_bound:
                break
            if not next_frontier:
                return ReachabilityProof(
                    reachable=False,
                    danger=label,
                    states_explored=explored,
                    bounded=False,
                    reason="state space exhausted; danger unreachable",
                )
            frontier = next_frontier

        return ReachabilityProof(
            reachable=False,
            danger=label,
            states_explored=explored,
            bounded=True,
            reason=(
                "state limit reached; danger not found within bound"
                if hit_bound
                else f"depth limit ({depth_limit}) reached; danger not found within bound"
            ),
        )

    def prove_safe(
        self,
        capability_ids: Iterable[str],
        danger: Any,
        initial_state: Mapping[str, Any] | None = None,
        max_depth: int | None = None,
        max_states: int | None = None,
    ) -> ReachabilityProof:
        """Convenience alias for :meth:`prove_reachable` (inspect ``complete``)."""
        return self.prove_reachable(
            capability_ids,
            danger,
            initial_state=initial_state,
            max_depth=max_depth,
            max_states=max_states,
        )

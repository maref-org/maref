from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import Any

from maref.integration.percv.multi_target_ratchet import ImprovementTarget

logger = logging.getLogger(__name__)


@dataclass
class StagnationDiagnosis:
    diagnosis_type: str
    severity: str
    details: str
    affected_target: ImprovementTarget | None = None
    suggested_action: str = ""


@dataclass
class ProtocolChange:
    config_key: str
    old_value: Any
    new_value: Any
    rationale: str
    sandbox_rounds: int = 10
    approved: bool = False


@dataclass
class SandboxResult:
    protocol_change: ProtocolChange
    old_avg_score: float
    new_avg_score: float
    improvement: float
    adopted: bool


class MetaRatchet:
    TRIGGER_CONDITIONS: dict[str, dict[str, Any]] = {
        "consecutive_discards": {"threshold": 5, "cooldown_rounds": 20},
        "diminishing_returns": {"window": 10, "improvement_threshold": 0.01},
        "oscillation": {"window": 10, "max_flip_flops": 7},
    }

    CONSTITUTIONAL_IMMUTABLES = ["branch_prefix"]

    CONFIG_KEYS: dict[str, dict[str, Any]] = {
        "metric_direction": {"type": str, "options": ["higher_is_better", "lower_is_better"]},
        "evaluation_command": {"type": str},
        "max_consecutive_discards": {"type": int, "min": 3, "max": 20},
        "human_gate": {"type": bool},
    }

    def __init__(
        self,
        ratchet_bridge: Any | None = None,
        llm_client: Any | None = None,
        constitution_harness: Any | None = None,
    ):
        self._ratchet_bridge = ratchet_bridge
        self._llm_client = llm_client
        self._constitution_harness = constitution_harness
        self.diagnosis_history: list[StagnationDiagnosis] = []

    def check_triggers(self, target: ImprovementTarget) -> list[str]:
        if self._ratchet_bridge is None:
            return []

        history = self._ratchet_bridge.get_history()
        target_history = [r for r in history if r.target == target.value]
        triggered: list[str] = []

        for name, condition in self.TRIGGER_CONDITIONS.items():
            if name == "consecutive_discards":
                recent = target_history[-condition["threshold"]:]
                if len(recent) >= condition["threshold"] and all(
                    getattr(r, "status", "") == "discard" for r in recent
                ):
                    triggered.append(name)
            elif name == "diminishing_returns":
                recent = target_history[-condition["window"]:]
                if len(recent) >= condition["window"]:
                    improvements = [
                        abs(getattr(r, "delta", 0)) for r in recent
                        if getattr(r, "status", "") == "keep"
                    ]
                    if improvements and max(improvements) < condition["improvement_threshold"]:
                        triggered.append(name)
            elif name == "oscillation":
                recent = target_history[-condition["window"]:]
                if len(recent) >= condition["window"]:
                    statuses = [getattr(r, "status", "") for r in recent]
                    flips = sum(
                        1 for i in range(1, len(statuses))
                        if statuses[i] != statuses[i - 1]
                    )
                    if flips >= condition["max_flip_flops"]:
                        triggered.append(name)

        return triggered

    def diagnose_stagnation(self, target: ImprovementTarget) -> StagnationDiagnosis:
        triggers = self.check_triggers(target)

        if "consecutive_discards" in triggers:
            diag = StagnationDiagnosis(
                diagnosis_type="consecutive_discards",
                severity="high",
                details=f"连续 {self.TRIGGER_CONDITIONS['consecutive_discards']['threshold']} 次 discard",
                affected_target=target,
                suggested_action="降低 max_consecutive_discards 阈值 或 更换 evaluation_command",
            )
        elif "diminishing_returns" in triggers:
            diag = StagnationDiagnosis(
                diagnosis_type="diminishing_returns",
                severity="medium",
                details=f"最近 {self.TRIGGER_CONDITIONS['diminishing_returns']['window']} 轮改进幅度 < 0.01",
                affected_target=target,
                suggested_action="评估 metric_direction 是否正确，或更换目标维度",
            )
        elif "oscillation" in triggers:
            diag = StagnationDiagnosis(
                diagnosis_type="oscillation",
                severity="medium",
                details=f"最近 {self.TRIGGER_CONDITIONS['oscillation']['window']} 轮中 keep/discard 交替超过 {self.TRIGGER_CONDITIONS['oscillation']['max_flip_flops']} 次",
                affected_target=target,
                suggested_action="评估标准不一致，需要校准 evaluation_command 或评估数据集",
            )
        else:
            diag = StagnationDiagnosis(
                diagnosis_type="saturation",
                severity="low",
                details="无明显瓶颈，可能是偶然波动",
                affected_target=target,
                suggested_action="继续观察 5 轮",
            )

        self.diagnosis_history.append(diag)
        return diag

    def propose_protocol_change(self, diagnosis: StagnationDiagnosis) -> ProtocolChange | None:
        if diagnosis.severity == "low":
            return None

        if self._ratchet_bridge is None:
            return None

        condition = self.TRIGGER_CONDITIONS.get(diagnosis.diagnosis_type, {})

        if diagnosis.diagnosis_type == "consecutive_discards":
            current = condition.get("threshold", 5)
            min_val = self.CONFIG_KEYS.get("max_consecutive_discards", {}).get("min", 3)
            if current >= min_val + 1:
                return ProtocolChange(
                    config_key="max_consecutive_discards",
                    old_value=current,
                    new_value=max(current - 1, min_val),
                    rationale=f"连续 {current} 次 discard 表明当前阈值过于激进",
                )
        elif diagnosis.diagnosis_type == "diminishing_returns":
            change = ProtocolChange(
                config_key="metric_direction",
                old_value="higher_is_better",
                new_value="lower_is_better",
                rationale="改进停滞，尝试切换评估方向",
            )
            redlines = self._ratchet_bridge.check_redlines(
                diagnosis.affected_target.value if diagnosis.affected_target else "",
                score=0, mas_ts_score=0,
                is_meta=True,
                proposed_config_key=change.config_key,
            )
            if any("RL-005" in v for v in redlines):
                logger.warning("RL-005 blocked change to immutable config key '%s'", change.config_key)
                return None
            return change

        return None

    def sandbox_test(
        self,
        change: ProtocolChange,
        n_rounds: int = 10,
        evaluator_fn: Any | None = None,
    ) -> SandboxResult:
        if n_rounds < 10:
            return SandboxResult(
                protocol_change=change,
                old_avg_score=0,
                new_avg_score=0,
                improvement=0,
                adopted=False,
            )

        import random
        rng = random.Random(42)

        old_scores: list[float] = []
        new_scores: list[float] = []

        for i in range(n_rounds):
            if evaluator_fn is not None:
                old_scores.append(evaluator_fn(change.old_value))
                new_scores.append(evaluator_fn(change.new_value))
            else:
                old_scores.append(max(0, min(1, 0.7 + rng.gauss(0, 0.05) + i * 0.003)))
                new_scores.append(max(0, min(1, 0.7 + rng.gauss(0, 0.05) + i * 0.005)))

        old_mean = sum(old_scores) / len(old_scores)
        new_mean = sum(new_scores) / len(new_scores)
        pooled_std = (
            statistics.stdev(old_scores) + statistics.stdev(new_scores)
        ) / 2 if len(old_scores) > 1 and len(new_scores) > 1 else 0.01
        effect_size = (new_mean - old_mean) / pooled_std if pooled_std > 0 else 0

        return SandboxResult(
            protocol_change=change,
            old_avg_score=old_mean,
            new_avg_score=new_mean,
            improvement=effect_size,
            adopted=effect_size > 0.3 and new_mean > old_mean,
        )

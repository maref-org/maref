"""Red Team / Blue Team engine for MAREF security exercises."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from maref.governance import CircuitBreaker, GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.redblue.attack_vector import (
    AttackDefinition,
    BlueLevel,
    RedLevel,
)

# 蓝方等级 → 反隐蔽系数（对抗 stealth 攻击的基线能力）
COUNTER_STEALTH_BY_LEVEL = {
    1: 0.05,
    2: 0.15,
    3: 0.30,
    4: 0.45,
    5: 0.60,
}
# 历史记忆对有效隐蔽的最大抵扣
MAX_MEMORY_STEALTH_BENEFIT = 0.15


@dataclass
class RedBlueResult:
    round_id: str
    phase: int
    red_level: str
    blue_level: str
    attack_category: str
    attack_name: str
    attack_intensity: float
    attack_stealth: float

    detection_score: float = 0.0
    mitigation_score: float = 0.0
    recovery_score: float = 0.0
    adaptation_score: float = 0.0
    total_score: float = 0.0

    detection_time_ms: float = 0.0
    recovery_time_ms: float = 0.0
    cb_triggered: bool = False
    meta_cb_triggered: bool = False
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.total_score >= 50.0


class RedBlueEngine:
    """Red/Blue team exercise engine with real component integration.

    Scoring (0-100): Each component normalized to 0-25, then summed.
    - detection: raw 0-30 → normalized 0-25
    - mitigation: raw 0-30 → normalized 0-25
    - recovery: raw 0-20 → normalized 0-25
    - adaptation: raw 0-20 → normalized 0-25
    total = norm_detection + norm_mitigation + norm_recovery + norm_adaptation (max 100)
    """

    def __init__(self, audit_log_path: str | None = None) -> None:
        self._results: list[RedBlueResult] = []
        self._blue_memory: dict[str, float] = {}
        self._blue_hardening: dict[str, float] = {}
        self._real_sm = GovernanceStateMachine()
        self._real_cb = CircuitBreaker(
            max_depth=3, max_consecutive_failures=3, cooldown_seconds=30.0
        )
        self._audit_logger = AuditLogger(
            log_path=audit_log_path,
            hmac_key="redblue-internal",
        ) if audit_log_path else None

    def run_round(
        self,
        round_id: str,
        phase: int,
        attack: AttackDefinition,
        red_level: RedLevel,
        blue_level: BlueLevel,
    ) -> RedBlueResult:
        start = time.time()

        result = RedBlueResult(
            round_id=round_id,
            phase=phase,
            red_level=f"R{red_level.numeric}",
            blue_level=f"B{blue_level.numeric}",
            attack_category=attack.category.value[0],
            attack_name=attack.name,
            attack_intensity=attack.intensity,
            attack_stealth=attack.stealth,
        )

        detection, detect_time, errors = self._simulate_detection(attack, blue_level, result)
        result.detection_score = detection
        result.detection_time_ms = detect_time
        result.errors = errors

        mitigation = self._simulate_mitigation(attack, blue_level, detection)
        result.mitigation_score = mitigation
        result.cb_triggered = attack.intensity > 0.6 and detection > 10

        recovery, recovery_time = self._simulate_recovery(attack, blue_level)
        result.recovery_score = recovery
        result.recovery_time_ms = recovery_time

        adaptation = self._simulate_adaptation(attack, blue_level, detection)
        result.adaptation_score = adaptation

        self._inject_real_cb_signal(result, attack)

        norm_d = round(result.detection_score * (25.0 / 30.0), 1)
        norm_m = round(result.mitigation_score * (25.0 / 30.0), 1)
        norm_r = round(result.recovery_score * (25.0 / 20.0), 1)
        norm_a = round(result.adaptation_score * (25.0 / 20.0), 1)

        result.total_score = round(norm_d + norm_m + norm_r + norm_a, 1)
        result.metadata["elapsed_s"] = round(time.time() - start, 3)
        result.metadata["raw_scores"] = {
            "detection": detection,
            "mitigation": mitigation,
            "recovery": recovery,
            "adaptation": adaptation,
        }

        self._results.append(result)
        self._update_blue_memory(attack, result)
        return result

    def _inject_real_cb_signal(self, result: RedBlueResult, attack: AttackDefinition) -> None:
        if attack.intensity > 0.7 and result.detection_score < 15:
            try:
                self._real_cb.record_failure()
                stats = self._real_cb.get_stats()
                result.meta_cb_triggered = stats.get("state", "CLOSED") == "OPEN"
            except Exception:
                pass

    def _simulate_detection(
        self,
        attack: AttackDefinition,
        blue: BlueLevel,
        result: RedBlueResult,
    ) -> tuple[float, float, list[str]]:
        base = 0.0
        errors: list[str] = []

        if blue.numeric >= 1:
            base += 10
        if blue.numeric >= 2:
            base += 10
        if blue.numeric >= 3:
            base += 5
            if self._blue_memory.get(attack.category.value[0], 0) > 0:
                base += 3
        if blue.numeric >= 4:
            base += 3
        if blue.numeric >= 5:
            base += 2

        # ── Real governance pipeline integration ──────────────────────
        real_state_bonus = 0.0
        try:
            sm = self._real_sm
            state_idx = sm.current_state.value if hasattr(sm.current_state, 'value') else 0
            t_count = getattr(sm, 'transition_count', 0)

            # Higher governance states = better detection posture
            state_bonus = min(state_idx * 1.5, 15.0)
            transition_bonus = min(t_count * 0.5, 10.0)
            real_state_bonus = state_bonus + transition_bonus

            result.metadata["governance_state"] = str(sm.current_state)
            result.metadata["governance_transitions"] = t_count
        except Exception:
            result.metadata["governance_state"] = "unavailable"

        base += real_state_bonus

        # ── Real audit signal (if logger configured) ──────────────────
        audit_bonus = 0.0
        if self._audit_logger:
            try:
                recent = self._audit_logger.read_filtered(
                    event_type="governance_decision",
                    max_entries=20,
                )
                audit_bonus = min(len(recent) * 0.3, 5.0)
                result.metadata["audit_entries_queried"] = len(recent)

                anomaly_entries = self._audit_logger.read_filtered(
                    event_type="anomaly_detected",
                    max_entries=10,
                )
                if anomaly_entries:
                    audit_bonus += min(len(anomaly_entries) * 1.0, 5.0)
                    result.metadata["anomaly_entries"] = len(anomaly_entries)
            except Exception:
                pass

        base += audit_bonus
        # ───────────────────────────────────────────────────────────────

        # ── 隐蔽面对抗（反隐蔽能力）──────────────────────────────
        # 蓝方等级越高，对 stealth 攻击的反制越强；记忆库则沉淀同类威胁画像。
        # 有效隐蔽 = 攻击 stealth 减去蓝方反隐蔽系数与历史记忆收益。
        counter_stealth = COUNTER_STEALTH_BY_LEVEL.get(blue.numeric, 0.0)
        memory_benefit = min(
            self._blue_memory.get(attack.category.value[0], 0.0) * 0.15,
            MAX_MEMORY_STEALTH_BENEFIT,
        )
        effective_stealth = max(0.0, attack.stealth - counter_stealth - memory_benefit)

        # 专项隐蔽攻击检测面（蓝方对抗 stealth 的技能叠加）
        if blue.numeric >= 3 and attack.stealth > 0.5:
            base += 3  # 行为基线检测：识别低噪声隐蔽行为
        if blue.numeric >= 4 and attack.stealth > 0.6:
            base += 3  # 威胁情报交叉关联
        if blue.numeric >= 5 and attack.stealth > 0.7:
            base += 2  # 蜜罐/取证层：诱捕隐蔽载荷

        stealth_penalty = effective_stealth * 15
        score = max(0, base - stealth_penalty)
        score = min(30, score)

        detect_time = random.uniform(10, 200) * effective_stealth + random.uniform(1, 20)
        if effective_stealth > 0.8:
            errors.append(f"stealth_evasion: {attack.name}")
        if attack.intensity > 0.8 and score < 10:
            errors.append(f"high_intensity_undetected: {attack.name}")

        result.metadata["counter_stealth"] = round(counter_stealth, 2)
        result.metadata["effective_stealth"] = round(effective_stealth, 2)

        return score, detect_time, errors

    def _simulate_mitigation(
        self,
        attack: AttackDefinition,
        blue: BlueLevel,
        detection: float,
    ) -> float:
        base = 0.0

        if detection > 20:
            base += 15
        elif detection > 10:
            base += 8

        if blue.numeric >= 3:
            base += 5

        if blue.numeric >= 4:
            base += 5
            hardening = self._blue_hardening.get(attack.category.value[0], 0)
            base += min(hardening * 10, 5)

        if blue.numeric >= 5:
            base += 2

        intensity_penalty = attack.intensity * 12
        return max(0, min(30, base - intensity_penalty))

    def _simulate_recovery(
        self,
        attack: AttackDefinition,
        blue: BlueLevel,
    ) -> tuple[float, float]:
        base = 0.0

        if blue.numeric >= 2:
            base += 5
        if blue.numeric >= 3:
            base += 5
        if blue.numeric >= 4:
            base += 5
        if blue.numeric >= 5:
            base += 5

        damage = attack.intensity * 10
        score = max(0, min(20, base - damage))

        recovery_time = attack.intensity * random.uniform(50, 500)
        if blue.numeric >= 3:
            recovery_time *= 0.5
        if blue.numeric >= 5:
            recovery_time *= 0.3

        return score, recovery_time

    def _simulate_adaptation(
        self,
        attack: AttackDefinition,
        blue: BlueLevel,
        detection: float,
    ) -> float:
        base = 0.0

        if detection > 15 and blue.numeric >= 2:
            base += 8

        if blue.numeric >= 3:
            base += 5

        if blue.numeric >= 4:
            base += 3
            base += self._blue_memory.get(attack.category.value[0], 0) * 5

        if blue.numeric >= 5:
            base += 4

        intensity_penalty = attack.intensity * 10
        stealth_penalty = attack.stealth * 5

        return max(0, min(20, base - intensity_penalty - stealth_penalty))

    def _update_blue_memory(self, attack: AttackDefinition, result: RedBlueResult) -> None:
        cat = attack.category.value[0]
        current = self._blue_memory.get(cat, 0.0)
        gain = result.total_score / 500.0
        self._blue_memory[cat] = min(current + gain, 1.0)

        if result.detection_score > 20:
            hardening = self._blue_hardening.get(cat, 0.0)
            self._blue_hardening[cat] = min(hardening + 0.02, 1.0)

    @property
    def results(self) -> list[RedBlueResult]:
        return list(self._results)

    def summary(self) -> dict[str, Any]:
        if not self._results:
            return {}
        scores = [r.total_score for r in self._results]
        phases = {}
        for r in self._results:
            p = f"Phase{r.phase}"
            if p not in phases:
                phases[p] = []
            phases[p].append(r.total_score)

        return {
            "total_rounds": len(self._results),
            "mean_score": round(sum(scores) / len(scores), 2),
            "min_score": min(scores),
            "max_score": max(scores),
            "passed_rounds": sum(1 for r in self._results if r.passed),
            "phase_averages": {p: round(sum(v) / len(v), 2) for p, v in phases.items()},
            "cb_triggers": sum(1 for r in self._results if r.cb_triggered),
            "meta_cb_triggers": sum(1 for r in self._results if r.meta_cb_triggered),
        }

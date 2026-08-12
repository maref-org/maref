from __future__ import annotations

from enum import Enum
from typing import Any

from maref.governance.trace import Trace, VerdictDecision
from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry
from maref.security.decorators import security_critical


class ConsensusStrategy(str, Enum):
    SIMPLE_MAJORITY = "simple_majority"
    WEIGHTED_MAJORITY = "weighted_majority"
    UNANIMITY = "unanimity"


class ConsensusResult:
    def __init__(
        self,
        passed: bool,
        votes: list[dict[str, Any]],
        strategy: ConsensusStrategy,
        agreement: float,
    ) -> None:
        self.passed = passed
        self.votes = votes
        self.strategy = strategy
        self.agreement = agreement

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "votes": self.votes,
            "strategy": self.strategy.value,
            "agreement": self.agreement,
        }


class VerifierConsensus:
    def __init__(self, registry: VerifierRegistry, judges: dict[str, Any] | None = None) -> None:
        self._registry = registry
        # verifier name -> Judge（方案 C）：注入法官后，对 Trace 输入走真实
        # 仲裁而非仿真表决。未注入法官的 verifier 保持向后兼容的仿真路径。
        self._judges: dict[str, Any] = judges or {}

    @property
    def has_judges(self) -> bool:
        """是否配置了任何 Agent-as-a-Judge 法官。

        调用方据此决定是否向 consensus 提交 Trace（真实仲裁）——
        未配置法官的 consensus 无法对轨迹做出可信裁决。
        """
        return bool(self._judges)

    def set_judges(self, judges: dict[str, Any]) -> None:
        """注入/替换 Agent-as-a-Judge 法官映射（verifier name → Judge）。

        v0.46.0 接线用公共 setter，避免调用方直接触碰私有属性。
        """
        self._judges = dict(judges)

    @property
    def judges(self) -> dict[str, Any]:
        """当前装配的法官映射（verifier name → Judge）。"""
        return dict(self._judges)

    def record_call(self, name: str, correct: bool) -> None:
        """在 Trace 裁决后回写 verifier 的 accuracy 校准（v0.47 S13）。

        用一次裁决的「正确与否」更新注册表中该 verifier 的精度统计，
        使共识表决权重随真实表现收敛。未知 verifier 静默忽略。
        """
        if self._registry.get(name) is None:
            return
        self._registry.record_evaluation(name, correct)

    @security_critical
    def evaluate(
        self,
        item: Any,
        strategy: ConsensusStrategy = ConsensusStrategy.SIMPLE_MAJORITY,
        weight_key: str = "accuracy",
        verdict_schema: dict[str, Any] | None = None,
    ) -> ConsensusResult:
        verifiers = self._registry.list_active()
        if not verifiers:
            return ConsensusResult(
                passed=False,
                votes=[],
                strategy=strategy,
                agreement=0.0,
            )

        votes: list[dict[str, Any]] = []
        total_weight = 0.0
        weighted_approvals = 0.0
        approvals = 0

        for v in verifiers:
            vote, verdict = self._call_verifier(v, item, verdict_schema)
            weight = self._get_weight(v, weight_key)
            vote_record: dict[str, Any] = {
                "verifier": v.name,
                "approved": vote,
                "weight": weight,
                "accuracy": v.accuracy,
            }
            if verdict is not None:
                vote_record["verdict"] = verdict
            votes.append(vote_record)
            if vote:
                approvals += 1
                weighted_approvals += weight
            total_weight += weight

        passed = self._apply_strategy(
            approvals,
            len(verifiers),
            weighted_approvals,
            total_weight,
            strategy,
        )
        agreement = weighted_approvals / total_weight if total_weight > 0 else 0.0

        return ConsensusResult(
            passed=passed,
            votes=votes,
            strategy=strategy,
            agreement=agreement,
        )

    def _call_verifier(
        self,
        verifier: VerifierEntry,
        item: Any,
        verdict_schema: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any] | None]:
        # 方案 C：注入法官且输入为轨迹时，走真实仲裁（Agent-as-a-Judge）。
        judge = self._judges.get(verifier.name)
        if isinstance(item, Trace):
            # 轨迹输入必须由真实法官裁决：未注入法官的 verifier 无法
            # 对轨迹做出可信判断，fail-closed 拒绝（不得退回仿真表决，
            # 否则评审可被静默绕过）。
            if judge is None:
                return False, {
                    "error": "no_judge_for_trace",
                    "judge": verifier.name,
                }
            try:
                verdict = judge.arbitrate(item, verdict_schema)
            except Exception:
                # 单法官故障不应中断整体共识：fail-closed 拒绝并标记异常，
                # 由其余法官的加权表决兜底（方案 C 验收：故障降级）。
                return False, {"error": "judge_failed", "judge": verifier.name}
            verdict_dict = verdict.to_dict()
            # FLAG 是风险提示而非否决：计为通过但保留 flag 标记，
            # 供上层决定是否升级人工复核；仅 BLOCK 计为否决。
            approved = verdict.decision in (VerdictDecision.PASS, VerdictDecision.FLAG)
            return approved, verdict_dict

        # 非 Trace 输入（bool/dict）：v0.50 W8-S2 (A10) 无官时 fail-closed。
        # 完全未配置法官（has_judges=False）时移除确定性仿真
        # （ground_truth = bool(item) 可被构造输入操纵，不构成可信仲裁）；
        # 有法官装配时保留向后兼容的仿真降级（调用方应传 Trace 走真实仲裁）。
        if not self._judges:
            return False, {
                "error": "no_judge_for_input",
                "judge": verifier.name,
            }
        ground_truth = bool(item)
        reliability = min(verifier.accuracy, 0.99)
        return ground_truth if reliability > 0.5 else not ground_truth, None

    def _get_weight(self, verifier: VerifierEntry, weight_key: str) -> float:
        if weight_key == "accuracy":
            return max(verifier.accuracy, 0.01)
        if weight_key == "recall":
            return max(verifier.recall, 0.01)
        return 1.0

    def _apply_strategy(
        self,
        approvals: int,
        total: int,
        weighted_approvals: float,
        total_weight: float,
        strategy: ConsensusStrategy,
    ) -> bool:
        if strategy == ConsensusStrategy.UNANIMITY:
            return approvals == total
        if strategy == ConsensusStrategy.WEIGHTED_MAJORITY:
            return weighted_approvals / total_weight > 0.5 if total_weight > 0 else False
        return approvals > total / 2

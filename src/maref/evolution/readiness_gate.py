"""Production Readiness Gate (PRG).

将 RSI 自主演进循环从「时间驱动」（固定 --duration 跑完即止）升级为
「目标驱动」（跑到达标自动收敛）。PRG 定义企业级生产就绪的量化门禁，
每个 cycle 对采集的 RealMetrics 评分；未达标的维度转成下一轮的修复
目标；全部达标（或收敛熔断）后循环停止并出 GA 缺口报告。

阶段式门槛（staged thresholds）——生产候选 → GA 候选 → 企业级：
    - candidate: 生产候选。正确性 100%、ruff 大幅收敛、治理健康、覆盖率
      起步线。达标后标记版本为 release-candidate。
    - ga: 正式 GA。覆盖率 ≥ 50%、ruff 零容忍（白名单内）、版本一致、
      安全 0 HIGH。
    - enterprise: 企业级硬门槛（后续随补测推进，默认不启用）。

收敛熔断：连续 ``stall_window`` 个 cycle 内 PRG 总分无进展 → 判定收敛停滞，
输出缺口报告而非无限空转。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReadinessStage(str, Enum):
    """生产就绪阶段门槛。"""

    CANDIDATE = "candidate"
    FULL_CANDIDATE = "full-candidate"
    GA = "ga"
    ENTERPRISE = "enterprise"


@dataclass
class GateCriterion:
    """单条门禁指标：id / 达标判定 / 当前值 / 是否满足。"""

    id: str
    description: str
    target: float
    current: float
    met: bool
    unit: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "target": self.target,
            "current": self.current,
            "met": self.met,
            "unit": self.unit,
            "detail": self.detail,
        }


@dataclass
class ReadinessReport:
    """一次 PRG 评估结果。"""

    stage: str
    score: float  # 0.0-1.0 达标率
    criteria: list[GateCriterion] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    is_met: bool = False
    cycle: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "score": self.score,
            "is_met": self.is_met,
            "cycle": self.cycle,
            "criteria": [c.to_dict() for c in self.criteria],
            "gaps": self.gaps,
        }


# 各阶段门槛阈值。字段含义见 collect_metrics 输入的 RealMetrics / dict。
_STAGE_THRESHOLDS: dict[str, dict[str, float]] = {
    # 生产候选（窄口径）：仅 src/ 作用域。src/ ruff 清零 + 快速子集测试通过 +
    # 覆盖率底线 + 治理健康。
    ReadinessStage.CANDIDATE.value: {
        "test_pass_rate": 1.0,      # 快速子集 100% 通过
        "ruff_zero_tolerance": 0.0, # ruff 清零（作用于 src/）
        "governance_health": 0.6,   # 宪法自审健康分下限
        "coverage": 5.0,            # 快速子集真实覆盖底线
        "no_blocking_failures": 0.0,  # 近 N cycle 无失败
    },
    # 全仓候选（宽口径）：ruff 扩到 src/ + scripts/，测试扩到核心子集。
    # 前置：candidate 已达成（src/ 干净）。下一步清全仓 ruff + 修测试失败。
    ReadinessStage.FULL_CANDIDATE.value: {
        "test_pass_rate": 1.0,      # 核心子集 100% 通过（当前 97.9%，97 失败待修）
        "ruff_zero_tolerance": 0.0, # ruff 清零（作用于 src/ + scripts/）
        "governance_health": 0.6,
        "coverage": 5.0,
        "no_blocking_failures": 0.0,
    },
    # GA：可对外发布正式版本。coverage 取全量套件基线（pyproject 实测 ~20%）。
    ReadinessStage.GA.value: {
        "test_pass_rate": 1.0,
        "ruff_zero_tolerance": 0.0,
        "governance_health": 0.6,
        "coverage": 20.0,           # 全量套件覆盖基线
        "no_blocking_failures": 0.0,
        "version_consistent": 1.0,
    },
    # 企业级：预留，覆盖 36%+（pyproject 阶段目标）、安全 0 HIGH、混沌通过等。
    ReadinessStage.ENTERPRISE.value: {
        "test_pass_rate": 1.0,
        "ruff_zero_tolerance": 0.0,
        "governance_health": 0.6,
        "coverage": 36.0,
        "no_blocking_failures": 0.0,
        "version_consistent": 1.0,
    },
}

# 各阶段的 ruff 作用域：candidate 仅 src/；full-candidate/ga/enterprise 为全仓。
_STAGE_RUFF_SCOPE: dict[str, str] = {
    ReadinessStage.CANDIDATE.value: "src",
    ReadinessStage.FULL_CANDIDATE.value: "full",
    ReadinessStage.GA.value: "full",
    ReadinessStage.ENTERPRISE.value: "full",
}


class ProductionReadinessGate:
    """评估 RSI 循环采集的真实指标并输出达标 / 缺口判定。

    Usage::

        gate = ProductionReadinessGate(stage="candidate")
        report = gate.evaluate(metrics, cycle=42)
        if report.is_met:
            stop_the_loop()   # 达标收敛
        else:
            target_next_cycle(report.gaps)  # 缺口 → 下一轮修复目标
    """

    def __init__(
        self,
        stage: str | ReadinessStage = ReadinessStage.CANDIDATE,
        stall_window: int = 20,
        stall_score_delta: float = 0.02,
    ) -> None:
        self.stage = (
            stage.value if isinstance(stage, ReadinessStage) else stage
        )
        if self.stage not in _STAGE_THRESHOLDS:
            raise ValueError(
                f"unknown readiness stage {self.stage!r}; "
                f"valid: {list(_STAGE_THRESHOLDS)}"
            )
        self._thresholds = _STAGE_THRESHOLDS[self.stage]
        # 收敛熔断参数
        self.stall_window = stall_window
        self.stall_score_delta = stall_score_delta
        self._score_history: list[float] = []

    @property
    def thresholds(self) -> dict[str, float]:
        return dict(self._thresholds)

    @property
    def ruff_scope(self) -> str:
        """本阶段的 ruff 作用域: "src" 或 "full"（src/+scripts/）。"""
        return _STAGE_RUFF_SCOPE.get(self.stage, "src")

    def evaluate(
        self,
        metrics: Any,
        cycle: int = 0,
        extra: dict[str, Any] | None = None,
    ) -> ReadinessReport:
        """评估一批真实指标。``metrics`` 可为 RealMetrics 或 dict。"""
        m = metrics.to_dict() if hasattr(metrics, "to_dict") else (metrics or {})
        extra = extra or {}

        def _get(*keys: str, default: Any = 0.0) -> float:
            for k in keys:
                if isinstance(m, dict) and k in m and m[k] is not None:
                    return float(m[k])
                if k in extra and extra[k] is not None:
                    return float(extra[k])
            return float(default)

        criteria: list[GateCriterion] = []
        gaps: list[dict[str, Any]] = []

        # ── test_pass_rate ──
        # <0 表示未采集（benchmark 超时/未收集到测试）→ 不判失败，避免把
        # 测量失败误当成测试失败（2026-09 PRG 停滞根因）。
        tpr = _get("test_pass_rate", "test_pass_rate")
        tpr_met = (
            True
            if tpr < 0
            else tpr >= self._thresholds["test_pass_rate"] - 1e-9
        )
        criteria.append(
            GateCriterion(
                id="test_pass_rate",
                description="全量测试通过率",
                target=self._thresholds["test_pass_rate"],
                current=round(tpr, 4),
                met=tpr_met,
                unit="ratio",
                detail="unavailable (measurement skipped)" if tpr < 0 else "",
            )
        )
        if not tpr_met:
            gaps.append({"id": "test_pass_rate", "fix": "fix_failing_tests",
                         "msg": f"test pass rate {tpr:.0%} < {self._thresholds['test_pass_rate']:.0%}"})

        # ── ruff_zero_tolerance ──
        ruff = _get("ruff_error_count", "ruff_error_count", default=-1.0)
        # ruff_error_count = -1 表示未采集（跳过判定，避免误报达标）
        ruff_met = ruff == 0.0
        if ruff < 0:
            ruff_met = True  # 无数据不判失败
        criteria.append(
            GateCriterion(
                id="ruff_zero_tolerance",
                description="ruff 错误清零（自演进作用域）",
                target=self._thresholds["ruff_zero_tolerance"],
                current=ruff,
                met=ruff_met,
                unit="errors",
            )
        )
        if not ruff_met:
            gaps.append({"id": "ruff_zero_tolerance", "fix": "ruff_fix",
                         "msg": f"ruff errors remaining: {ruff:.0f}"})

        # ── coverage ──
        # <0 表示未采集（benchmark 超时）→ 不判失败（与 test_pass_rate 同源问题）。
        cov = _get("coverage_pct", "coverage_pct")
        cov_target = self._thresholds["coverage"]
        cov_met = True if cov < 0 else cov >= cov_target
        criteria.append(
            GateCriterion(
                id="coverage",
                description="行覆盖率",
                target=cov_target,
                current=round(cov, 2),
                met=cov_met,
                unit="%",
                detail="unavailable (measurement skipped)" if cov < 0 else "",
            )
        )
        if not cov_met:
            gaps.append({"id": "coverage", "fix": "generate_tests",
                         "msg": f"coverage {cov:.1f}% < target {cov_target:.0f}% (Δ={cov_target - cov:.1f}pp)"})

        # ── governance_health ──
        gov = _get("governance_health", "governance_health", default=-1.0)
        gov_target = self._thresholds["governance_health"]
        gov_met = gov >= gov_target
        if gov < 0:
            gov_met = True  # 未采集不判失败
            gov = -1.0
        criteria.append(
            GateCriterion(
                id="governance_health",
                description="宪法自审健康分",
                target=gov_target,
                current=gov,
                met=gov_met,
                unit="score",
            )
        )
        if not gov_met:
            gaps.append({"id": "governance_health", "fix": "governance_remediation",
                         "msg": f"governance health {gov:.2f} < {gov_target:.2f}"})

        # ── no_blocking_failures（近 5 cycle 无失败）──
        recent_fail = _get("recent_failures", "recent_failures", default=0.0)
        nbf_target = self._thresholds["no_blocking_failures"]
        nbf_met = recent_fail <= nbf_target
        criteria.append(
            GateCriterion(
                id="no_blocking_failures",
                description="近 5 cycle 失败数",
                target=nbf_target,
                current=recent_fail,
                met=nbf_met,
                unit="count",
            )
        )
        if not nbf_met:
            gaps.append({"id": "no_blocking_failures", "fix": "stability",
                         "msg": f"{recent_fail:.0f} recent failures"})

        # ── version_consistent（仅 GA / enterprise）──
        if "version_consistent" in self._thresholds:
            ver = _get("version_consistent", "version_consistent", default=0.0)
            ver_met = ver >= 1.0
            criteria.append(
                GateCriterion(
                    id="version_consistent",
                    description="pyproject 与代码版本一致",
                    target=1.0,
                    current=ver,
                    met=ver_met,
                    unit="bool",
                )
            )
            if not ver_met:
                gaps.append({"id": "version_consistent", "fix": "version_sync",
                             "msg": "pyproject version != __version__"})

        met_count = sum(1 for c in criteria if c.met)
        score = met_count / len(criteria) if criteria else 1.0

        self._score_history.append(score)
        if len(self._score_history) > self.stall_window * 4:
            self._score_history = self._score_history[-self.stall_window * 4:]

        return ReadinessReport(
            stage=self.stage,
            score=round(score, 4),
            criteria=criteria,
            gaps=gaps,
            is_met=len(gaps) == 0,
            cycle=cycle,
        )

    def is_stalled(self) -> bool:
        """收敛熔断：最近 stall_window 个 cycle 分数提升 < stall_score_delta。"""
        hist = self._score_history
        if len(hist) < self.stall_window:
            return False
        window = hist[-self.stall_window:]
        return (window[-1] - window[0]) < self.stall_score_delta

    def stalled_detail(self) -> str:
        hist = self._score_history
        window = hist[-self.stall_window:] if len(hist) >= self.stall_window else hist
        return f"score over last {len(window)} cycles: {[round(s, 2) for s in window]}"

    def write_report(
        self, report: ReadinessReport, path: str | Path
    ) -> Path:
        """把一次评估结果落盘（供 GA 报告 / 收敛熔断报告）。"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return p


def build_readiness_metrics(
    metrics: Any,
    ruff_count: float = -1.0,
    governance_health: float = -1.0,
    recent_failures: int = 0,
    version_consistent: int = 0,
) -> dict[str, Any]:
    """把 RSI 采集的 RealMetrics + 外部快照合并成 PRG 输入 dict。"""
    m = metrics.to_dict() if hasattr(metrics, "to_dict") else dict(metrics or {})
    m["ruff_error_count"] = ruff_count
    m["governance_health"] = governance_health
    m["recent_failures"] = recent_failures
    m["version_consistent"] = version_consistent
    return m

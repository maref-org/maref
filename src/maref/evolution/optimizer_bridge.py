from __future__ import annotations

import logging
from typing import Any

from drift_guard.policy_sandbox import PipelineConfig, PolicyChange, PolicyChangeType, PolicySandbox
from maref.recursive.self_diagnostician import DiagnosisReport, RiskLevel
from maref.recursive.self_observer import SystemSnapshot
from maref.recursive.self_optimizer import OptimizationHypothesis, SelfOptimizer

logger = logging.getLogger(__name__)


class OptimizerEvolutionBridge:
    """Bridges SelfOptimizer (diagnosis-based optimization) with RecursiveEvolutionEngine.

    Converts DiagnosisReport signals into enriched optimization hypotheses,
    and adopted hypotheses into PolicySandbox PolicyChange proposals.

    Usage:
        bridge = OptimizerEvolutionBridge()
        hypotheses = bridge.diagnose_to_hypotheses(report, snapshot)
        for h in hypotheses:
            result = optimizer.run_experiment(h)
            if optimizer.adopt_if_gain(h, result):
                change = bridge.adopt_to_policy_change(h, sandbox)
    """

    def __init__(self, optimizer: SelfOptimizer | None = None) -> None:
        self._optimizer = optimizer or SelfOptimizer()

    def diagnose_to_hypotheses(
        self,
        report: DiagnosisReport,
        snapshot: SystemSnapshot,
    ) -> list[OptimizationHypothesis]:
        """Generate optimization hypotheses from diagnosis signals.

        Each critical/warning probe produces one hypothesis targeting
        the relevant subsystem (tests, latency, module deps, etc.).
        """
        hypotheses: list[OptimizationHypothesis] = []

        ctx = report.diagnostic_context
        risk = report.risk_matrix

        # ── Entropy (test failure) → test reliability hypothesis ──────
        if risk.get("entropy") in (RiskLevel.CRITICAL, RiskLevel.WARNING):
            entropy_val = ctx.get("entropy_value", 0)
            hypotheses.append(
                OptimizationHypothesis(
                    hypothesis_id=f"entropy_{snapshot.timestamp}",
                    description=(
                        f"Entropy level {entropy_val:.1f}: reduce test failures "
                        f"({ctx.get('entropy_test_failure_ratio', 0):.1%} failure rate)"
                    ),
                    target_module="tests",
                )
            )

        # ── Latency → performance optimization hypothesis ────────────
        if risk.get("latency") in (RiskLevel.CRITICAL, RiskLevel.WARNING):
            latency_ms = ctx.get("latency_value", 0)
            hypotheses.append(
                OptimizationHypothesis(
                    hypothesis_id=f"latency_{snapshot.timestamp}",
                    description=(
                        f"Latency {latency_ms:.0f}ms: optimize slow tests "
                        f"or reduce module complexity"
                    ),
                    target_module="execution",
                )
            )

        # ── Anomaly (source complexity) → module split hypothesis ─────
        if risk.get("anomaly") in (RiskLevel.CRITICAL, RiskLevel.WARNING):
            source_count = ctx.get("source_file_count", 0)
            hypotheses.append(
                OptimizationHypothesis(
                    hypothesis_id=f"complexity_{snapshot.timestamp}",
                    description=(
                        f"Source file count {source_count}: "
                        f"refactor large modules into smaller units"
                    ),
                    target_module="architecture",
                )
            )

        # ── KG (module graph orphan ratio) → dependency clean-up ─────
        if risk.get("knowledge_graph") in (RiskLevel.CRITICAL, RiskLevel.WARNING):
            hypotheses.append(
                OptimizationHypothesis(
                    hypothesis_id=f"kg_{snapshot.timestamp}",
                    description=(
                        "Knowledge graph orphan ratio elevated: "
                        "remove or re-integrate orphaned modules"
                    ),
                    target_module="knowledge_graph",
                )
            )

        # ── Desktop / Playwright → desktop agent health ──────────────
        if (
            risk.get("desktop") == RiskLevel.CRITICAL
            or risk.get("playwright") == RiskLevel.CRITICAL
        ):
            hypotheses.append(
                OptimizationHypothesis(
                    hypothesis_id=f"desktop_{snapshot.timestamp}",
                    description=(
                        "Desktop agent or Playwright probe CRITICAL: "
                        "ensure browser engine is installed and pool is healthy"
                    ),
                    target_module="desktop",
                )
            )

        # ── GUI Build → build pipeline health ────────────────────────
        if risk.get("gui_build") in (RiskLevel.CRITICAL, RiskLevel.WARNING):
            hypotheses.append(
                OptimizationHypothesis(
                    hypothesis_id=f"gui_build_{snapshot.timestamp}",
                    description=(
                        "GUI build quality degraded: fix TypeScript errors, "
                        "lint failures, or stale dependencies"
                    ),
                    target_module="gui",
                )
            )

        return hypotheses

    def adopt_to_policy_change(
        self,
        hypothesis: OptimizationHypothesis,
        sandbox: PolicySandbox,
    ) -> PolicyChange | None:
        """Convert an adopted hypothesis to a PolicySandbox change.

        Returns None if the hypothesis cannot be translated to a
        known policy change type.
        """
        target = hypothesis.target_module

        if target == "tests":
            return sandbox.propose_change(
                change_type=PolicyChangeType.THRESHOLD_ADJUSTMENT,
                description=hypothesis.description,
                new_config=PipelineConfig(
                    hellinger_warning=0.15,
                    hellinger_critical=0.4,
                ),
            )
        if target == "execution":
            return sandbox.propose_change(
                change_type=PolicyChangeType.THRESHOLD_ADJUSTMENT,
                description=hypothesis.description,
                new_config=PipelineConfig(
                    review_timeout_seconds=600.0,
                ),
            )
        if target == "architecture":
            return sandbox.propose_change(
                change_type=PolicyChangeType.STATE_MACHINE_RULE,
                description=hypothesis.description,
                new_config=PipelineConfig(
                    check_interval_seconds=120.0,
                ),
            )
        if target == "knowledge_graph":
            return sandbox.propose_change(
                change_type=PolicyChangeType.MONITOR_CONFIG,
                description=hypothesis.description,
                new_config=PipelineConfig(
                    reset_on_critical=False,
                ),
            )
        if target in ("desktop", "gui"):
            return sandbox.propose_change(
                change_type=PolicyChangeType.ACTION_POLICY,
                description=hypothesis.description,
                new_config=PipelineConfig(
                    auto_action_threshold=drift_guard_severity("MEDIUM"),
                ),
            )

        logger.info("No policy change mapping for target=%s", target)
        return None


def drift_guard_severity(name: str) -> Any:
    """Lazy import of DriftSeverity to avoid circular imports."""
    from drift_guard.types import DriftSeverity

    return getattr(DriftSeverity, name.upper(), DriftSeverity.MEDIUM)

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maref.recursive.self_observer import SystemSnapshot

from maref.observation.probes import (
    AnomalyProbe,
    DesktopProbe,
    EntropyProbe,
    GUIBuildProbe,
    KGProbe,
    LatencyProbe,
    OscillationProbe,
    PlaywrightProbe,
    ProbeReading,
    ProbeSeverity,
)


class RiskLevel(Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DiagnosisReport:
    snapshot_ref: str
    probe_results: dict[str, list[ProbeReading]] = field(default_factory=dict)
    risk_matrix: dict[str, RiskLevel] = field(default_factory=dict)
    cb_status: str = "CLOSED"
    recommendations: list[str] = field(default_factory=list)
    overall_risk: RiskLevel = RiskLevel.NORMAL
    # Enhanced diagnostic context
    diagnostic_context: dict[str, float] = field(default_factory=dict)


class SelfDiagnostician:
    """Diagnostician that uses real system metrics for risk assessment.

    Each probe is calibrated with sensible thresholds:
      - entropy:  test failure ratio × 10 (threshold 3.0 critical, 1.5 warning)
      - latency:  real test collection/execution duration in seconds
      - anomaly:  source file count (proxy for codebase complexity)
      - kg:       orphan ratio in module dependency graph
      - oscillation: tag frequency (proxy for release churn)
    """

    def __init__(self) -> None:
        self._entropy_probe = EntropyProbe(primary_threshold=3.0, shadow_threshold=1.5)
        self._anomaly_probe = AnomalyProbe(primary_threshold=3000, shadow_threshold=1500)
        self._latency_probe = LatencyProbe(primary_threshold=60000.0, shadow_threshold=30000.0)
        self._kg_probe = KGProbe(primary_threshold=0.8)
        self._oscillation_probe = OscillationProbe(primary_threshold=5.0, shadow_threshold=2.0)
        self._playwright_probe = PlaywrightProbe(critical_threshold=0.0)
        self._desktop_probe = DesktopProbe(critical_threshold=0.3, warning_threshold=0.6)
        self._gui_build_probe = GUIBuildProbe(critical_threshold=0.3, warning_threshold=0.6)
        self._cb_state = "CLOSED"
        self._trip_count = 0
        self._blocked = False

    @property
    def cb_state(self) -> str:
        return self._cb_state

    def diagnose(self, snapshot: SystemSnapshot) -> DiagnosisReport:
        probe_results: dict[str, list[ProbeReading]] = {}
        diagnostic_context: dict[str, float] = {}

        # ── Entropy: test failure ratio ─────────────────────────
        total_tests = max(snapshot.test_stats.get("total", 1), 1)
        failed = snapshot.test_stats.get("failed", 0)
        entropy_val = failed / total_tests * 10.0
        diagnostic_context["entropy_test_failure_ratio"] = round(failed / total_tests, 4)
        diagnostic_context["entropy_value"] = round(entropy_val, 2)
        probe_results["entropy"] = self._entropy_probe.read(entropy=entropy_val)

        # ── Anomaly: source file count (codebase complexity) ────
        source_count = snapshot.source_file_count
        diagnostic_context["source_file_count"] = source_count
        diagnostic_context["anomaly_value"] = source_count
        probe_results["anomaly"] = self._anomaly_probe.read(anomaly_count=source_count)

        # ── Latency: real test execution duration ───────────────
        test_duration = snapshot.test_stats.get("duration_ms", 0)
        latency_ms = max(test_duration, float(source_count * 0.5))
        diagnostic_context["latency_test_duration_ms"] = round(latency_ms, 1)
        diagnostic_context["latency_value"] = round(latency_ms, 1)
        probe_results["latency"] = self._latency_probe.read(latency_ms=latency_ms)

        # ── Knowledge Graph: dependency health ────────────────────
        kg_nodes = snapshot.source_file_count if snapshot.source_file_count > 0 else 0
        total_edges = sum(len(deps) for deps in snapshot.module_graph.values())
        diagnostic_context["kg_nodes"] = kg_nodes
        diagnostic_context["kg_relation_density"] = round(total_edges / max(kg_nodes, 1), 4)
        probe_results["kg"] = self._kg_probe.read(
            total_nodes=float(kg_nodes),
            relation_count=float(total_edges),
        )

        # ── Oscillation: release tag frequency ──────────────────
        tags = len(snapshot.git_stats.get("tags", []))
        oscillation_val = float(tags) / 10.0
        diagnostic_context["oscillation_tag_count"] = tags
        diagnostic_context["oscillation_value"] = round(oscillation_val, 2)
        probe_results["oscillation"] = self._oscillation_probe.read(
            oscillation_count=oscillation_val
        )

        # ── Playwright: browser engine install status ──────────
        playwright_reading = self._playwright_probe.measure()
        probe_results["playwright"] = [playwright_reading]
        diagnostic_context["playwright_installed"] = playwright_reading.context.get("installed", False)
        diagnostic_context["playwright_browsers"] = sum(
            playwright_reading.context.get(k, False)
            for k in ("chromium_available", "firefox_available", "webkit_available")
        )

        # ── Desktop: desktop agent runtime health ─────────────
        desktop_reading = self._desktop_probe.measure()
        probe_results["desktop"] = [desktop_reading]
        diagnostic_context["desktop_active_sessions"] = desktop_reading.context.get(
            "active_sessions", 0
        )
        diagnostic_context["desktop_pool_available"] = desktop_reading.context.get(
            "pool_available", False
        )

        # ── GUI Build: Electron build health ──────────────────
        gui_reading = self._gui_build_probe.measure()
        probe_results["gui_build"] = [gui_reading]
        diagnostic_context["gui_build_value"] = gui_reading.value
        diagnostic_context["gui_lint_passes"] = gui_reading.context.get("lint_passes", False)
        diagnostic_context["gui_build_success"] = gui_reading.context.get("build_success", False)
        diagnostic_context["gui_ts_errors"] = gui_reading.context.get("ts_errors", 0)

        risk_matrix = self._build_risk_matrix(probe_results)

        return DiagnosisReport(
            snapshot_ref=f"snapshot_{snapshot.timestamp}",
            probe_results=probe_results,
            risk_matrix=risk_matrix,
            cb_status=self._cb_state,
            recommendations=self._generate_recommendations(
                probe_results, risk_matrix, diagnostic_context
            ),
            overall_risk=self._overall_risk(risk_matrix),
            diagnostic_context=diagnostic_context,
        )

    def _build_risk_matrix(
        self, probe_results: dict[str, list[ProbeReading]]
    ) -> dict[str, RiskLevel]:
        matrix: dict[str, RiskLevel] = {}
        for probe_name, readings in probe_results.items():
            if not readings:
                matrix[probe_name] = RiskLevel.NORMAL
                continue
            severities = [r.severity for r in readings]
            if ProbeSeverity.CRITICAL in severities:
                matrix[probe_name] = RiskLevel.CRITICAL
            elif ProbeSeverity.WARNING in severities:
                matrix[probe_name] = RiskLevel.WARNING
            else:
                matrix[probe_name] = RiskLevel.NORMAL
        return matrix

    @staticmethod
    def _overall_risk(risk_matrix: dict[str, RiskLevel]) -> RiskLevel:
        values = list(risk_matrix.values())
        if RiskLevel.CRITICAL in values:
            return RiskLevel.CRITICAL
        if RiskLevel.WARNING in values:
            return RiskLevel.WARNING
        return RiskLevel.NORMAL

    @staticmethod
    def _generate_recommendations(
        probe_results: dict[str, list[ProbeReading]],
        risk_matrix: dict[str, RiskLevel],
        diagnostic_context: dict[str, float] | None = None,
    ) -> list[str]:
        ctx = diagnostic_context or {}
        recommendations: list[str] = []

        for probe_name, level in risk_matrix.items():
            if level == RiskLevel.CRITICAL:
                if probe_name == "entropy":
                    ratio = ctx.get("entropy_test_failure_ratio", 0)
                    recommendations.append(
                        f"[entropy] CRITICAL: test failure ratio={ratio:.1%} — 优先修复失败的测试用例"
                    )
                elif probe_name == "latency":
                    ms = ctx.get("latency_test_duration_ms", 0)
                    recommendations.append(
                        f"[latency] CRITICAL: test duration={ms:.0f}ms — 检查慢测试和性能回退"
                    )
                elif probe_name == "anomaly":
                    count = ctx.get("source_file_count", 0)
                    recommendations.append(
                        f"[anomaly] CRITICAL: source files={count} — 代码库复杂度高，考虑模块拆分"
                    )
                elif probe_name == "knowledge_graph":
                    ratio = ctx.get("kg_orphan_ratio", 0)
                    recommendations.append(
                        f"[knowledge_graph] CRITICAL: orphan ratio={ratio:.1%} — 检测到大量孤立模块"
                    )
                elif probe_name == "oscillation":
                    val = ctx.get("oscillation_value", 0)
                    recommendations.append(
                        f"[oscillation] CRITICAL: oscillation rate={val:.1f} — 版本发布频率异常"
                    )
                elif probe_name == "playwright":
                    recommendations.append(
                        "[playwright] CRITICAL: Playwright 未安装或无可用浏览器引擎 — 桌面自动化将不可用"
                    )
                elif probe_name == "desktop":
                    recommendations.append(
                        "[desktop] CRITICAL: 桌面代理不可用 — 浏览器会话池为空或 Playwright 未安装"
                    )
                elif probe_name == "gui_build":
                    recommendations.append(
                        "[gui_build] CRITICAL: GUI 构建完全失败 — 建议立即修复构建流程"
                    )
                else:
                    recommendations.append(f"[{probe_name}] CRITICAL: 建议立即修复")

            elif level == RiskLevel.WARNING:
                if probe_name == "entropy":
                    recommendations.append("[entropy] WARNING: 测试失败率上升，建议关注")
                elif probe_name == "latency":
                    recommendations.append("[latency] WARNING: 测试耗时偏高，建议优化")
                elif probe_name == "kg":
                    recommendations.append("[knowledge_graph] WARNING: 模块依赖结构趋于碎片化")
                elif probe_name == "anomaly":
                    recommendations.append("[anomaly] WARNING: 代码量增长较快")
                elif probe_name == "oscillation":
                    recommendations.append("[oscillation] WARNING: 发布频率偏高")
                elif probe_name == "gui_build":
                    recommendations.append(
                        "[gui_build] WARNING: GUI 构建质量下降 — 存在 TypeScript 错误或 lint 失败"
                    )
                else:
                    recommendations.append(f"[{probe_name}] WARNING: 建议监控")

        if not recommendations:
            recommendations.append("系统正常，无异常")
        return recommendations

    def attach_circuit_breaker(self) -> None:
        self._cb_state = "CLOSED"
        self._blocked = False

    def check_and_trip(self, report: DiagnosisReport) -> bool:
        critical_count = sum(1 for v in report.risk_matrix.values() if v == RiskLevel.CRITICAL)
        if self._cb_state == "OPEN":
            self._blocked = True
            return False
        if critical_count >= 1:
            self._trip_count += 1
            if self._trip_count > 3:
                self._cb_state = "OPEN"
                self._blocked = True
                return False
            return True
        if self._trip_count > 0:
            self._trip_count -= 1
        return True

    def reset_to_half_open(self) -> None:
        if self._cb_state == "OPEN":
            self._cb_state = "HALF_OPEN"
            self._blocked = False

    def close(self) -> None:
        self._cb_state = "CLOSED"
        self._blocked = False
        self._trip_count = 0

    def is_blocked(self) -> bool:
        return self._blocked

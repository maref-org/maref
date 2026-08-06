"""
Behavior Monitor - Emergent Behavior Detection (S7)

Models agent behavior baselines and detects anomalies,
including emergent multi-agent interaction risks.
"""

from __future__ import annotations

import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BehaviorBaseline:
    agent_id: str
    avg_ops_per_minute: float = 0.0
    avg_chain_depth: float = 0.0
    tool_usage_distribution: dict[str, float] = field(default_factory=dict)
    sample_count: int = 0
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "avg_ops_per_minute": round(self.avg_ops_per_minute, 2),
            "avg_chain_depth": round(self.avg_chain_depth, 2),
            "tool_usage_distribution": self.tool_usage_distribution,
            "sample_count": self.sample_count,
        }


@dataclass
class BehaviorAnomaly:
    agent_id: str
    severity: str  # low, medium, high, critical
    deviation_sigma: float
    metric_name: str
    expected_value: float
    actual_value: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "severity": self.severity,
            "deviation_sigma": round(self.deviation_sigma, 2),
            "metric": self.metric_name,
            "expected": round(self.expected_value, 2),
            "actual": round(self.actual_value, 2),
        }


class BehaviorMonitor:
    """
    Monitors agent behavior for anomalies and emergent patterns.

    Features:
    - Per-agent behavior baseline learning
    - Statistical anomaly detection (3-sigma rule)
    - Multi-agent emergent behavior detection
    """

    def __init__(self, sigma_threshold: float = 3.0) -> None:
        self.sigma_threshold = sigma_threshold
        self._baselines: dict[str, BehaviorBaseline] = {}
        self._samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._max_samples = 100

    def record_activity(
        self,
        agent_id: str,
        ops_count: int = 0,
        chain_depth: int = 0,
        tools_used: list[str] | None = None,
    ) -> None:
        """Record an agent activity sample."""
        sample = {
            "timestamp": time.time(),
            "ops_count": ops_count,
            "chain_depth": chain_depth,
            "tools_used": tools_used or [],
        }
        self._samples[agent_id].append(sample)
        if len(self._samples[agent_id]) > self._max_samples:
            self._samples[agent_id].pop(0)

        # Update baseline every 10 samples
        if len(self._samples[agent_id]) % 10 == 0:
            self._update_baseline(agent_id)

    def _update_baseline(self, agent_id: str) -> None:
        """Update behavior baseline from samples."""
        samples = self._samples[agent_id]
        if len(samples) < 5:
            return

        ops_counts = [s["ops_count"] for s in samples]
        chain_depths = [s["chain_depth"] for s in samples]

        # Tool usage distribution
        tool_counts: dict[str, int] = defaultdict(int)
        total_tools = 0
        for s in samples:
            for tool in s["tools_used"]:
                tool_counts[tool] += 1
                total_tools += 1

        tool_dist = {}
        if total_tools > 0:
            tool_dist = {tool: count / total_tools for tool, count in tool_counts.items()}

        self._baselines[agent_id] = BehaviorBaseline(
            agent_id=agent_id,
            avg_ops_per_minute=statistics.mean(ops_counts),
            avg_chain_depth=statistics.mean(chain_depths),
            tool_usage_distribution=tool_dist,
            sample_count=len(samples),
        )

    def detect_anomalies(self, agent_id: str) -> list[BehaviorAnomaly]:
        """Detect anomalies for a single agent."""
        baseline = self._baselines.get(agent_id)
        if not baseline or baseline.sample_count < 10:
            return []

        samples = self._samples[agent_id][-10:]  # Last 10 samples
        anomalies: list[BehaviorAnomaly] = []

        # Use baseline samples (excluding current window) for std calculation
        # to avoid anomalous samples inflating the standard deviation
        baseline_samples = (
            self._samples[agent_id][:-10]
            if len(self._samples[agent_id]) > 20
            else self._samples[agent_id][:-5]
        )

        # Check ops rate
        ops_counts = [s["ops_count"] for s in samples]
        if len(ops_counts) >= 2:
            mean_ops = baseline.avg_ops_per_minute
            baseline_ops = [s["ops_count"] for s in baseline_samples]
            std_ops = statistics.stdev(baseline_ops) if len(baseline_ops) >= 2 else 1.0
            current_ops = statistics.mean(ops_counts)
            if std_ops > 0:
                sigma = abs(current_ops - mean_ops) / std_ops
                if sigma > self.sigma_threshold:
                    anomalies.append(
                        BehaviorAnomaly(
                            agent_id=agent_id,
                            severity=self._severity_from_sigma(sigma),
                            deviation_sigma=sigma,
                            metric_name="ops_per_minute",
                            expected_value=mean_ops,
                            actual_value=current_ops,
                        )
                    )

        # Check chain depth
        chain_depths = [s["chain_depth"] for s in samples]
        if len(chain_depths) >= 2:
            mean_depth = baseline.avg_chain_depth
            baseline_depths = [s["chain_depth"] for s in baseline_samples]
            std_depth = statistics.stdev(baseline_depths) if len(baseline_depths) >= 2 else 1.0
            current_depth = statistics.mean(chain_depths)
            if std_depth > 0:
                sigma = abs(current_depth - mean_depth) / std_depth
                if sigma > self.sigma_threshold:
                    anomalies.append(
                        BehaviorAnomaly(
                            agent_id=agent_id,
                            severity=self._severity_from_sigma(sigma),
                            deviation_sigma=sigma,
                            metric_name="chain_depth",
                            expected_value=mean_depth,
                            actual_value=current_depth,
                        )
                    )

        return anomalies

    def detect_emergent_behavior(self, agent_ids: list[str]) -> list[BehaviorAnomaly]:
        """Detect emergent behavior when multiple agents are anomalous simultaneously."""
        all_anomalies: list[BehaviorAnomaly] = []
        for agent_id in agent_ids:
            all_anomalies.extend(self.detect_anomalies(agent_id))

        # If 2+ agents have high/critical anomalies simultaneously, escalate
        high_anomaly_agents = {
            a.agent_id for a in all_anomalies if a.severity in ("high", "critical")
        }

        emergent: list[BehaviorAnomaly] = []
        if len(high_anomaly_agents) >= 2:
            for agent_id in high_anomaly_agents:
                for a in all_anomalies:
                    if a.agent_id == agent_id:
                        emergent.append(
                            BehaviorAnomaly(
                                agent_id=agent_id,
                                severity="critical",
                                deviation_sigma=a.deviation_sigma * 2,
                                metric_name=f"emergent_{a.metric_name}",
                                expected_value=a.expected_value,
                                actual_value=a.actual_value,
                            )
                        )

        return emergent

    def _severity_from_sigma(self, sigma: float) -> str:
        if sigma > 5:
            return "critical"
        elif sigma > 4:
            return "high"
        elif sigma > 3:
            return "medium"
        return "low"

    def get_baseline(self, agent_id: str) -> BehaviorBaseline | None:
        return self._baselines.get(agent_id)

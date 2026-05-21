"""
MAREF Discovery Engine

Cross-temporal analysis and hypothesis generation for continuous autoresearch.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from research.knowledge_graph import KnowledgeGraph, KnowledgeNode


@dataclass
class TemporalPattern:
    """A pattern detected across multiple time periods."""

    pattern_type: str
    description: str
    confidence: float
    supporting_evidence: list[str] = field(default_factory=list)


@dataclass
class ContradictionAlert:
    """Alert for contradictions between findings."""

    severity: str  # "low", "medium", "high"
    description: str
    conflicting_nodes: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class GeneratedHypothesis:
    """A hypothesis generated from observed patterns."""

    hypothesis: str
    based_on: list[str]
    testable: bool
    suggested_experiment: str = ""


class DiscoveryEngine:
    """
    Analyzes research findings across time to discover patterns,
    contradictions, and generate new hypotheses.
    """

    def __init__(self, knowledge_graph: KnowledgeGraph | None = None) -> None:
        self._kg = knowledge_graph or KnowledgeGraph()

    def analyze_trends(self, metric_name: str, window_size: int = 7) -> dict[str, Any]:
        """
        Analyze trends in a specific metric over time.

        Args:
            metric_name: Name of the metric to analyze
            window_size: Number of data points to consider

        Returns:
            Trend analysis results
        """
        # Query knowledge graph for metric nodes
        nodes = self._kg.query(metric_name)
        metric_nodes = [n for n in nodes if n.type == "metric"]

        if len(metric_nodes) < 3:
            return {"trend": "insufficient_data", "confidence": 0.0}

        # Sort by timestamp
        metric_nodes.sort(key=lambda n: n.timestamp)
        recent = metric_nodes[-window_size:]

        # Extract values
        values = []
        for node in recent:
            if "value" in node.metadata:
                values.append(float(node.metadata["value"]))

        if len(values) < 3:
            return {"trend": "insufficient_values", "confidence": 0.0}

        # Calculate trend
        first_half = statistics.mean(values[:len(values)//2])
        second_half = statistics.mean(values[len(values)//2:])

        diff = second_half - first_half
        threshold = abs(first_half) * 0.1 if first_half != 0 else 0.01

        if abs(diff) < threshold:
            trend = "stable"
        elif diff > 0:
            trend = "increasing"
        else:
            trend = "decreasing"

        # Calculate confidence based on variance
        if len(values) > 1:
            try:
                variance = statistics.variance(values)
                confidence = max(0.0, 1.0 - variance / (abs(statistics.mean(values)) + 0.001))
            except statistics.StatisticsError:
                confidence = 0.5
        else:
            confidence = 0.5

        return {
            "trend": trend,
            "confidence": confidence,
            "change_rate": diff / max(abs(first_half), 0.001),
            "sample_size": len(values),
        }

    def detect_contradictions(self) -> list[ContradictionAlert]:
        """
        Detect contradictions between findings in the knowledge graph.

        Returns:
            List of contradiction alerts
        """
        alerts = []
        findings = [
            n for n in self._kg._nodes.values()
            if n.type == "finding"
        ]

        # Simple contradiction detection: look for opposing statements
        for i, f1 in enumerate(findings):
            for f2 in findings[i+1:]:
                # Check if findings are about the same topic but disagree
                if self._are_related(f1, f2) and self._are_opposing(f1, f2):
                    alert = ContradictionAlert(
                        severity="medium",
                        description=f"矛盾: '{f1.content}' 与 '{f2.content}'",
                        conflicting_nodes=[f1.id, f2.id],
                        recommendation="运行针对性实验解决矛盾",
                    )
                    alerts.append(alert)

        return alerts

    def generate_hypotheses(self) -> list[GeneratedHypothesis]:
        """
        Generate testable hypotheses from observed patterns.

        Returns:
            List of generated hypotheses
        """
        hypotheses = []

        # Find correlations between different metrics
        findings = [n for n in self._kg._nodes.values() if n.type == "finding"]

        # Simple hypothesis: if two metrics often appear together, they may be correlated
        metric_pairs = self._find_metric_pairs(findings)

        for m1, m2, count in metric_pairs:
            if count >= 3:  # Appeared together at least 3 times
                hyp = GeneratedHypothesis(
                    hypothesis=f"{m1}与{m2}呈正相关",
                    based_on=[m1, m2],
                    testable=True,
                    suggested_experiment=f"controlled_experiment_{m1}_{m2}",
                )
                hypotheses.append(hyp)

        # Generate hypotheses from trend analysis
        for metric in ["convergence_rate", "stability_rate", "safety_rate", "f1_score"]:
            trend = self.analyze_trends(metric)
            if trend["trend"] != "insufficient_data" and trend["confidence"] > 0.6:
                if trend["trend"] == "increasing":
                    hyp = GeneratedHypothesis(
                        hypothesis=f"{metric}呈现持续改善趋势",
                        based_on=[metric],
                        testable=True,
                        suggested_experiment=f"verify_{metric}_trend",
                    )
                    hypotheses.append(hyp)
                elif trend["trend"] == "decreasing":
                    hyp = GeneratedHypothesis(
                        hypothesis=f"{metric}正在退化，需要干预",
                        based_on=[metric],
                        testable=True,
                        suggested_experiment=f"investigate_{metric}_degradation",
                    )
                    hypotheses.append(hyp)

        # Generate hypotheses from contradictions
        contradictions = self.detect_contradictions()
        for contradiction in contradictions[:3]:  # Limit to top 3
            hyp = GeneratedHypothesis(
                hypothesis=f"需要解决: {contradiction.description}",
                based_on=contradiction.conflicting_nodes,
                testable=True,
                suggested_experiment="contradiction_resolution",
            )
            hypotheses.append(hyp)

        return hypotheses

    def _are_related(self, node1: KnowledgeNode, node2: KnowledgeNode) -> bool:
        """Check if two nodes are about the same topic."""
        # Simple check: share at least 2 keywords
        words1 = set(node1.content.lower().split())
        words2 = set(node2.content.lower().split())
        shared = words1 & words2
        return len(shared) >= 2

    def _are_opposing(self, node1: KnowledgeNode, node2: KnowledgeNode) -> bool:
        """Check if two findings contradict each other."""
        # Simple heuristic: check for opposing keywords
        content1 = node1.content.lower()
        content2 = node2.content.lower()

        opposites = [
            ("increases", "decreases"),
            ("improves", "degrades"),
            ("stable", "unstable"),
            ("converges", "diverges"),
            ("positive", "negative"),
        ]

        for word1, word2 in opposites:
            if (word1 in content1 and word2 in content2) or \
               (word2 in content1 and word1 in content2):
                return True

        return False

    def _find_metric_pairs(self, findings: list[KnowledgeNode]) -> list[tuple[str, str, int]]:
        """Find pairs of metrics that frequently appear together."""
        from collections import Counter

        pairs = []
        for finding in findings:
            metrics = finding.metadata.get("metrics", [])
            if len(metrics) >= 2:
                for i, m1 in enumerate(metrics):
                    for m2 in metrics[i+1:]:
                        pairs.append(tuple(sorted([m1, m2])))

        counter = Counter(pairs)
        return [(m1, m2, count) for (m1, m2), count in counter.most_common(10)]

    def get_insights(self) -> list[str]:
        """Get high-level insights from the knowledge graph."""
        insights = []

        # Check for trends
        trends = self.analyze_trends("convergence_rate")
        if trends["trend"] != "insufficient_data":
            insights.append(
                f"收敛率{trends['trend']}（置信度: {trends['confidence']:.2f}）"
            )

        # Check for contradictions
        contradictions = self.detect_contradictions()
        if contradictions:
            insights.append(
                f"发现 {len(contradictions)} 个矛盾需要调查"
            )

        # Check for open questions
        open_q = self._kg.get_open_questions()
        if open_q:
            insights.append(
                f"{len(open_q)} 个假设待验证"
            )

        return insights

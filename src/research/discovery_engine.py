import statistics
from dataclasses import dataclass
from typing import Any

# mypy: ignore-errors
from research.knowledge_graph import KnowledgeGraph


@dataclass
class TemporalPattern:
    metric: str
    trend: str
    slope: float
    confidence: float
    period: tuple[str, str]

@dataclass
class ContradictionAlert:
    metric: str
    source_a: str
    source_b: str
    value_a: float
    value_b: float
    severity: str

@dataclass
class GeneratedHypothesis:
    statement: str
    supporting_evidence: list[str]
    confidence: float
    related_metrics: list[str]

class DiscoveryEngine:

    def __init__(self, knowledge_graph: KnowledgeGraph) -> None:
        self.kg = knowledge_graph
        self._pattern_cache: dict[str, list[TemporalPattern]] = {}
        self._contradiction_cache: dict[str, list[ContradictionAlert]] = {}

    async def analyze_trends(self, metrics: list[str], window: int=30) -> dict[str, list[TemporalPattern]]:
        try:
            results: dict[str, list[TemporalPattern]] = {}
            for metric in metrics:
                nodes = self.kg.query(metric=metric, limit=window)
                if len(nodes) < 3:
                    results[metric] = []
                    continue
                values = [n.value for n in nodes if n.value is not None]
                timestamps = [n.timestamp for n in nodes if n.value is not None]
                if len(values) < 3:
                    results[metric] = []
                    continue
                (slope, _) = statistics.linear_regression(list(range(len(values))), values)
                trend = 'up' if slope > 0.01 else 'down' if slope < -0.01 else 'stable'
                confidence = min(1.0, abs(slope) * 10)
                pattern = TemporalPattern(metric=metric, trend=trend, slope=slope, confidence=confidence, period=(timestamps[0], timestamps[-1]))
                results[metric] = [pattern]
            self._pattern_cache.update(results)
            return results
        except Exception:
            return {}

    async def detect_contradictions(self, metrics: list[str]) -> dict[str, list[ContradictionAlert]]:
        try:
            results: dict[str, list[ContradictionAlert]] = {}
            for metric in metrics:
                nodes = self.kg.query(metric=metric, limit=100)
                if len(nodes) < 2:
                    results[metric] = []
                    continue
                alerts: list[ContradictionAlert] = []
                for i in range(len(nodes)):
                    for j in range(i + 1, len(nodes)):
                        (a, b) = (nodes[i], nodes[j])
                        if a.value is None or b.value is None:
                            continue
                        if abs(a.value - b.value) > 0.5 * max(abs(a.value), abs(b.value)):
                            severity = 'high' if abs(a.value - b.value) > 0.8 * max(abs(a.value), abs(b.value)) else 'medium'
                            alert = ContradictionAlert(metric=metric, source_a=a.source, source_b=b.source, value_a=a.value, value_b=b.value, severity=severity)
                            alerts.append(alert)
                results[metric] = alerts
            self._contradiction_cache.update(results)
            return results
        except Exception:
            return {}

    async def generate_hypotheses(self, metrics: list[str]) -> list[GeneratedHypothesis]:
        try:
            hypotheses: list[GeneratedHypothesis] = []
            for i in range(len(metrics)):
                for j in range(i + 1, len(metrics)):
                    (m1, m2) = (metrics[i], metrics[j])
                    if not self._are_related(m1, m2):
                        continue
                    patterns1 = self._pattern_cache.get(m1, [])
                    patterns2 = self._pattern_cache.get(m2, [])
                    if not patterns1 or not patterns2:
                        continue
                    (p1, p2) = (patterns1[0], patterns2[0])
                    if p1.trend == p2.trend:
                        statement = f'{m1} and {m2} show correlated {p1.trend}ward trends'
                        evidence = [f'{m1}: {p1.trend} (slope={p1.slope:.3f})', f'{m2}: {p2.trend} (slope={p2.slope:.3f})']
                        confidence = (p1.confidence + p2.confidence) / 2
                        hypothesis = GeneratedHypothesis(statement=statement, supporting_evidence=evidence, confidence=confidence, related_metrics=[m1, m2])
                        hypotheses.append(hypothesis)
            return hypotheses
        except Exception:
            return []

    def _are_related(self, m1: str, m2: str) -> bool:
        try:
            nodes1 = self.kg.query(metric=m1, limit=10)
            nodes2 = self.kg.query(metric=m2, limit=10)
            sources1 = {n.source for n in nodes1}
            sources2 = {n.source for n in nodes2}
            return len(sources1 & sources2) > 0
        except Exception:
            return False

    def _are_opposing(self, m1: str, m2: str) -> bool:
        try:
            patterns1 = self._pattern_cache.get(m1, [])
            patterns2 = self._pattern_cache.get(m2, [])
            if not patterns1 or not patterns2:
                return False
            return patterns1[0].trend != patterns2[0].trend
        except Exception:
            return False

    def _find_metric_pairs(self, metrics: list[str]) -> list[tuple[str, str]]:
        try:
            pairs: list[tuple[str, str]] = []
            for i in range(len(metrics)):
                for j in range(i + 1, len(metrics)):
                    if self._are_related(metrics[i], metrics[j]):
                        pairs.append((metrics[i], metrics[j]))
            return pairs
        except Exception:
            return []

    async def get_insights(self, metrics: list[str]) -> dict[str, Any]:
        try:
            trends = await self.analyze_trends(metrics)
            contradictions = await self.detect_contradictions(metrics)
            hypotheses = await self.generate_hypotheses(metrics)
            return {'trends': trends, 'contradictions': contradictions, 'hypotheses': hypotheses, 'metric_count': len(metrics)}
        except Exception:
            return {'trends': {}, 'contradictions': {}, 'hypotheses': [], 'metric_count': 0}

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


@dataclass
class InteractionEdge:
    source_module: str
    target_module: str
    edge_type: str
    call_count: int = 0
    established_at: float = field(default_factory=time.time)


@dataclass
class ComplexityBudgetConfig:
    max_interaction_edges_per_module: int = 6
    max_total_edges: int = 200
    max_module_count: int = 50
    edge_growth_rate_threshold: float = 2.0
    warn_at_percent: float = 0.75
    block_at_percent: float = 0.95


@dataclass
class ComplexityAssessment:
    module_name: str
    current_edge_count: int
    max_allowed: int
    usage_percent: float
    status: str
    recommendations: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class GlobalComplexityReport:
    total_modules: int
    total_interaction_edges: int
    total_unused_edges: int
    max_module_edge_count: int
    avg_edges_per_module: float
    modules_near_limit: list[str] = field(default_factory=list)
    modules_at_limit: list[str] = field(default_factory=list)
    global_status: str = "healthy"
    timestamp: float = field(default_factory=time.time)


class ArchitectureComplexityBudget:
    def __init__(
        self,
        config: ComplexityBudgetConfig | None = None,
        audit_store: UnifiedAuditStore | None = None,
    ) -> None:
        self._config = config or ComplexityBudgetConfig()
        self._edges: dict[str, InteractionEdge] = {}
        self._module_edges: dict[str, list[str]] = defaultdict(list)
        self._edge_history: list[tuple[str, int]] = []
        self._audit_store = audit_store or UnifiedAuditStore()
        self._blocked_modules: set[str] = set()
        self._alerts: list[dict[str, Any]] = []

    @property
    def config(self) -> ComplexityBudgetConfig:
        return self._config

    def register_edge(self, source_module: str, target_module: str,
                       edge_type: str = "import") -> ComplexityAssessment | None:
        edge_key = f"{source_module}->{target_module}:{edge_type}"
        if edge_key in self._edges:
            self._edges[edge_key].call_count += 1
            return None

        edge = InteractionEdge(
            source_module=source_module,
            target_module=target_module,
            edge_type=edge_type,
            call_count=1,
        )
        self._edges[edge_key] = edge
        self._module_edges[source_module].append(edge_key)
        self._edge_history.append((edge_key, 1))

        return self._assess_module(source_module)

    def check_complexity_budget(self, module_name: str) -> ComplexityAssessment:
        return self.get_module_assessment(module_name)

    def get_module_assessment(self, module_name: str) -> ComplexityAssessment:
        edges = self._module_edges.get(module_name, [])
        edge_count = len(edges)
        max_allowed = self._config.max_interaction_edges_per_module
        usage = edge_count / max_allowed if max_allowed > 0 else 1.0

        if usage >= self._config.block_at_percent:
            status = "BLOCKED"
            self._blocked_modules.add(module_name)
        elif usage >= self._config.warn_at_percent:
            status = "WARNING"
        else:
            status = "OK"

        recommendations: list[str] = []
        if status == "WARNING":
            recommendations.append(
                f"[{module_name}] Complexity at {usage:.0%} - consider merging or splitting"
            )
        elif status == "BLOCKED":
            recommendations.append(
                f"[{module_name}] BLOCKED at {usage:.0%} - must reduce edges before adding"
            )
            targeted = [e for e in self._edges.values()
                         if e.source_module == module_name]
            sorted_by_count = sorted(targeted, key=lambda e: -e.call_count)
            for e in sorted_by_count[:3]:
                recommendations.append(
                    f"  → {e.source_module}->{e.target_module} ({e.call_count} calls)"
                )

        return ComplexityAssessment(
            module_name=module_name,
            current_edge_count=edge_count,
            max_allowed=max_allowed,
            usage_percent=round(usage * 100, 1),
            status=status,
            recommendations=recommendations,
        )

    def get_global_report(self) -> GlobalComplexityReport:
        modules = list(self._module_edges.keys())
        total_modules = len(modules)
        total_edges = len(self._edges)

        if not modules:
            return GlobalComplexityReport(
                total_modules=0,
                total_interaction_edges=0,
                total_unused_edges=0,
                max_module_edge_count=0,
                avg_edges_per_module=0.0,
                global_status="empty",
            )

        edge_counts = [len(edges) for edges in self._module_edges.values()]
        avg_edges = sum(edge_counts) / len(edge_counts)
        max_edges = max(edge_counts)

        near_limit: list[str] = []
        at_limit: list[str] = []
        warn_threshold = int(self._config.max_interaction_edges_per_module *
                              self._config.warn_at_percent)
        int(self._config.max_interaction_edges_per_module *
                               self._config.block_at_percent)

        for mod, edges in self._module_edges.items():
            count = len(edges)
            if count >= self._config.max_interaction_edges_per_module:
                at_limit.append(mod)
            elif count >= warn_threshold:
                near_limit.append(mod)

        unused = sum(1 for e in self._edges.values() if e.call_count <= 1)

        if at_limit:
            global_status = "BLOCKED"
        elif near_limit:
            global_status = "WARNING"
        else:
            global_status = "HEALTHY"

        if avg_edges > self._config.edge_growth_rate_threshold:
            if global_status == "HEALTHY":
                global_status = "WARNING"

        return GlobalComplexityReport(
            total_modules=total_modules,
            total_interaction_edges=total_edges,
            total_unused_edges=unused,
            max_module_edge_count=max_edges,
            avg_edges_per_module=round(avg_edges, 2),
            modules_near_limit=near_limit,
            modules_at_limit=at_limit,
            global_status=global_status,
        )

    def is_module_blocked(self, module_name: str) -> bool:
        if module_name in self._blocked_modules:
            return True
        assessment = self.get_module_assessment(module_name)
        return assessment.status == "BLOCKED"

    def suggest_edge_reduction(self, module_name: str,
                                 target_edge_count: int | None = None) -> list[str]:
        edges = self._module_edges.get(module_name, [])
        if not edges:
            return []

        target = target_edge_count or (
            self._config.max_interaction_edges_per_module - 2
        )
        current = len(edges)
        reduction_needed = max(current - target, 0)
        if reduction_needed == 0:
            return [f"[{module_name}] Already within budget ({current}/{target})"]

        sorted_by_usage = sorted(
            [self._edges[e] for e in edges],
            key=lambda e: e.call_count,
        )

        suggestions: list[str] = [
            f"[{module_name}] Need to reduce {current}->{target} ({reduction_needed} edges)"
        ]
        for edge in sorted_by_usage[:reduction_needed]:
            suggestions.append(
                f"  candidate: {edge.source_module}→{edge.target_module} "
                f"({edge.call_count} calls, type={edge.edge_type})"
            )

        return suggestions

    def remove_edge(self, source_module: str, target_module: str,
                     edge_type: str = "import") -> None:
        edge_key = f"{source_module}->{target_module}:{edge_type}"
        if edge_key in self._edges:
            del self._edges[edge_key]
            self._module_edges[source_module] = [
                e for e in self._module_edges.get(source_module, []) if e != edge_key
            ]
            remaining = len(self._module_edges.get(source_module, []))
            self._audit_store.append(UnifiedAuditRecord(
                record_id=make_record_id("cb", hash(edge_key) % 100000),
                timestamp=time.time(),
                layer="evolution",
                round=33,
                event_type="complexity_edge_removed",
                source_module="ComplexityBudget",
                target_module=source_module,
                decision=f"remove_edge({source_module}->{target_module})",
                justification=f"Edge removed, {remaining} remaining",
                outcome="success",
            ))

    def _assess_module(self, module_name: str) -> ComplexityAssessment | None:
        assessment = self.get_module_assessment(module_name)
        if assessment.status == "BLOCKED":
            self._alerts.append({
                "timestamp": time.time(),
                "module": module_name,
                "event": "BLOCKED",
                "edge_count": assessment.current_edge_count,
                "limit": assessment.max_allowed,
            })
        elif assessment.status == "WARNING":
            self._alerts.append({
                "timestamp": time.time(),
                "module": module_name,
                "event": "WARNING",
                "edge_count": assessment.current_edge_count,
                "limit": assessment.max_allowed,
            })
        return assessment

    @property
    def alerts(self) -> list[dict[str, Any]]:
        return list(self._alerts)

    @property
    def blocked_modules(self) -> list[str]:
        return sorted(self._blocked_modules)

    def clear(self) -> None:
        self._edges.clear()
        self._module_edges.clear()
        self._edge_history.clear()
        self._blocked_modules.clear()
        self._alerts.clear()

"""Tests for C3: SensitiveDataLineage (v0.51 W3-S3).

Tracks sensitive-data flow across domain boundaries and raises circuit-breaker
alerts when a flow crosses a domain not authorized for its classification.
"""

from __future__ import annotations

from maref.compliance.data_sovereignty import DataCategory
from maref.data.sensitive_lineage import SensitiveDataLineage, SensitiveFlowNode


def _flow(
    asset: str,
    from_domain: str,
    to_domain: str,
    category: DataCategory = DataCategory.HEALTH,
) -> SensitiveFlowNode:
    return SensitiveFlowNode(asset=asset, from_domain=from_domain, to_domain=to_domain, category=category)


def test_record_flow_and_list() -> None:
    lineage = SensitiveDataLineage()
    lineage.record_flow(_flow("patient_records", "health", "analytics"))
    flows = lineage.flows()
    assert len(flows) == 1
    assert flows[0].asset == "patient_records"
    assert flows[0].category == DataCategory.HEALTH


def test_allowed_cross_domain_no_alert() -> None:
    lineage = SensitiveDataLineage()
    lineage.record_flow(_flow("patient_records", "health", "analytics"))
    alerts = lineage.audit_alerts()
    assert alerts == []


def test_unauthorized_cross_domain_triggers_circuit_breaker() -> None:
    lineage = SensitiveDataLineage()
    lineage.record_flow(
        _flow("patient_records", "health", "marketing", category=DataCategory.HEALTH)
    )
    alerts = lineage.audit_alerts()
    assert len(alerts) == 1
    assert alerts[0]["asset"] == "patient_records"
    assert alerts[0]["event_type"] == "sensitive_flow_violation"
    assert "marketing" in alerts[0]["message"]


def test_spread_analysis_downstream() -> None:
    lineage = SensitiveDataLineage()
    # raw 经 etl 清洗进入 analytics，最后产出 report —— asset 链式扩散
    lineage.record_flow(_flow("raw", "src", "etl"), next_asset="cleansed")
    lineage.record_flow(_flow("cleansed", "etl", "analytics"), next_asset="analytics_out")
    lineage.record_flow(_flow("analytics_out", "analytics", "report"))
    spread = lineage.trace_downstream("raw")
    assert spread == {"cleansed", "analytics_out"}


def test_violation_count_accumulates() -> None:
    lineage = SensitiveDataLineage(
        allowed_cross_domains={
            DataCategory.FINANCIAL: {"ok", "finance"},
        }
    )
    lineage.record_flow(_flow("a", "src", "bad-1", category=DataCategory.FINANCIAL))
    lineage.record_flow(_flow("b", "src", "bad-2", category=DataCategory.FINANCIAL))
    lineage.record_flow(_flow("c", "src", "ok", category=DataCategory.FINANCIAL))
    assert lineage.violation_count() == 2


def test_allowed_domains_configurable() -> None:
    lineage = SensitiveDataLineage(
        allowed_cross_domains={
            DataCategory.HEALTH: {"analytics", "clinical"},
        }
    )
    lineage.record_flow(_flow("p", "health", "analytics", category=DataCategory.HEALTH))
    lineage.record_flow(_flow("q", "health", "marketing", category=DataCategory.HEALTH))
    assert lineage.violation_count() == 1


def test_circuit_breaker_state_after_violation() -> None:
    lineage = SensitiveDataLineage()
    assert not lineage.circuit_breaker_open()
    lineage.record_flow(_flow("p", "health", "marketing", category=DataCategory.HEALTH))
    assert lineage.circuit_breaker_open()

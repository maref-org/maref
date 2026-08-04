"""Tests for LineageTracker (v0.51 W1-S2 / A2).

Covers data lineage graph construction, downstream spread analysis, and
upstream root-cause tracing for enterprise data assets.
"""

from __future__ import annotations

from maref.data.lineage import LineageTracker


def _build_graph() -> LineageTracker:
    """raw → cleansed → aggregated → report 四层数据流 + 一条并行支线."""
    lt = LineageTracker()
    lt.add_edge("raw_orders", "cleansed_orders", transform="normalize")
    lt.add_edge("raw_orders", "cleansed_customers", transform="join_customer")
    lt.add_edge("cleansed_orders", "agg_monthly", transform="groupby_month")
    lt.add_edge("cleansed_customers", "agg_monthly", transform="groupby_month")
    lt.add_edge("agg_monthly", "exec_report", transform="render")
    return lt


def test_add_edge_records_node_and_edge() -> None:
    lt = LineageTracker()
    lt.add_edge("a", "b", transform="copy")
    assert lt.nodes() == {"a", "b"}
    assert lt.upstream_of("b") == {"a"}
    assert lt.downstream_of("a") == {"b"}


def test_trace_downstream_spread() -> None:
    lt = _build_graph()
    spread = lt.trace_downstream("raw_orders")
    assert spread == {"cleansed_orders", "cleansed_customers", "agg_monthly", "exec_report"}
    # 扩散面应包含全部下游，无论深度


def test_trace_downstream_leaf() -> None:
    lt = _build_graph()
    assert lt.trace_downstream("exec_report") == set()


def test_trace_upstream_roots() -> None:
    lt = _build_graph()
    roots = lt.trace_upstream("exec_report")
    assert roots == {"raw_orders", "cleansed_orders", "cleansed_customers", "agg_monthly"}
    # 上游链含全部直接与间接来源


def test_trace_upstream_includes_immediate() -> None:
    lt = _build_graph()
    assert lt.trace_upstream("cleansed_orders") == {"raw_orders"}


def test_transform_lookup() -> None:
    lt = _build_graph()
    assert lt.transform("raw_orders", "cleansed_orders") == "normalize"
    assert lt.transform("cleansed_orders", "raw_orders") is None


def test_unconnected_asset_isolated() -> None:
    lt = _build_graph()
    lt.add_edge("standalone", "isolated_out", transform="copy")
    assert lt.trace_downstream("standalone") == {"isolated_out"}
    assert lt.trace_upstream("isolated_out") == {"standalone"}

from __future__ import annotations

from maref.recursive.runtime_kg import (
    RuntimeInstrumentor,
    RuntimeKGEnricher,
    SamplingStrategy,
)


class TestSamplingStrategy:
    def test_enum_values(self) -> None:
        assert SamplingStrategy.FULL.value == "full"
        assert SamplingStrategy.SAMPLING.value == "sampling"
        assert SamplingStrategy.LAZY.value == "lazy"

    def test_full_strategy_records_all(self) -> None:
        inst = RuntimeInstrumentor()
        inst.configure_sampling(SamplingStrategy.FULL)
        for _ in range(20):
            inst.record_call("module_a", "module_b", latency_ms=1.0)
        records = inst.all_records()
        assert len(records) == 20

    def test_sampling_strategy_reduces_records(self) -> None:
        inst = RuntimeInstrumentor()
        inst.configure_sampling(SamplingStrategy.SAMPLING)
        for _ in range(100):
            inst.record_call("module_a", "module_b", latency_ms=1.0)
        records = inst.all_records()
        assert 0 < len(records) < 100

    def test_lazy_strategy_records_periodic(self) -> None:
        inst = RuntimeInstrumentor()
        inst.configure_sampling(SamplingStrategy.LAZY, sampling_interval=5)
        for _ in range(20):
            inst.record_call("module_a", "module_b", latency_ms=1.0)
        records = inst.all_records()
        assert len(records) == 4

    def test_critical_caller_always_recorded(self) -> None:
        inst = RuntimeInstrumentor()
        inst.configure_sampling(
            SamplingStrategy.LAZY,
            critical_callers={"module_critical"},
            sampling_interval=100,
        )
        for _ in range(10):
            inst.record_call("module_critical", "module_b", latency_ms=1.0)
        records = inst.all_records()
        assert len(records) == 10

    def test_critical_caller_ignores_sampling(self) -> None:
        inst = RuntimeInstrumentor()
        inst.configure_sampling(
            SamplingStrategy.SAMPLING,
            critical_callers={"module_critical"},
        )
        for _ in range(50):
            inst.record_call("module_critical", "module_b", latency_ms=1.0)
        records = inst.all_records()
        assert len(records) == 50

    def test_default_strategy_is_full(self) -> None:
        inst = RuntimeInstrumentor()
        for _ in range(10):
            inst.record_call("a", "b")
        assert len(inst.all_records()) == 10

    def test_record_call_with_error(self) -> None:
        inst = RuntimeInstrumentor()
        inst.record_call("a", "b", error="timeout")
        records = inst.all_records()
        assert len(records) == 1
        assert records[0].error_count == 1
        assert records[0].last_error == "timeout"

    def test_configure_sampling_min_interval(self) -> None:
        inst = RuntimeInstrumentor()
        inst.configure_sampling(SamplingStrategy.LAZY, sampling_interval=0)
        for _ in range(10):
            inst.record_call("a", "b")
        assert len(inst.all_records()) == 10

    def test_get_calls_from(self) -> None:
        inst = RuntimeInstrumentor()
        inst.record_call("caller_a", "callee_1")
        inst.record_call("caller_a", "callee_2")
        inst.record_call("caller_b", "callee_3")
        a_calls = inst.get_calls_from("caller_a")
        assert len(a_calls) == 2
        assert a_calls[0].callee == "callee_1"

    def test_get_calls_from_unknown(self) -> None:
        inst = RuntimeInstrumentor()
        assert inst.get_calls_from("nonexistent") == []

    def test_clear_resets_state(self) -> None:
        inst = RuntimeInstrumentor()
        inst.record_call("a", "b")
        inst.clear()
        assert len(inst.all_records()) == 0
        assert inst.get_calls_from("a") == []


class TestRuntimeKGEnricherIntegration:
    def test_inject_from_instrumentor_with_sampled_data(self) -> None:
        inst = RuntimeInstrumentor()
        inst.configure_sampling(SamplingStrategy.LAZY, sampling_interval=3)
        for _ in range(9):
            inst.record_call("caller_a", "callee_b", latency_ms=5.0)
        inst.record_call("caller_a", "callee_b", error="fail")

        enricher = RuntimeKGEnricher()
        enricher.inject_from_instrumentor(inst)
        assert enricher.node_count() >= 2
        assert enricher.relation_count() >= 1

    def test_inject_frequent_calls(self) -> None:
        inst = RuntimeInstrumentor()
        for _ in range(15):
            inst.record_call("hot_caller", "hot_callee")
        enricher = RuntimeKGEnricher()
        enricher.inject_from_instrumentor(inst)
        relations = [r for r in enricher._relations if r.from_node == "hot_caller"]
        assert len(relations) == 15

    def test_query_error_propagation(self) -> None:
        inst = RuntimeInstrumentor()
        inst.record_call("a", "b", error="boom")
        enricher = RuntimeKGEnricher()
        enricher.inject_from_instrumentor(inst)
        errors = enricher.query_error_propagation()
        assert len(errors) == 1

    def test_query_bottlenecks(self) -> None:
        inst = RuntimeInstrumentor()
        inst.record_call("a", "b", latency_ms=200.0)
        inst.record_call("c", "d", latency_ms=50.0)
        enricher = RuntimeKGEnricher()
        enricher.inject_from_instrumentor(inst)
        bottlenecks = enricher.query_bottlenecks(latency_threshold_ms=100.0)
        assert len(bottlenecks) == 1

    def test_get_node(self) -> None:
        enricher = RuntimeKGEnricher()
        enricher.add_node("n1", "module")
        node = enricher.get_node("n1")
        assert node is not None
        assert node.node_type == "module"
        assert enricher.get_node("n2") is None

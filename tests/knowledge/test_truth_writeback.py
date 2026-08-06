"""Tests for the recursive truth writeback loop (HypothesisCycle → TruthStore).

对齐桥水"组织学习复利"：分析结论写回存储，并作为后续推理输入。
"""

from __future__ import annotations

from maref.knowledge.graph import KnowledgeGraph
from maref.knowledge.hypothesis_cycle import HypothesisCycle
from maref.knowledge.truth_store import TruthStore
from maref.knowledge.writeback import TruthWriteback


class TestHypothesisCycleWriteback:
    def test_conclude_confirmed_upgrades_current_best(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        hc = HypothesisCycle(KnowledgeGraph(), truth_store=store)

        hyp = hc.propose("Is X true?", "X is true", entity_id="topic:x")
        hc.record_finding(hyp.node_id, "Experiment confirms X", supports=True, confidence=0.9)
        hyp.confidence = 0.9
        hc.conclude(hyp.node_id, "X is confirmed", confirmed=True)

        page = store.load("topic:x")
        assert page is not None
        assert page.compiled_truth.current_best == "X is confirmed"
        assert page.compiled_truth.confidence == 0.9
        assert len(page.evidence_trail) >= 1

    def test_conclude_refuted_only_appends_evidence(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        hc = HypothesisCycle(KnowledgeGraph(), truth_store=store)

        hyp = hc.propose("Is Y true?", "Y is true", entity_id="topic:y")
        hc.conclude(hyp.node_id, "Y is false", confirmed=False)

        page = store.load("topic:y")
        assert page is not None
        # 失败不升级 current_best（保持空），只追加否定证据
        assert page.compiled_truth.current_best == ""
        assert len(page.evidence_trail) >= 1

    def test_low_confidence_confirmed_does_not_upgrade(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        hc = HypothesisCycle(KnowledgeGraph(), truth_store=store)

        hyp = hc.propose("Is Z true?", "Z is true", entity_id="topic:z")
        hyp.confidence = 0.4  # 低于确认阈值 0.7
        hc.conclude(hyp.node_id, "Z weakly confirmed", confirmed=True)

        page = store.load("topic:z")
        assert page is not None
        assert page.compiled_truth.current_best == ""
        assert len(page.evidence_trail) >= 1

    def test_recompile_preserves_prior_as_evidence(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        hc = HypothesisCycle(KnowledgeGraph(), truth_store=store)

        h1 = hc.propose("Q", "first", entity_id="topic:evo")
        h1.confidence = 0.9
        hc.conclude(h1.node_id, "v1", confirmed=True)

        h2 = hc.propose("Q", "second", entity_id="topic:evo")
        h2.confidence = 0.9
        hc.conclude(h2.node_id, "v2", confirmed=True)

        page = store.load("topic:evo")
        assert page is not None
        assert page.compiled_truth.current_best == "v2"
        # 旧版本 v1 进入证据链
        assert any("v1" in e.text for e in page.evidence_trail)

    def test_get_truth_context_after_writeback(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        hc = HypothesisCycle(KnowledgeGraph(), truth_store=store)

        hyp = hc.propose("Q", "hyp", entity_id="topic:ctx")
        hc.record_finding(hyp.node_id, "evidence A", supports=True, confidence=0.8)
        hyp.confidence = 0.9
        hc.conclude(hyp.node_id, "resolved", confirmed=True)

        ctx = store.get_truth_context("topic:ctx")
        assert ctx is not None
        assert ctx["current_best"] == "resolved"
        assert len(ctx["active_evidence"]) >= 1

    def test_prior_truth_injected_on_second_propose(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        hc = HypothesisCycle(KnowledgeGraph(), truth_store=store)

        h1 = hc.propose("Q", "first", entity_id="topic:prior")
        h1.confidence = 0.9
        hc.conclude(h1.node_id, "prior conclusion", confirmed=True)

        # 第二次提出假设时注入 prior_truth 作为推理上下文
        h2 = hc.propose(
            "Q", "second", entity_id="topic:prior",
            prior_truth=store.get_truth_context("topic:prior"),
        )
        node = hc._kg.get_node(h2.node_id)
        assert node is not None
        assert node.metadata.get("prior_truth") == "prior conclusion"
        assert "[prior_truth]" in node.content


class TestTruthWriteback:
    def test_register_and_resolve_all_passed(self, tmp_path) -> None:
        wb = TruthWriteback(store=TruthStore(storage_dir=tmp_path))

        wb.register_hypothesis("h_1", "tests 可靠性假设", "tests")
        page = wb.resolve_outcome("h_1", all_passed=True, summary="all green")

        assert page is not None
        assert page.entity_id == "arch:tests"
        assert page.compiled_truth.current_best == "all green"
        assert page.compiled_truth.confidence >= 0.7

    def test_register_and_resolve_failed_only_evidence(self, tmp_path) -> None:
        wb = TruthWriteback(store=TruthStore(storage_dir=tmp_path))

        wb.register_hypothesis("h_2", "latency 优化假设", "execution")
        page = wb.resolve_outcome("h_2", all_passed=False, summary="flaky")

        assert page is not None
        assert page.compiled_truth.current_best == ""
        assert len(page.evidence_trail) >= 1

    def test_prior_truth_injected_on_second_register(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        wb = TruthWriteback(store=store)

        wb.register_hypothesis("h_a", "first hypothesis", "tests")
        wb.resolve_outcome("h_a", all_passed=True, summary="v1 confirmed")

        # 第二次注册同一实体 → register 自动注入 prior_truth
        record_b = wb.register_hypothesis("h_b", "second hypothesis", "tests")
        node = wb.cycle._kg.get_node(record_b.node_id)
        assert node is not None
        assert node.metadata.get("prior_truth") == "v1 confirmed"

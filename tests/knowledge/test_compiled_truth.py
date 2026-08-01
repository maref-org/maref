"""Tests for Compiled Truth + Timeline data model and TruthStore."""

from __future__ import annotations

import time

from maref.knowledge.compiled_truth import CompiledTruth, TruthPage
from maref.knowledge.truth_store import TruthStore


def _page(entity_id: str, best: str = "truth", confidence: float = 0.7) -> TruthPage:
    return TruthPage(
        entity_id=entity_id,
        compiled_truth=CompiledTruth(
            entity_id=entity_id,
            current_best=best,
            confidence=confidence,
            last_updated=time.time(),
            updated_by="tester",
        ),
    )


class TestCompiledTruth:
    def test_compile_updates_truth(self) -> None:
        page = _page("test_1", best="old version", confidence=0.5)
        page.compile("new version", "agent_b", confidence=0.8)
        assert page.compiled_truth.current_best == "new version"
        assert page.compiled_truth.confidence == 0.8
        assert page.compiled_truth.updated_by == "agent_b"

    def test_compile_preserves_old_as_evidence(self) -> None:
        page = _page("test_2", best="original", confidence=0.5)
        page.compile("updated", "agent_b")
        assert len(page.evidence_trail) >= 1
        assert page.evidence_trail[0].text == "original"

    def test_add_evidence(self) -> None:
        page = _page("test_3")
        entry = page.add_evidence("new finding", "experiment", confidence=0.8)
        assert entry.text == "new finding"
        assert entry.source == "experiment"
        assert entry.confidence == 0.8
        assert len(page.evidence_trail) == 1

    def test_get_timeline(self) -> None:
        page = _page("test_4")
        page.add_evidence("finding A", "src_a")
        page.add_evidence("finding B", "src_b")
        timeline = page.get_timeline()
        assert len(timeline) == 2

    def test_get_active_evidence(self) -> None:
        page = _page("test_5")
        e1 = page.add_evidence("old finding", "src")
        e2 = page.add_evidence("newer finding", "src")
        e1.superseded_by = e2.citation_id
        active = page.get_active_evidence()
        assert len(active) == 1
        assert active[0].citation_id == e2.citation_id

    def test_to_dict_roundtrip(self) -> None:
        page = _page("test_6")
        page.add_evidence("evidence text", "test")
        data = page.to_dict()
        restored = TruthPage.from_dict(data)
        assert restored.entity_id == page.entity_id
        assert restored.compiled_truth.current_best == page.compiled_truth.current_best
        assert len(restored.evidence_trail) == 1


class TestTruthStore:
    def test_save_and_load(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        page = _page("test_save", best="stored truth", confidence=0.9)
        page.add_evidence("stored evidence", "test")
        store.save(page)
        loaded = store.load("test_save")
        assert loaded is not None
        assert loaded.compiled_truth.current_best == "stored truth"
        assert len(loaded.evidence_trail) == 1

    def test_load_nonexistent(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        assert store.load("nonexistent") is None

    def test_list_all(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        for i in range(3):
            store.save(_page(f"entity_{i}", best=f"truth_{i}"))
        assert len(store.list_all()) == 3

    def test_find_by_entity(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        store.save(_page("entity_SpaceX_123", best="SpaceX is a space company", confidence=0.9))
        assert len(store.find_by_entity("SpaceX")) >= 1

    def test_delete(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        store.save(_page("to_delete", best="temp"))
        assert store.count >= 1
        assert store.delete("to_delete")
        assert store.load("to_delete") is None

    def test_get_truth_context(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        page = _page("entity_ctx", best="current best", confidence=0.9)
        e1 = page.add_evidence("old", "src")
        e2 = page.add_evidence("new", "src")
        e1.superseded_by = e2.citation_id
        store.save(page)

        ctx = store.get_truth_context("entity_ctx")
        assert ctx is not None
        assert ctx["current_best"] == "current best"
        assert ctx["confidence"] == 0.9
        # 只含未被替代的证据
        assert len(ctx["active_evidence"]) == 1

    def test_get_truth_context_missing(self, tmp_path) -> None:
        store = TruthStore(storage_dir=tmp_path)
        assert store.get_truth_context("nope") is None

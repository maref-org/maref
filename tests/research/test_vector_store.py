"""
Tests for VectorKnowledgeStore (P1.1)

Verifies semantic search, batch operations, and edge cases
using ChromaDB's ONNX-based embedding (no external API calls).
"""

from __future__ import annotations

import pytest

from research.vector_store import SearchResult, VectorKnowledgeStore


class TestVectorKnowledgeStore:
    """Test suite for vector store."""

    @pytest.fixture
    def store(self) -> VectorKnowledgeStore:
        """Ephemeral in-memory store for testing (isolated per test)."""
        import uuid
        s = VectorKnowledgeStore(collection_name=f"test_{uuid.uuid4().hex[:8]}")
        return s

    # --- add_finding ---

    async def test_add_and_search(self, store: VectorKnowledgeStore) -> None:
        """Basic add + search round-trip."""
        store.add_finding("KL divergence threshold 0.15 gives best F1 score", {"metric": "f1"})
        results = store.search("best KL threshold")
        assert len(results) >= 1
        assert results[0].score < 1.0  # semantically similar

    async def test_add_returns_id(self, store: VectorKnowledgeStore) -> None:
        doc_id = store.add_finding("test finding", {"experiment": "test"})
        assert doc_id.startswith("finding_")
        assert len(doc_id) > 10

    async def test_add_empty_content(self, store: VectorKnowledgeStore) -> None:
        doc_id = store.add_finding("", {"experiment": "test"})
        assert doc_id is not None

    # --- search ---

    async def test_search_empty_store(self, store: VectorKnowledgeStore) -> None:
        results = store.search("anything")
        assert results == []

    async def test_search_relevance_ordering(
        self, store: VectorKnowledgeStore
    ) -> None:
        """More semantically relevant results should have lower scores (closer = 0)."""
        store.add_finding("The cat sat on the mat", {"topic": "cats"})
        store.add_finding("Policy gradient methods optimize reward", {"topic": "rl"})
        store.add_finding("KL divergence measures distribution distance", {"topic": "math"})

        results = store.search("machine learning policy optimization")
        assert len(results) > 0
        # At least one RL-related result should be returned
        rl_results = [r for r in results if "policy" in r.content.lower()]
        assert len(rl_results) >= 1, "Expected at least one RL-related result"

    async def test_search_semantic_match_vs_keyword(
        self, store: VectorKnowledgeStore
    ) -> None:
        """Semantic search should find related concepts, not just keywords."""
        store.add_finding("Oscillation in governance states detected", {"type": "finding"})
        store.add_finding("The weather is sunny today", {"type": "irrelevant"})

        results = store.search("unstable state transitions in agents")
        assert len(results) > 0
        # The oscillation finding should be most relevant
        assert "oscillation" in results[0].content.lower()

    async def test_search_returns_correct_structure(
        self, store: VectorKnowledgeStore
    ) -> None:
        store.add_finding("test finding", {"experiment": "test_exp"})
        results = store.search("test")
        r = results[0]
        assert isinstance(r, SearchResult)
        assert isinstance(r.content, str)
        assert isinstance(r.score, float)
        assert isinstance(r.metadata, dict)
        assert isinstance(r.id, str)
        assert r.metadata.get("experiment") == "test_exp"

    # --- search_similar ---

    async def test_search_similar_finds_related(
        self, store: VectorKnowledgeStore
    ) -> None:
        store.add_finding("High entropy leads to unstable governance")
        store.add_finding("Entropy is a measure of disorder in systems")
        store.add_finding("The sky appears blue due to Rayleigh scattering")

        results = store.search_similar("entropy and stability in governance")
        assert len(results) >= 2
        assert all(r.score < 1.5 for r in results[:2])

    # --- add_findings (batch) ---

    async def test_add_findings_batch(self, store: VectorKnowledgeStore) -> None:
        ids = store.add_findings([
            ("Finding one", {"exp": "exp1"}),
            ("Finding two", {"exp": "exp2"}),
            ("Finding three", {"exp": "exp3"}),
        ])
        assert len(ids) == 3
        assert all(id.startswith("finding_") for id in ids)
        assert store.count() == 3

    async def test_add_findings_empty(self, store: VectorKnowledgeStore) -> None:
        ids = store.add_findings([])
        assert ids == []

    async def test_add_findings_without_metadata(
        self, store: VectorKnowledgeStore
    ) -> None:
        ids = store.add_findings([
            ("Finding one", None),
            ("Finding two", None),
        ])
        assert len(ids) == 2

    # --- count ---

    async def test_count_empty(self, store: VectorKnowledgeStore) -> None:
        assert store.count() == 0

    async def test_count_after_add(self, store: VectorKnowledgeStore) -> None:
        store.add_finding("finding 1")
        store.add_finding("finding 2")
        store.add_finding("finding 3")
        assert store.count() == 3

    # --- clear ---

    async def test_clear(self, store: VectorKnowledgeStore) -> None:
        store.add_finding("something")
        assert store.count() > 0
        store.clear()
        assert store.count() == 0

    async def test_clear_then_add(self, store: VectorKnowledgeStore) -> None:
        store.add_finding("first")
        store.clear()
        store.add_finding("second")
        assert store.count() == 1
        results = store.search("second")
        assert len(results) == 1

    # --- get_all ---

    async def test_get_all(self, store: VectorKnowledgeStore) -> None:
        store.add_finding("A", {"idx": "1"})
        store.add_finding("B", {"idx": "2"})
        store.add_finding("C", {"idx": "3"})
        all_items = store.get_all()
        assert len(all_items) == 3
        contents = {r.content for r in all_items}
        assert contents == {"A", "B", "C"}

    async def test_get_all_empty(self, store: VectorKnowledgeStore) -> None:
        assert store.get_all() == []

    # --- reconstruction and semantic consistency ---

    async def test_semantic_search_across_domains(
        self, store: VectorKnowledgeStore
    ) -> None:
        """Very strict test: semantically different topics should rank correctly."""
        store.add_finding("Recursive governance oscillation detection", {"area": "governance"})
        store.add_finding("F1 score for anomaly detection models", {"area": "metrics"})
        store.add_finding("KL divergence threshold optimization", {"area": "drift"})

        results = store.search("detecting oscillation in multi-agent systems")
        assert len(results) >= 1
        # The finding mentioning "oscillation" should be most relevant to this query
        top = results[0].content.lower()
        assert "oscillation" in top, (
            f"Expected oscillation finding first, got: {results[0].content}"
        )

    # --- metadata handling ---

    async def test_metadata_preserved(self, store: VectorKnowledgeStore) -> None:
        store.add_finding("finding with meta", {
            "experiment": "test_exp",
            "phase": "8",
            "confidence": "0.95",
        })
        results = store.search("finding with meta")
        assert len(results) >= 1
        meta = results[0].metadata
        assert meta.get("experiment") == "test_exp"
        assert meta.get("phase") == "8"
        assert meta.get("confidence") == "0.95"

"""Tests for VectorStore with n-gram embeddings."""

import pytest

from maref.memory.vector_store import VectorRecord, VectorStore


class TestVectorStore:
    def test_insert_and_get(self):
        vs = VectorStore()
        rec = VectorRecord(id="r1", text="machine learning is powerful")
        vs.insert(rec)
        got = vs.get("r1")
        assert got is not None
        assert got.text == "machine learning is powerful"

    def test_similarity_search_returns_similar(self):
        vs = VectorStore(min_score=0.1)
        vs.insert(VectorRecord(id="r1", text="deep learning neural networks"))
        vs.insert(VectorRecord(id="r2", text="machine learning algorithms"))
        vs.insert(VectorRecord(id="r3", text="cooking pasta recipes"))
        results = vs.similarity_search("neural network training", k=5)
        ids = [r[0].id for r in results]
        assert "r1" in ids
        assert "r2" in ids
        assert "r3" not in ids, "unrelated text should not match"

    def test_empty_store_returns_empty(self):
        vs = VectorStore()
        results = vs.similarity_search("anything", k=5)
        assert len(results) == 0

    def test_delete_removes_record(self):
        vs = VectorStore()
        vs.insert(VectorRecord(id="r1", text="hello"))
        assert vs.delete("r1") is True
        assert vs.get("r1") is None
        assert vs.delete("nonexistent") is False

    def test_similarity_scores_are_between_0_and_1(self):
        vs = VectorStore(min_score=0.0)
        vs.insert(VectorRecord(id="r1", text="exact same text content here"))
        results = vs.similarity_search("exact same text content here", k=5)
        assert len(results) == 1
        score = results[0][1]
        assert 0.0 <= score <= 1.0

    def test_clear(self):
        vs = VectorStore()
        vs.insert(VectorRecord(id="r1", text="hello"))
        vs.clear()
        assert len(vs) == 0

    def test_threshold_filters_low_scores(self):
        vs = VectorStore(min_score=0.5)
        vs.insert(VectorRecord(id="r1", text="abcdefghijklmnopqrstuvwxyz"))
        vs.insert(VectorRecord(id="r2", text="zyxwvutsrqponmlkjihgfedcba"))
        results = vs.similarity_search("abcdefghijklmnop", k=5)
        assert len(results) <= 2

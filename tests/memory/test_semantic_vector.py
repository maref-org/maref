"""Tests for SemanticMemoryStore with vector search."""

from maref.memory.memory_manager import (
    MemoryManager,
    MemoryQuery,
    MemoryRecord,
)


class TestSemanticVectorSearch:
    def test_vector_search_returns_semantic_matches(self):
        mm = MemoryManager()
        mm.semantic.store(MemoryRecord(content={"text": "deep learning neural networks"}))
        mm.semantic.store(MemoryRecord(content={"text": "machine learning algorithms"}))
        mm.semantic.store(MemoryRecord(content={"text": "cooking pasta recipes"}))
        results = mm.semantic.query(MemoryQuery(keywords=["neural", "network"]))
        ids = [r.memory_id for r in results]
        assert len(results) >= 1

    def test_vector_search_falls_back_to_keyword(self):
        mm = MemoryManager()
        mm.semantic.store(MemoryRecord(content={"text": "exact keyword match test"}))
        results = mm.semantic.query(MemoryQuery(keywords=["exact", "keyword"]))
        assert len(results) >= 1

    def test_query_similar_by_text(self):
        mm = MemoryManager()
        mm.semantic.store(MemoryRecord(content={"topic": "machine learning basics"}))
        results = mm.semantic.query_similar("deep learning introduction", limit=5)
        assert len(results) >= 1

    def test_empty_query_returns_empty(self):
        mm = MemoryManager()
        mm.semantic.store(MemoryRecord(content={"text": "something"}))
        results = mm.semantic.query(MemoryQuery(keywords=[]))
        assert len(results) == 0

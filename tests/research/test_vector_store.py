"""
Comprehensive tests for vector_store.py.
All external dependencies (chromadb, uuid, time, pathlib) are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from chromadb.errors import NotFoundError
from research.vector_store import SearchResult, VectorKnowledgeStore


class TestSearchResult:
    """Tests for SearchResult dataclass construction and defaults."""

    def test_construction_all_fields(self) -> None:
        sr = SearchResult(content="hello", score=0.5, metadata={"k": "v"}, id="id1")
        assert sr.content == "hello"
        assert sr.score == 0.5
        assert sr.metadata == {"k": "v"}
        assert sr.id == "id1"

    def test_defaults(self) -> None:
        sr = SearchResult(content="hello", score=0.5)
        assert sr.metadata == {}
        assert sr.id == ""

    def test_default_factory_isolation(self) -> None:
        sr1 = SearchResult(content="a", score=0.1)
        sr2 = SearchResult(content="b", score=0.2)
        sr1.metadata["x"] = 1
        assert "x" not in sr2.metadata

    def test_empty_content(self) -> None:
        sr = SearchResult(content="", score=0.0)
        assert sr.content == ""
        assert sr.score == 0.0

    def test_negative_score(self) -> None:
        sr = SearchResult(content="x", score=-1.5)
        assert sr.score == -1.5


@pytest.fixture
def mock_uuid() -> MagicMock:
    counter = 0
    def _fake() -> object:
        nonlocal counter
        counter += 1
        return type("FakeUUID", (), {"hex": f"{counter:08x}"})()
    return MagicMock(side_effect=_fake)


@pytest.fixture
def mock_chromadb_client() -> tuple[MagicMock, MagicMock]:
    client = MagicMock()
    collection = MagicMock()
    client.get_collection.return_value = collection
    client.create_collection.return_value = collection
    client.delete_collection.return_value = None
    collection.count.return_value = 0
    collection.add.return_value = None
    collection.query.return_value = {
        "ids": [[]],
        "distances": [[]],
        "documents": [[]],
        "metadatas": [[]],
    }
    collection.get.return_value = {
        "ids": [],
        "documents": [],
        "metadatas": [],
    }
    return client, collection


@pytest.fixture
def patched_store(mock_chromadb_client: tuple[MagicMock, MagicMock], mock_uuid: MagicMock):
    client, collection = mock_chromadb_client
    with (
        patch("research.vector_store.chromadb.EphemeralClient", return_value=client),
        patch("research.vector_store.chromadb.PersistentClient", return_value=client),
        patch("research.vector_store.uuid.uuid4", mock_uuid),
        patch("research.vector_store.time.time", return_value=1234567890.0),
    ):
        yield client, collection


class TestInit:
    """Tests for VectorKnowledgeStore.__init__."""

    def test_ephemeral_no_path(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        assert store.collection_name == VectorKnowledgeStore.DEFAULT_COLLECTION
        assert store._client is client
        assert store._collection is collection

    def test_persistent_with_path(self, patched_store: tuple[MagicMock, MagicMock], tmp_path) -> None:
        client, collection = patched_store
        db_path = tmp_path / "db"
        store = VectorKnowledgeStore(path=db_path)
        from research.vector_store import chromadb
        chromadb.PersistentClient.assert_called_once_with(str(db_path / "chroma_db"))
        assert store.collection_name == VectorKnowledgeStore.DEFAULT_COLLECTION

    def test_path_as_string(self, patched_store: tuple[MagicMock, MagicMock], tmp_path) -> None:
        client, collection = patched_store
        db_path = str(tmp_path / "db")
        store = VectorKnowledgeStore(path=db_path)
        assert store.collection_name == VectorKnowledgeStore.DEFAULT_COLLECTION

    def test_custom_collection_name(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore(collection_name="custom")
        client.get_collection.assert_called_once_with("custom")
        assert store.collection_name == "custom"

    def test_collection_exists(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        client.get_collection.assert_called_once()
        client.create_collection.assert_not_called()

    def test_collection_not_found_valueerror(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        client.get_collection.side_effect = ValueError("no such collection")
        store = VectorKnowledgeStore()
        client.create_collection.assert_called_once()

    def test_collection_not_found_notfounderror(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        client.get_collection.side_effect = NotFoundError("missing")
        store = VectorKnowledgeStore()
        client.create_collection.assert_called_once()


class TestAddFinding:
    """Tests for add_finding."""

    def test_basic(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        doc_id = store.add_finding("content", {"key": "value"})
        assert doc_id == "finding_00000001"
        collection.add.assert_called_once()
        kwargs = collection.add.call_args[1]
        assert kwargs["documents"] == ["content"]
        assert kwargs["ids"] == ["finding_00000001"]
        meta = kwargs["metadatas"][0]
        assert meta["key"] == "value"
        assert meta["stored_at"] == "1234567890.0"

    def test_no_metadata(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        doc_id = store.add_finding("content")
        assert doc_id == "finding_00000001"
        kwargs = collection.add.call_args[1]
        assert kwargs["metadatas"][0] == {"stored_at": "1234567890.0"}

    def test_empty_content(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        store.add_finding("")
        kwargs = collection.add.call_args[1]
        assert kwargs["documents"] == [""]

    def test_metadata_filters_invalid_types(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        store.add_finding(
            "x",
            {
                "good_str": "val",
                "bad_list": [1, 2],
                "bad_dict": {"a": 1},
                "bad_none": None,
                "bad_bytes": b"data",
            },
        )
        meta = collection.add.call_args[1]["metadatas"][0]
        assert "good_str" in meta
        assert "bad_list" not in meta
        assert "bad_dict" not in meta
        assert "bad_none" not in meta
        assert "bad_bytes" not in meta
        assert "stored_at" in meta

    def test_metadata_keeps_valid_types(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        store.add_finding(
            "x",
            {"s": "a", "i": 1, "f": 1.5, "b": True},
        )
        meta = collection.add.call_args[1]["metadatas"][0]
        assert meta["s"] == "a"
        assert meta["i"] == "1"
        assert meta["f"] == "1.5"
        assert meta["b"] == "True"
        assert meta["stored_at"] == "1234567890.0"


class TestAddFindings:
    """Tests for add_findings (batch)."""

    def test_empty_list(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        result = store.add_findings([])
        assert result == []
        collection.add.assert_not_called()

    def test_batch(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        ids = store.add_findings([
            ("one", {"a": "1"}),
            ("two", {"b": "2"}),
        ])
        assert ids == ["finding_00000001", "finding_00000002"]
        collection.add.assert_called_once()
        kwargs = collection.add.call_args[1]
        assert kwargs["documents"] == ["one", "two"]
        assert len(kwargs["metadatas"]) == 2

    def test_mixed_metadata(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        ids = store.add_findings([
            ("one", None),
            ("two", {"k": "v"}),
        ])
        assert len(ids) == 2
        kwargs = collection.add.call_args[1]
        assert kwargs["metadatas"][0] == {"stored_at": "1234567890.0"}
        assert kwargs["metadatas"][1]["k"] == "v"
        assert "stored_at" in kwargs["metadatas"][1]

    def test_invalid_metadata_filtered(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        store.add_findings([
            ("one", {"valid": "yes", "invalid": [1]}),
        ])
        meta = collection.add.call_args[1]["metadatas"][0]
        assert "valid" in meta
        assert "invalid" not in meta


class TestCount:
    """Tests for count."""

    def test_returns_collection_count(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 7
        assert store.count() == 7

    def test_zero(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 0
        assert store.count() == 0


class TestSearch:
    """Tests for search."""

    def test_empty_store(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 0
        results = store.search("query")
        assert results == []
        collection.query.assert_not_called()

    def test_non_empty(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 2
        collection.query.return_value = {
            "ids": [["id1", "id2"]],
            "distances": [[0.1, 0.5]],
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"k": "1"}, {"k": "2"}]],
        }
        results = store.search("query", n_results=5)
        assert len(results) == 2
        assert results[0].id == "id1"
        assert results[0].score == 0.1
        assert results[0].content == "doc1"
        assert results[0].metadata == {"k": "1"}
        collection.query.assert_called_once_with(query_texts=["query"], n_results=2)

    def test_n_results_capped(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 1
        collection.query.return_value = {
            "ids": [["id1"]],
            "distances": [[0.0]],
            "documents": [["d1"]],
            "metadatas": [[{}]],
        }
        store.search("q", n_results=10)
        collection.query.assert_called_once_with(query_texts=["q"], n_results=1)

    def test_n_results_zero(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 3
        collection.query.return_value = {
            "ids": [[]],
            "distances": [[]],
            "documents": [[]],
            "metadatas": [[]],
        }
        store.search("q", n_results=0)
        collection.query.assert_called_once_with(query_texts=["q"], n_results=0)

    def test_result_ordering(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 3
        collection.query.return_value = {
            "ids": [["a", "b", "c"]],
            "distances": [[0.01, 0.5, 0.9]],
            "documents": [["A", "B", "C"]],
            "metadatas": [[{}, {}, {}]],
        }
        results = store.search("q")
        assert [r.id for r in results] == ["a", "b", "c"]
        assert [r.score for r in results] == [0.01, 0.5, 0.9]


class TestSearchSimilar:
    """Tests for search_similar."""

    def test_delegates_to_search(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 1
        collection.query.return_value = {
            "ids": [["id1"]],
            "distances": [[0.2]],
            "documents": [["doc1"]],
            "metadatas": [[{"x": "y"}]],
        }
        results = store.search_similar("content", n_results=3)
        assert len(results) == 1
        assert results[0].id == "id1"
        collection.query.assert_called_once_with(query_texts=["content"], n_results=1)


class TestClear:
    """Tests for clear."""

    def test_deletes_and_recreates(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        store.clear()
        client.delete_collection.assert_called_once_with(VectorKnowledgeStore.DEFAULT_COLLECTION)
        client.create_collection.assert_called_once_with(VectorKnowledgeStore.DEFAULT_COLLECTION)
        assert store._collection is collection

    def test_suppresses_valueerror(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        client.delete_collection.side_effect = ValueError("no")
        store.clear()
        client.create_collection.assert_called_once()

    def test_suppresses_notfounderror(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        client.delete_collection.side_effect = NotFoundError("missing")
        store.clear()
        client.create_collection.assert_called_once()


class TestGetAll:
    """Tests for get_all."""

    def test_empty_store(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 0
        assert store.get_all() == []
        collection.get.assert_not_called()

    def test_non_empty(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 2
        collection.get.return_value = {
            "ids": ["i1", "i2"],
            "documents": ["d1", "d2"],
            "metadatas": [{"k": "1"}, {"k": "2"}],
        }
        results = store.get_all()
        assert len(results) == 2
        assert results[0].id == "i1"
        assert results[0].content == "d1"
        assert results[0].metadata == {"k": "1"}
        assert results[0].score == 0.0
        assert results[1].score == 0.0

    def test_no_ids_in_get(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        collection.count.return_value = 1
        collection.get.return_value = {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }
        assert store.get_all() == []


class TestBuildResults:
    """Tests for _build_results internal helper."""

    def test_empty_ids(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        assert store._build_results({"ids": [[]]}) == []

    def test_no_ids_key(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        assert store._build_results({}) == []

    def test_missing_distances(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        raw = {
            "ids": [["id1"]],
            "documents": [["doc1"]],
            "metadatas": [[{"k": "v"}]],
        }
        results = store._build_results(raw)
        assert len(results) == 1
        assert results[0].score == 1.0

    def test_none_values(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        raw = {
            "ids": [["id1"]],
            "distances": [[None]],
            "documents": [[None]],
            "metadatas": [[None]],
        }
        results = store._build_results(raw)
        assert results[0].score == 1.0
        assert results[0].content == ""
        assert results[0].metadata == {}

    def test_multiple_items(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        raw = {
            "ids": [["a", "b"]],
            "distances": [[0.1, 0.2]],
            "documents": [["A", "B"]],
            "metadatas": [[{"x": 1}, {"y": 2}]],
        }
        results = store._build_results(raw)
        assert len(results) == 2
        assert results[0].id == "a"
        assert results[1].id == "b"

    def test_empty_inner_documents_metadatas(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore()
        raw = {
            "ids": [["id1"]],
            "distances": [[0.5]],
            "documents": [[]],
            "metadatas": [[]],
        }
        # zip stops at shortest iterable, so no results
        assert store._build_results(raw) == []


class TestCollectionNameProperty:
    """Tests for collection_name property."""

    def test_returns_name(self, patched_store: tuple[MagicMock, MagicMock]) -> None:
        client, collection = patched_store
        store = VectorKnowledgeStore(collection_name="my_collection")
        assert store.collection_name == "my_collection"

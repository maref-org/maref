"""
MAREF Vector Knowledge Store

Semantic vector store for research findings, built on ChromaDB.
Layers on top of KnowledgeGraph without replacing it — enables
semantic search where keyword-based KG query falls short.

Usage:
    store = VectorKnowledgeStore()
    store.add_finding("KL threshold 0.15 gives best F1=0.903",
                      {"experiment": "policy_lifecycle"})
    results = store.search("best threshold for KL divergence")
"""

from __future__ import annotations

import contextlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api import ClientAPI
from chromadb.errors import NotFoundError


@dataclass
class SearchResult:
    """Result from a vector store semantic search."""

    content: str
    score: float  # cosine distance (0 = identical, 1 = orthogonal, 2 = opposite)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = ""


class VectorKnowledgeStore:
    """
    Semantic vector store for research findings.

    Uses ChromaDB's built-in embedding function (all-MiniLM-L6-v2 via ONNX)
    so no external model download is required at import time.

    Defaults to ephemeral storage (in-memory). Pass a `path` for persistent
    on-disk storage that survives restarts.
    """

    DEFAULT_COLLECTION = "maref_findings"

    def __init__(
        self,
        path: Path | None = None,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        """
        Initialize the vector store.

        Args:
            path: Directory for persistent storage. None = ephemeral.
            collection_name: Name of the ChromaDB collection.
        """
        if path is not None:
            path = Path(path)
            path.mkdir(parents=True, exist_ok=True)
            self._client: ClientAPI = chromadb.PersistentClient(
                str(path / "chroma_db")
            )
        else:
            self._client = chromadb.EphemeralClient()

        # Get or create collection
        try:
            self._collection = self._client.get_collection(collection_name)
        except (ValueError, NotFoundError):
            self._collection = self._client.create_collection(collection_name)

        self._collection_name = collection_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_finding(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Add a single finding to the vector store.

        Args:
            content: The finding text.
            metadata: Optional metadata dict (supports experiment name, etc.).

        Returns:
            The generated document ID.
        """
        doc_id = f"finding_{uuid.uuid4().hex[:8]}"
        clean_meta = {k: str(v) for k, v in (metadata or {}).items()
                      if isinstance(v, (str, int, float, bool))}
        clean_meta["stored_at"] = str(time.time())

        self._collection.add(
            documents=[content],
            metadatas=[clean_meta],
            ids=[doc_id],
        )
        return doc_id

    def add_findings(
        self,
        findings: list[tuple[str, dict[str, Any] | None]],
    ) -> list[str]:
        """
        Add multiple findings in a single batch.

        Args:
            findings: List of (content, metadata) tuples.

        Returns:
            List of generated document IDs.
        """
        if not findings:
            return []

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str]] = []

        for content, metadata in findings:
            doc_id = f"finding_{uuid.uuid4().hex[:8]}"
            ids.append(doc_id)
            documents.append(content)
            clean = {k: str(v) for k, v in (metadata or {}).items()
                     if isinstance(v, (str, int, float, bool))}
            clean["stored_at"] = str(time.time())
            metadatas.append(clean)

        self._collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        return ids

    def search(
        self,
        query: str,
        n_results: int = 5,
    ) -> list[SearchResult]:
        """
        Search findings by semantic similarity to query text.

        Args:
            query: Natural language query string.
            n_results: Maximum number of results.

        Returns:
            List of SearchResult ordered by relevance (closest first).
        """
        if self.count() == 0:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=min(n_results, self.count()),
        )

        return self._build_results(results)

    def search_similar(
        self,
        content: str,
        n_results: int = 5,
    ) -> list[SearchResult]:
        """
        Find findings semantically similar to a given finding text.

        Useful for novelty detection — if a new finding is too similar
        to existing ones, it may not be novel.

        Args:
            content: Finding text to compare against.
            n_results: Maximum number of results.

        Returns:
            List of SearchResult ordered by similarity (closest first).
        """
        return self.search(content, n_results=n_results)

    def count(self) -> int:
        """Return the number of stored findings."""
        return self._collection.count()

    def clear(self) -> None:
        """Delete all findings from the collection."""
        with contextlib.suppress(ValueError, NotFoundError):
            self._client.delete_collection(self._collection_name)
        self._collection = self._client.create_collection(self._collection_name)

    def get_all(self) -> list[SearchResult]:
        """Return all stored findings (no semantic ordering)."""
        if self.count() == 0:
            return []
        raw = self._collection.get()
        ids = raw.get("ids", [])
        if not ids:
            return []
        # get() returns flat lists; wrap for _build_results which expects nested
        return self._build_results({
            "ids": [ids],
            "distances": [[0.0] * len(ids)],
            "metadatas": [raw.get("metadatas", [])],
            "documents": [raw.get("documents", [])],
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_results(
        self,
        raw: dict[str, Any],
    ) -> list[SearchResult]:
        """Convert raw ChromaDB response to SearchResult list."""
        parsed: list[SearchResult] = []

        ids_list = raw.get("ids")
        if not ids_list or not ids_list[0]:
            return []
        ids_list = ids_list[0]
        distances = (raw.get("distances") or [[None] * len(ids_list)])[0] or [None] * len(ids_list)
        documents = (raw.get("documents") or [[]])[0] or []
        metadatas = (raw.get("metadatas") or [[]])[0] or []

        for doc_id, dist, doc, meta in zip(
            ids_list, distances, documents, metadatas, strict=False
        ):
            parsed.append(SearchResult(
                content=doc or "",
                score=dist if dist is not None else 1.0,
                metadata=meta or {},
                id=doc_id,
            ))

        return parsed

    @property
    def collection_name(self) -> str:
        return self._collection_name

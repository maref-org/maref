"""Memory Manager — unified three-tier memory architecture for MAREF.

Design principles:
- All critical state externalized (no reliance on LLM context window)
- Memory carries confidence labels and source annotations
- Centralized service (no private agent memory)
- Layered decay: Hot(7d full) → Warm(7-90d summary) → Cold(>90d archive)
- User isolation tags prevent cross-user leakage
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ConfidenceLabel(Enum):
    """Confidence level for memory reliability."""

    CERTAIN = "certain"      # Verified by human or multiple sources
    HIGH = "high"            # Strong evidence
    MEDIUM = "medium"        # Single source, plausible
    LOW = "low"              # Weak evidence, speculative
    UNCERTAIN = "uncertain"  # Unverified, use with caution


class SourceAnnotation(Enum):
    """Source type for memory provenance."""

    HUMAN = "human"              # Direct human input
    AGENT_INFERENCE = "agent"    # Agent-generated
    EXTERNAL_API = "api"         # External system
    OBSERVATION = "observation"  # System observation
    DERIVED = "derived"          # Derived/computed


class UserIsolationTag:
    """Tag for user isolation. Empty = system-wide shared memory."""

    def __init__(self, user_id: str = "", session_id: str = "") -> None:
        self.user_id = user_id
        self.session_id = session_id

    def is_shared(self) -> bool:
        return self.user_id == "" and self.session_id == ""

    def matches(self, other: UserIsolationTag) -> bool:
        if self.is_shared() or other.is_shared():
            return True
        if self.user_id and other.user_id and self.user_id != other.user_id:
            return False
        return True

    def __repr__(self) -> str:
        return f"UserIsolationTag(user={self.user_id!r}, session={self.session_id!r})"


@dataclass
class MemoryRecord:
    """A single memory record with metadata."""

    memory_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: dict[str, Any] = field(default_factory=dict)
    confidence: ConfidenceLabel = ConfidenceLabel.MEDIUM
    source: SourceAnnotation = SourceAnnotation.AGENT_INFERENCE
    user_tag: UserIsolationTag = field(default_factory=UserIsolationTag)
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0          # 0 = no expiration
    access_count: int = 0
    last_accessed_at: float = field(default_factory=time.time)
    linked_task_ids: list[str] = field(default_factory=list)
    summary: str = ""                # For compressed/archive form

    def is_expired(self) -> bool:
        if self.expires_at == 0:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        self.last_accessed_at = time.time()
        self.access_count += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "confidence": self.confidence.value,
            "source": self.source.value,
            "user_id": self.user_tag.user_id,
            "session_id": self.user_tag.session_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at,
            "linked_task_ids": self.linked_task_ids,
            "summary": self.summary,
        }


@dataclass
class MemoryQuery:
    """Query parameters for memory retrieval."""

    keywords: list[str] = field(default_factory=list)
    task_id: str = ""
    user_tag: UserIsolationTag = field(default_factory=UserIsolationTag)
    min_confidence: ConfidenceLabel = ConfidenceLabel.LOW
    time_range: tuple[float, float] | None = None  # (start, end) timestamps
    limit: int = 10


# --------------------------------------------------------------------------- #
# Tier 1: Working Memory (Hot)
# --------------------------------------------------------------------------- #
class WorkingMemoryStore:
    """Hot-tier memory: runtime state, TTL minutes, Pub/Sub sync.

    In production this wraps Redis with Pub/Sub. Here we use in-memory
    dict for local development and testing.
    """

    DEFAULT_TTL_SECONDS = 600  # 10 minutes

    def __init__(self, ttl_seconds: float | None = None) -> None:
        self._ttl = ttl_seconds if ttl_seconds is not None else self.DEFAULT_TTL_SECONDS
        self._store: dict[str, MemoryRecord] = {}
        self._subscribers: list[Callable[[str, MemoryRecord], None]] = []

    def put(self, record: MemoryRecord) -> MemoryRecord:
        """Store a record in working memory with TTL."""
        record.expires_at = time.time() + self._ttl
        self._store[record.memory_id] = record
        self._publish("put", record)
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a record, returning None if expired."""
        record = self._store.get(memory_id)
        if record is None:
            return None
        if record.is_expired():
            self._store.pop(memory_id, None)
            return None
        record.touch()
        return record

    def query(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Query working memory by keywords and user tag."""
        results: list[MemoryRecord] = []
        for record in list(self._store.values()):
            if record.is_expired():
                self._store.pop(record.memory_id, None)
                continue
            if not record.user_tag.matches(query.user_tag):
                continue
            if query.task_id and query.task_id not in record.linked_task_ids:
                continue
            if query.keywords:
                content_str = str(record.content).lower()
                if not any(kw.lower() in content_str for kw in query.keywords):
                    continue
            results.append(record)
        results.sort(key=lambda r: r.last_accessed_at, reverse=True)
        return results[: query.limit]

    def remove(self, memory_id: str) -> bool:
        """Remove a record."""
        if memory_id in self._store:
            record = self._store.pop(memory_id)
            self._publish("remove", record)
            return True
        return False

    def clear_expired(self) -> int:
        """Remove all expired records. Returns count removed."""
        expired = [mid for mid, r in self._store.items() if r.is_expired()]
        for mid in expired:
            self._store.pop(mid, None)
        return len(expired)

    def checkpoint(self) -> dict[str, Any]:
        """Serialize all non-expired records for recovery."""
        return {
            mid: r.to_dict()
            for mid, r in self._store.items()
            if not r.is_expired()
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore from checkpoint."""
        for mid, d in data.items():
            record = MemoryRecord(
                memory_id=d.get("memory_id", mid),
                content=d.get("content", {}),
                confidence=ConfidenceLabel(d.get("confidence", "medium")),
                source=SourceAnnotation(d.get("source", "agent")),
                user_tag=UserIsolationTag(
                    d.get("user_id", ""), d.get("session_id", "")
                ),
                created_at=d.get("created_at", time.time()),
                expires_at=d.get("expires_at", 0),
                access_count=d.get("access_count", 0),
                last_accessed_at=d.get("last_accessed_at", time.time()),
                linked_task_ids=d.get("linked_task_ids", []),
                summary=d.get("summary", ""),
            )
            self._store[mid] = record

    def subscribe(self, callback: Callable[[str, MemoryRecord], None]) -> None:
        self._subscribers.append(callback)

    def _publish(self, event: str, record: MemoryRecord) -> None:
        for cb in self._subscribers:
            cb(event, record)

    def __len__(self) -> int:
        return len(self._store)


# --------------------------------------------------------------------------- #
# Tier 2: Episodic Memory (Warm)
# --------------------------------------------------------------------------- #
class EpisodicMemoryStore:
    """Warm-tier memory: historical task records, SQL-like query.

    In production this wraps PostgreSQL. Here we use in-memory list.
    """

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    def append(self, record: MemoryRecord) -> None:
        """Append a task episode."""
        self._records.append(record)

    def query(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Query episodic memory with filtering."""
        results: list[MemoryRecord] = []
        for record in self._records:
            if not record.user_tag.matches(query.user_tag):
                continue
            if query.task_id and query.task_id not in record.linked_task_ids:
                continue
            if query.time_range:
                start, end = query.time_range
                if not (start <= record.created_at <= end):
                    continue
            if query.keywords:
                content_str = str(record.content).lower()
                if not any(kw.lower() in content_str for kw in query.keywords):
                    continue
            results.append(record)
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[: query.limit]

    def get_agent_history(
        self,
        agent_id: str,
        user_tag: UserIsolationTag | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Get historical episodes for a specific agent."""
        tag = user_tag or UserIsolationTag()
        results = [
            r for r in self._records
            if r.user_tag.matches(tag)
            and r.content.get("agent_id") == agent_id
        ]
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    def summarize_episodes(
        self,
        task_type: str,
        user_tag: UserIsolationTag | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Summarize episodes of a given task type.

        Compression: 100 detailed logs → 1 summary.
        """
        tag = user_tag or UserIsolationTag()
        episodes = [
            r for r in self._records
            if r.user_tag.matches(tag)
            and r.content.get("task_type") == task_type
        ]
        episodes.sort(key=lambda r: r.created_at, reverse=True)
        episodes = episodes[:limit]

        total = len(episodes)
        if total == 0:
            return {"task_type": task_type, "count": 0, "summary": "No episodes found"}

        success_count = sum(
            1 for e in episodes if e.content.get("outcome") == "success"
        )
        avg_duration = sum(
            e.content.get("duration_ms", 0) for e in episodes
        ) / max(total, 1)

        return {
            "task_type": task_type,
            "count": total,
            "success_rate": success_count / total,
            "avg_duration_ms": round(avg_duration, 2),
            "latest_episode": episodes[0].created_at if episodes else None,
            "summary": f"{total} episodes, {success_count}/{total} success, avg {avg_duration:.0f}ms",
        }

    def archive_old(self, max_age_days: float = 90) -> list[MemoryRecord]:
        """Move records older than max_age_days to archive (return them for cold storage)."""
        cutoff = time.time() - max_age_days * 86400
        archived: list[MemoryRecord] = []
        remaining: list[MemoryRecord] = []
        for record in self._records:
            if record.created_at < cutoff:
                # Compress: generate summary if not present
                if not record.summary:
                    record.summary = str(record.content)[:200]
                archived.append(record)
            else:
                remaining.append(record)
        self._records = remaining
        return archived

    def __len__(self) -> int:
        return len(self._records)


# --------------------------------------------------------------------------- #
# Tier 3: Semantic Memory (Cold)
# --------------------------------------------------------------------------- #
class SemanticMemoryStore:
    """Cold-tier memory: knowledge ontology, semantic retrieval.

    In production this wraps a vector DB (e.g., pgvector). Here we use
    simple keyword matching as a placeholder.
    """

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}

    def store(self, record: MemoryRecord) -> MemoryRecord:
        """Store a semantic memory (knowledge fact, schema, ontology)."""
        self._records[record.memory_id] = record
        return record

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve by ID."""
        record = self._records.get(memory_id)
        if record:
            record.touch()
        return record

    def query(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Semantic query by keywords (placeholder for vector search)."""
        results: list[tuple[float, MemoryRecord]] = []
        for record in self._records.values():
            if not record.user_tag.matches(query.user_tag):
                continue
            # Simple keyword relevance scoring
            content_str = str(record.content).lower()
            score = sum(1.0 for kw in query.keywords if kw.lower() in content_str)
            if score > 0:
                results.append((score, record))
        results.sort(key=lambda x: (-x[0], -x[1].access_count))
        return [r for _, r in results[: query.limit]]

    def get_ontology(self, concept: str) -> list[MemoryRecord]:
        """Retrieve knowledge about a specific concept."""
        return [
            r for r in self._records.values()
            if r.content.get("concept") == concept
        ]

    def __len__(self) -> int:
        return len(self._records)


# --------------------------------------------------------------------------- #
# Unified Manager
# --------------------------------------------------------------------------- #
class MemoryManager:
    """Unified interface for MAREF's three-tier memory system.

    Usage:
        mm = MemoryManager()
        # Agent crash recovery
        checkpoint = mm.working.checkpoint()
        # ... crash ...
        mm.working.restore(checkpoint)

        # Query another agent's history
        history = mm.episodic.get_agent_history("agent-b", limit=10)

        # Semantic retrieval
        facts = mm.semantic.query(MemoryQuery(keywords=["pricing", "model"]))
    """

    def __init__(self) -> None:
        self.working = WorkingMemoryStore()
        self.episodic = EpisodicMemoryStore()
        self.semantic = SemanticMemoryStore()

    def create_record(
        self,
        content: dict[str, Any],
        confidence: ConfidenceLabel = ConfidenceLabel.MEDIUM,
        source: SourceAnnotation = SourceAnnotation.AGENT_INFERENCE,
        user_tag: UserIsolationTag | None = None,
        task_ids: list[str] | None = None,
    ) -> MemoryRecord:
        """Factory for creating a properly annotated memory record."""
        return MemoryRecord(
            content=content,
            confidence=confidence,
            source=source,
            user_tag=user_tag or UserIsolationTag(),
            linked_task_ids=task_ids or [],
        )

    def query_all_tiers(
        self,
        query: MemoryQuery,
    ) -> dict[str, list[MemoryRecord]]:
        """Query across all three memory tiers."""
        return {
            "working": self.working.query(query),
            "episodic": self.episodic.query(query),
            "semantic": self.semantic.query(query),
        }

    def decay_and_archive(self) -> dict[str, int]:
        """Run decay cycle:
        - Clear expired working memory
        - Archive old episodic memory to semantic
        Returns counts of affected records.
        """
        cleared = self.working.clear_expired()
        archived = self.episodic.archive_old(max_age_days=90)
        for record in archived:
            self.semantic.store(record)
        return {
            "working_expired": cleared,
            "episodic_archived": len(archived),
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            "working_count": len(self.working),
            "episodic_count": len(self.episodic),
            "semantic_count": len(self.semantic),
        }

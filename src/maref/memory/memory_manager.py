"""Memory Manager — unified three-tier memory architecture for MAREF.

Design principles:
- All critical state externalized (no reliance on LLM context window)
- Memory carries confidence labels and source annotations
- Centralized service (no private agent memory)
- Layered decay: Hot(7d full) → Warm(7-90d summary) → Cold(>90d archive)
- User isolation tags prevent cross-user leakage
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast


class ConfidenceLabel(Enum):
    """Confidence level for memory reliability."""

    CERTAIN = "certain"  # Verified by human or multiple sources
    HIGH = "high"  # Strong evidence
    MEDIUM = "medium"  # Single source, plausible
    LOW = "low"  # Weak evidence, speculative
    UNCERTAIN = "uncertain"  # Unverified, use with caution


class SourceAnnotation(Enum):
    """Source type for memory provenance."""

    HUMAN = "human"  # Direct human input
    AGENT_INFERENCE = "agent"  # Agent-generated
    EXTERNAL_API = "api"  # External system
    OBSERVATION = "observation"  # System observation
    DERIVED = "derived"  # Derived/computed


class PiiCategory(Enum):
    """v0.53 S3 记忆治理 — 个人敏感信息（PII）类别（个保法/AI Act）。"""

    EMAIL = "email"
    PHONE = "phone"
    ID_CARD = "id_card"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    NAME = "name"


_PII_PATTERNS: dict[PiiCategory, str] = {
    PiiCategory.EMAIL: r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    # 支持 +86 国际前缀与 -/ 分隔符：13812345678 / 138-1234-5678 / +86 138-1234-5678
    PiiCategory.PHONE: r"(?<!\d)(?:\+?86[- ]?)?(?:1[3-9]\d{9}|1[3-9]\d[- ]?\d{4}[- ]?\d{4})(?!\d)",
    PiiCategory.ID_CARD: r"(?<!\d)\d{17}[\dXx](?!\d)",
    PiiCategory.SSN: r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)",
    PiiCategory.CREDIT_CARD: r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}(?!\d)",
    PiiCategory.IP_ADDRESS: r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)",
}

# NAME 类无正则模式，仅按字段键识别
_PII_FIELD_KEYS: dict[PiiCategory, tuple[str, ...]] = {
    PiiCategory.EMAIL: ("email", "mail"),
    PiiCategory.PHONE: ("phone", "mobile", "tel", "contact"),
    PiiCategory.ID_CARD: ("id_card", "passport", "national_id", "ssn", "identity_number"),
    PiiCategory.CREDIT_CARD: ("credit_card", "card_number", "card_no", "pan"),
    PiiCategory.IP_ADDRESS: ("ip", "ip_address", "client_ip", "remote_ip"),
    PiiCategory.NAME: ("full_name", "real_name", "display_name"),
}

# 常见带连接词的键映射：email_address/phoneNumber → 类别
_KEY_SUFFIX_ALIASES: dict[str, PiiCategory] = {}


def _category_for_key(key: str) -> PiiCategory | None:
    """字段键 → PII 类别（归一化后精确/后缀匹配，避免 id_card 误入 card 类）。"""
    if not isinstance(key, str):
        return None
    normalized = key.lower().replace("_", "").replace("-", "")
    for cat, keys in _PII_FIELD_KEYS.items():
        for k in keys:
            norm = k.replace("_", "").replace("-", "")
            # 精确 / 后缀（id_card → idcard） / 单词包含（email_address → emailaddress）
            if normalized == norm or normalized.endswith(norm) or norm in normalized:
                return cat
    return None


def _mask(text: str, category: PiiCategory) -> str:
    if category is PiiCategory.EMAIL:
        local, _, domain = text.partition("@")
        shown = local[0] if local else "*"
        return f"{shown}***@{domain}"
    if category is PiiCategory.PHONE:
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 7:
            return f"{digits[:3]}{'*' * (len(digits) - 7)}{digits[-4:]}"
        return "*" * len(text)
    if category in (PiiCategory.ID_CARD, PiiCategory.SSN):
        if len(text) > 10:
            return f"{text[:6]}{'*' * (len(text) - 10)}{text[-4:]}"
        return "*" * len(text)
    if category is PiiCategory.CREDIT_CARD:
        digits = re.sub(r"\D", "", text)
        return f"****-****-****-{digits[-4:]}"
    if category is PiiCategory.IP_ADDRESS:
        parts = text.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.*.*"
        return "*" * len(text)
    # NAME
    return f"{text[0]}{'*' * (len(text) - 1)}" if text else text


def _mask_string(text: str) -> tuple[str, dict[PiiCategory, list[str]]]:
    """掩码一字符串中所有 pattern 类 PII，返回 (脱敏文本, 命中值)。"""
    hits: dict[PiiCategory, list[str]] = {}
    out = text
    for cat, pattern in _PII_PATTERNS.items():
        matches = list(re.finditer(pattern, out))
        if matches:
            hits[cat] = [m.group() for m in matches]
            for m in reversed(matches):
                out = out[: m.start()] + _mask(m.group(), cat) + out[m.end() :]
    return out, hits


def _scan_content(node: Any, mask: bool) -> tuple[Any, dict[PiiCategory, list[str]]]:
    """递归扫描 dict/list/str，detect（mask=False）或去识别（mask=True）。"""
    hits: dict[PiiCategory, list[str]] = {}

    def add(cat: PiiCategory, values: list[str]) -> None:
        bucket = hits.setdefault(cat, [])
        for v in values:
            if v and v not in bucket:
                bucket.append(v)

    if isinstance(node, dict):
        out: Any = {}
        for key, value in node.items():
            cat = _category_for_key(key)
            if cat is not None and isinstance(value, str):
                masked, sub_hits = _mask_string(value)
                if mask:
                    # NAME 无 pattern，或字段键断言的值未被任何 pattern 命中时，
                    # 对整个值做类别掩码兜底，保证 detect 与去识别行为一致。
                    if cat is PiiCategory.NAME or cat not in sub_hits:
                        masked = _mask(value, cat)
                    out[key] = masked
                for c, values in sub_hits.items():
                    add(c, values)
                add(cat, [value])
            else:
                new_value, sub = _scan_content(value, mask)
                out[key] = new_value
                for c, values in sub.items():
                    add(c, values)
        return out, hits
    if isinstance(node, list):
        out = []
        for value in node:
            new_value, sub = _scan_content(value, mask)
            out.append(new_value)
            for c, values in sub.items():
                add(c, values)
        return out, hits
    if isinstance(node, str):
        if mask:
            return _mask_string(node)
        for cat, pattern in _PII_PATTERNS.items():
            values = re.findall(pattern, node)
            if values:
                add(cat, values)
        return node, hits
    return node, hits


def detect_pii(content: Any) -> dict[PiiCategory, list[str]]:
    """静态扫描内容中的 PII，返回 {类别: [匹配到的原始值]}。"""
    return _scan_content(content, mask=False)[1]


def deidentify_content(content: Any) -> tuple[Any, list[PiiCategory]]:
    """对内容做去识别掩码，返回 (脱敏后的副本, 发现的 PII 类别)。不修改入参。"""
    out, hits = _scan_content(content, mask=True)
    return out, list(hits.keys())


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
        return not (self.user_id and other.user_id and self.user_id != other.user_id)

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
    expires_at: float = 0.0  # 0 = no expiration
    access_count: int = 0
    last_accessed_at: float = field(default_factory=time.time)
    linked_task_ids: list[str] = field(default_factory=list)
    summary: str = ""  # For compressed/archive form
    retention_days: int = 0  # 0 = use store default
    pii_categories: list[str] = field(default_factory=list)

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
            "retention_days": self.retention_days,
            "pii_categories": self.pii_categories,
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

    def deidentify(self, memory_id: str) -> bool:
        """Mask PII in a record's content in place. Returns True if PII found."""
        record = self._store.get(memory_id)
        if record is None:
            return False
        content, categories = deidentify_content(record.content)
        if not categories:
            return False
        record.content = cast(dict[str, Any], content)
        record.pii_categories = [c.value for c in categories]
        return True

    def erase_by_user(self, user_id: str) -> int:
        """Erase all records of a user (GDPR Art.17 right to erasure). Returns count."""
        ids = [mid for mid, r in self._store.items() if r.user_tag.user_id == user_id]
        for mid in ids:
            self._store.pop(mid, None)
        return len(ids)

    def purge_expired_retention(self, default_days: int = 90) -> int:
        """Remove records whose retention period elapsed. Returns count.

        基于 last_accessed_at（最近活跃），避免热层被频繁访问的记录
        因 created_at 老化而误清。
        """
        now = time.time()
        ids = [
            mid
            for mid, r in self._store.items()
            if r.last_accessed_at + (r.retention_days or default_days) * 86400 < now
        ]
        for mid in ids:
            self._store.pop(mid, None)
        return len(ids)

    def checkpoint(self) -> dict[str, Any]:
        """Serialize all non-expired records for recovery."""
        return {mid: r.to_dict() for mid, r in self._store.items() if not r.is_expired()}

    def restore(self, data: dict[str, Any]) -> None:
        """Restore from checkpoint."""
        for mid, d in data.items():
            record = MemoryRecord(
                memory_id=d.get("memory_id", mid),
                content=d.get("content", {}),
                confidence=ConfidenceLabel(d.get("confidence", "medium")),
                source=SourceAnnotation(d.get("source", "agent")),
                user_tag=UserIsolationTag(d.get("user_id", ""), d.get("session_id", "")),
                created_at=d.get("created_at", time.time()),
                expires_at=d.get("expires_at", 0),
                access_count=d.get("access_count", 0),
                last_accessed_at=d.get("last_accessed_at", time.time()),
                linked_task_ids=d.get("linked_task_ids", []),
                summary=d.get("summary", ""),
                retention_days=d.get("retention_days", 0),
                pii_categories=d.get("pii_categories", []),
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
            r
            for r in self._records
            if r.user_tag.matches(tag) and r.content.get("agent_id") == agent_id
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
            r
            for r in self._records
            if r.user_tag.matches(tag) and r.content.get("task_type") == task_type
        ]
        episodes.sort(key=lambda r: r.created_at, reverse=True)
        episodes = episodes[:limit]

        total = len(episodes)
        if total == 0:
            return {"task_type": task_type, "count": 0, "summary": "No episodes found"}

        success_count = sum(1 for e in episodes if e.content.get("outcome") == "success")
        avg_duration = sum(e.content.get("duration_ms", 0) for e in episodes) / max(total, 1)

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

    def deidentify(self, memory_id: str) -> bool:
        """Mask PII in a record's content in place. Returns True if PII found."""
        for record in self._records:
            if record.memory_id == memory_id:
                content, categories = deidentify_content(record.content)
                if not categories:
                    return False
                record.content = cast(dict[str, Any], content)
                record.pii_categories = [c.value for c in categories]
                return True
        return False

    def erase(self, memory_id: str) -> bool:
        """Erase a single record."""
        before = len(self._records)
        self._records = [r for r in self._records if r.memory_id != memory_id]
        return before != len(self._records)

    def erase_by_user(self, user_id: str) -> int:
        """Erase all records of a user (GDPR Art.17 right to erasure). Returns count."""
        before = len(self._records)
        self._records = [r for r in self._records if r.user_tag.user_id != user_id]
        return before - len(self._records)

    def purge_expired_retention(self, default_days: int = 90) -> int:
        """Remove records whose retention period elapsed. Returns count."""
        now = time.time()
        before = len(self._records)
        self._records = [
            r
            for r in self._records
            if r.created_at + (r.retention_days or default_days) * 86400 >= now
        ]
        return before - len(self._records)

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
        return [r for r in self._records.values() if r.content.get("concept") == concept]

    def deidentify(self, memory_id: str) -> bool:
        """Mask PII in a record's content in place. Returns True if PII found."""
        record = self._records.get(memory_id)
        if record is None:
            return False
        content, categories = deidentify_content(record.content)
        if not categories:
            return False
        record.content = cast(dict[str, Any], content)
        record.pii_categories = [c.value for c in categories]
        return True

    def erase(self, memory_id: str) -> bool:
        """Erase a single record."""
        return self._records.pop(memory_id, None) is not None

    def erase_by_user(self, user_id: str) -> int:
        """Erase all records of a user (GDPR Art.17 right to erasure). Returns count."""
        ids = [mid for mid, r in self._records.items() if r.user_tag.user_id == user_id]
        for mid in ids:
            self._records.pop(mid, None)
        return len(ids)

    def purge_expired_retention(self, default_days: int = 90) -> int:
        """Remove records whose retention period elapsed. Returns count."""
        now = time.time()
        ids = [
            mid
            for mid, r in self._records.items()
            if r.created_at + (r.retention_days or default_days) * 86400 < now
        ]
        for mid in ids:
            self._records.pop(mid, None)
        return len(ids)

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

    def __init__(
        self,
        on_governance_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.working = WorkingMemoryStore()
        self.episodic = EpisodicMemoryStore()
        self.semantic = SemanticMemoryStore()
        self._on_governance_event = on_governance_event

    def _emit_governance_event(self, name: str, **payload: Any) -> None:
        """发治理事件（去识别/擦除/保留期清理），供审计总线订阅。"""
        if self._on_governance_event is not None:
            self._on_governance_event(name, payload)

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

    def deidentify(self, memory_id: str) -> dict[str, bool]:
        """Mask PII across all tiers for a memory id. Returns per-tier results."""
        stats = {
            "working": self.working.deidentify(memory_id),
            "episodic": self.episodic.deidentify(memory_id),
            "semantic": self.semantic.deidentify(memory_id),
        }
        if any(stats.values()):
            self._emit_governance_event("memory.deidentify", memory_id=memory_id, **stats)
        return stats

    def forget(self, user_id: str) -> dict[str, int]:
        """GDPR Art.17 遗忘权：擦除某用户全部记忆（三个 tier）。返回各层擦除数。

        注意: 仅擦除显式携带该 user_id 的 user_tag 记录；共享标签（空 user_id）
        不属于单个用户，保留不动（需由管理员按系统级策略处理）。
        """
        stats = {
            "working": self.working.erase_by_user(user_id),
            "episodic": self.episodic.erase_by_user(user_id),
            "semantic": self.semantic.erase_by_user(user_id),
        }
        self._emit_governance_event("memory.forget", user_id=user_id, **stats)
        return stats

    def purge_expired_retention(self, default_days: int = 90) -> dict[str, int]:
        """按保留期清理各层过期记忆。返回各层清理数。"""
        stats = {
            "working": self.working.purge_expired_retention(default_days),
            "episodic": self.episodic.purge_expired_retention(default_days),
            "semantic": self.semantic.purge_expired_retention(default_days),
        }
        self._emit_governance_event("memory.retention_purge", default_days=default_days, **stats)
        return stats

    def get_stats(self) -> dict[str, Any]:
        return {
            "working_count": len(self.working),
            "episodic_count": len(self.episodic),
            "semantic_count": len(self.semantic),
        }

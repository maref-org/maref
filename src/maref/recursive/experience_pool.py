from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


def _compute_precondition_hash(context: str) -> str:
    return hashlib.sha256(context.encode()).hexdigest()[:16]


@dataclass
class ExperienceEntry:
    entry_id: str
    timestamp: float
    context: str
    decision: str
    outcome: str
    lesson_learned: str
    tags: list[str] = field(default_factory=list)
    version_tag: str = "unknown"
    precondition_hash: str | None = None
    decay_factor: float = 1.0


class ExperiencePool:
    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: list[ExperienceEntry] = []
        self._by_tag: dict[str, list[int]] = defaultdict(list)
        self._by_outcome: dict[str, list[int]] = defaultdict(list)
        self._max_entries = max_entries
        self._on_store: list[Callable[[ExperienceEntry], None]] = []

    def on_store(self, callback: Callable[[ExperienceEntry], None]) -> None:
        """Register a callback invoked on every new entry. Enables bidirectional bridges."""
        self._on_store.append(callback)

    def store(self, entry: ExperienceEntry) -> None:
        if len(self._entries) >= self._max_entries:
            self._entries.pop(0)
            self._rebuild_indices()
        idx = len(self._entries)
        self._entries.append(entry)
        for tag in entry.tags:
            self._by_tag[tag].append(idx)
        self._by_outcome[entry.outcome].append(idx)
        for cb in self._on_store:
            cb(entry)

    def query_by_tag(self, tag: str) -> list[ExperienceEntry]:
        return [self._entries[i] for i in self._by_tag.get(tag, [])]

    def query_by_outcome(self, outcome: str) -> list[ExperienceEntry]:
        return [self._entries[i] for i in self._by_outcome.get(outcome, [])]

    def all_entries(self) -> list[ExperienceEntry]:
        """Return all entries in the pool."""
        return list(self._entries)

    def query_by_context(self, keyword: str) -> list[ExperienceEntry]:
        return [e for e in self._entries if keyword.lower() in e.context.lower()]

    def search_similar(self, context: str, max_results: int = 5) -> list[ExperienceEntry]:
        scored: list[tuple[float, ExperienceEntry]] = []
        words = set(context.lower().split())
        for entry in self._entries:
            entry_words = set(entry.context.lower().split())
            overlap = len(words & entry_words)
            if overlap > 0:
                scoring = overlap / max(len(words), 1)
                scored.append((scoring, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:max_results]]

    def replay_lessons(self, threshold_outcome: str = "failure") -> list[str]:
        failures = self.query_by_outcome(threshold_outcome)
        return [f.lesson_learned for f in failures]

    def search_similar_with_decay(
        self, context: str, current_version: str | None = None, max_results: int = 5
    ) -> list[ExperienceEntry]:
        now = time.time()
        scored: list[tuple[float, ExperienceEntry]] = []
        words = set(context.lower().split())
        for entry in self._entries:
            entry_words = set(entry.context.lower().split())
            overlap = len(words & entry_words)
            if overlap == 0:
                continue
            relevance = overlap / max(len(words), 1)
            age_hours = (now - entry.timestamp) / 3600.0
            time_decay = entry.decay_factor / (1.0 + age_hours / 24.0)
            version_match = 1.0 if current_version and entry.version_tag == current_version else 0.7
            score = relevance * time_decay * version_match
            scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:max_results]]

    def purge_stale(self, max_age_hours: float = 720.0) -> int:
        cutoff = time.time() - max_age_hours * 3600.0
        kept = [e for e in self._entries if e.timestamp >= cutoff]
        removed = len(self._entries) - len(kept)
        self._entries = kept
        self._rebuild_indices()
        return removed

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._by_tag.clear()
        self._by_outcome.clear()

    def _rebuild_indices(self) -> None:
        self._by_tag.clear()
        self._by_outcome.clear()
        for i, entry in enumerate(self._entries):
            for tag in entry.tags:
                self._by_tag[tag].append(i)
            self._by_outcome[entry.outcome].append(i)

    def store_with_reward(
        self,
        context: str,
        decision: str,
        outcome: str,
        reward_vector: Any,
        tags: list[str] | None = None,
    ) -> ExperienceEntry:
        """存储带奖励向量的经验条目。"""
        import uuid as _uuid
        reward_tags = []
        if hasattr(reward_vector, "dim_scores"):
            scores = reward_vector.dim_scores()
            reward_tags = [
                f"success:{scores.get('task_success', 0.0):.2f}",
                f"g1:{scores.get('metacognition', 0.0):.2f}",
                f"g2:{scores.get('subgoal', 0.0):.2f}",
                f"g3:{scores.get('safety', 0.0):.2f}",
                f"g4:{scores.get('resource', 0.0):.2f}",
                f"g5:{scores.get('cross_instance', 0.0):.2f}",
            ]
        all_tags = (tags or []) + reward_tags
        entry = ExperienceEntry(
            entry_id=str(_uuid.uuid4()),
            timestamp=time.time(),
            context=context,
            decision=decision,
            outcome=outcome,
            lesson_learned="",
            tags=all_tags,
        )
        self.store(entry)
        return entry

    def query_by_reward_range(
        self,
        dimension: str,
        min_score: float = 0.0,
        max_score: float = 1.0,
    ) -> list[ExperienceEntry]:
        """按奖励维度范围查询经验。"""
        prefix = f"{dimension}:"
        results = []
        for entry in self._entries:
            for tag in entry.tags:
                if tag.startswith(prefix):
                    try:
                        score = float(tag[len(prefix):])
                        if min_score <= score <= max_score:
                            results.append(entry)
                            break
                    except ValueError:
                        continue
        return results


class ContextManager:
    def __init__(self, max_sessions: int = 50) -> None:
        self._sessions: list[dict[str, Any]] = []
        self._active: str | None = None
        self._max_sessions = max_sessions

    def start_session(self, session_id: str, **metadata: Any) -> None:
        self._active = session_id
        self._sessions.append(
            {
                "session_id": session_id,
                "started_at": time.time(),
                "metadata": metadata,
                "context_stack": [],
                "decision_count": 0,
            }
        )

    def push_context(self, key: str, value: Any) -> None:
        if self._active is None:
            return
        session = self._find_session(self._active)
        if session:
            session["context_stack"].append({"key": key, "value": value, "timestamp": time.time()})

    def pop_context(self) -> dict[str, Any] | None:
        if self._active is None:
            return None
        session = self._find_session(self._active)
        if session and session["context_stack"]:
            return session["context_stack"].pop()
        return None

    def record_decision(self, decision: str) -> None:
        if self._active is None:
            return
        session = self._find_session(self._active)
        if session:
            session["decision_count"] += 1

    def get_active_context(self) -> dict[str, Any] | None:
        if self._active is None:
            return None
        return self._find_session(self._active)

    def end_session(self) -> dict[str, Any] | None:
        if self._active is None:
            return None
        session = self._find_session(self._active)
        if session:
            while len(self._sessions) > self._max_sessions:
                self._sessions.pop(0)
        self._active = None
        return session

    def session_count(self) -> int:
        return len(self._sessions)

    def _find_session(self, session_id: str) -> dict[str, Any] | None:
        for s in self._sessions:
            if s["session_id"] == session_id:
                return s
        return None

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from maref.execution.harness.epitaph import DeathCause, Epitaph, EpitaphWriter
from maref.recursive.hook_registry import HookRegistry, HookResult, HookVerdict
from maref.recursive.hook_topics import MarefTopic

SHADOW_HMAC_KEY = "shadow-registry-integrity-key"


@dataclass
class ShadowEntry:
    entry_id: str
    agent_id: str
    lineage: str
    death_cause: str
    lifespan_seconds: float
    tasks_completed: int
    tasks_failed: int
    total_lives: int
    trust_legacy: float
    epitaph_id: str | None
    assimilated_delta_ids: list[str]
    timestamp: float
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "agent_id": self.agent_id,
            "lineage": self.lineage,
            "death_cause": self.death_cause,
            "lifespan_seconds": round(self.lifespan_seconds, 2),
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "total_lives": self.total_lives,
            "trust_legacy": round(self.trust_legacy, 4),
            "epitaph_id": self.epitaph_id,
            "assimilated_delta_ids": self.assimilated_delta_ids,
            "timestamp": self.timestamp,
            "signature": self.signature[:16],
        }

    def verify_signature(self, hmac_key: str = SHADOW_HMAC_KEY) -> bool:
        payload = json.dumps({
            "entry_id": self.entry_id,
            "agent_id": self.agent_id,
            "lineage": self.lineage,
            "death_cause": self.death_cause,
            "lifespan_seconds": self.lifespan_seconds,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "total_lives": self.total_lives,
            "trust_legacy": self.trust_legacy,
            "epitaph_id": self.epitaph_id,
            "assimilated_delta_ids": self.assimilated_delta_ids,
            "timestamp": self.timestamp,
        }, sort_keys=True)
        expected = hmac.new(
            hmac_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)


class ShadowRegistry:
    def __init__(self, hmac_key: str = SHADOW_HMAC_KEY) -> None:
        self._entries: list[ShadowEntry] = []
        self._by_entry_id: dict[str, ShadowEntry] = {}
        self._by_agent: dict[str, list[ShadowEntry]] = {}
        self._hmac_key = hmac_key

    def _sign(self, payload_dict: dict[str, Any]) -> str:
        payload = json.dumps(payload_dict, sort_keys=True)
        return hmac.new(
            self._hmac_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

    def is_empty(self) -> bool:
        return len(self._entries) == 0

    @property
    def total_entries(self) -> int:
        return len(self._entries)

    def append(self, entry: ShadowEntry) -> None:
        if entry.entry_id in self._by_entry_id:
            return
        if not entry.verify_signature(self._hmac_key):
            raise ValueError(f"ShadowEntry {entry.entry_id} has invalid signature")
        self._entries.append(entry)
        self._by_entry_id[entry.entry_id] = entry
        self._by_agent.setdefault(entry.agent_id, []).append(entry)

    def create_entry(
        self,
        agent_id: str,
        lineage: str,
        death_cause: DeathCause | str,
        lifespan_seconds: float = 0.0,
        tasks_completed: int = 0,
        tasks_failed: int = 0,
        total_lives: int = 1,
        trust_legacy: float = 0.5,
        epitaph_id: str | None = None,
        assimilated_delta_ids: list[str] | None = None,
    ) -> ShadowEntry:
        cause = death_cause.value if isinstance(death_cause, DeathCause) else death_cause
        entry_id = uuid.uuid4().hex[:12]
        ts = time.time()
        payload = {
            "entry_id": entry_id,
            "agent_id": agent_id,
            "lineage": lineage,
            "death_cause": cause,
            "lifespan_seconds": lifespan_seconds,
            "tasks_completed": tasks_completed,
            "tasks_failed": tasks_failed,
            "total_lives": total_lives,
            "trust_legacy": trust_legacy,
            "epitaph_id": epitaph_id,
            "assimilated_delta_ids": assimilated_delta_ids or [],
            "timestamp": ts,
        }
        signature = self._sign(payload)
        entry = ShadowEntry(
            entry_id=entry_id,
            agent_id=agent_id,
            lineage=lineage,
            death_cause=cause,
            lifespan_seconds=lifespan_seconds,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            total_lives=total_lives,
            trust_legacy=trust_legacy,
            epitaph_id=epitaph_id,
            assimilated_delta_ids=assimilated_delta_ids or [],
            timestamp=ts,
            signature=signature,
        )
        self.append(entry)
        return entry

    def from_epitaph(
        self,
        epitaph: Epitaph,
        assimilated_delta_ids: list[str] | None = None,
    ) -> ShadowEntry:
        return self.create_entry(
            agent_id=epitaph.agent_id,
            lineage=epitaph.lineage,
            death_cause=epitaph.death_cause,
            lifespan_seconds=epitaph.autopsy.lifespan_seconds,
            tasks_completed=epitaph.autopsy.tasks_completed,
            tasks_failed=epitaph.autopsy.tasks_failed,
            total_lives=epitaph.total_lives,
            trust_legacy=epitaph.crystallized.trust_legacy,
            epitaph_id=epitaph.epitaph_id,
            assimilated_delta_ids=assimilated_delta_ids,
        )

    def get_by_entry_id(self, entry_id: str) -> ShadowEntry | None:
        return self._by_entry_id.get(entry_id)

    def get_by_agent(self, agent_id: str) -> list[ShadowEntry]:
        return list(self._by_agent.get(agent_id, []))

    def get_by_lineage_prefix(self, prefix: str) -> list[ShadowEntry]:
        return [
            e for e in self._entries
            if e.lineage == prefix or e.lineage.startswith(prefix + "->")
        ]

    def get_by_death_cause(self, cause: str) -> list[ShadowEntry]:
        return [e for e in self._entries if e.death_cause == cause]

    def get_by_time_range(
        self, start: float, end: float
    ) -> list[ShadowEntry]:
        return [
            e for e in self._entries
            if start <= e.timestamp <= end
        ]

    def get_recent(self, limit: int = 10) -> list[ShadowEntry]:
        return list(self._entries[-limit:])

    def get_all(self) -> list[ShadowEntry]:
        return list(self._entries)

    def count_by_agent(self, agent_id: str) -> int:
        return len(self._by_agent.get(agent_id, []))

    def count_by_death_cause(self, cause: str) -> int:
        return sum(1 for e in self._entries if e.death_cause == cause)

    def aggregated_stats(self) -> dict[str, Any]:
        causes: dict[str, int] = {}
        total_trust = 0.0
        for e in self._entries:
            causes[e.death_cause] = causes.get(e.death_cause, 0) + 1
            total_trust += e.trust_legacy
        trust_avg = (total_trust / len(self._entries)) if self._entries else 0.5
        return {
            "total_entries": self.total_entries,
            "unique_agents": len(self._by_agent),
            "death_cause_distribution": causes,
            "average_trust_legacy": round(trust_avg, 4),
        }

    def verify_integrity(self) -> dict[str, Any]:
        verified = 0
        failed = 0
        for entry in self._entries:
            if entry.verify_signature(self._hmac_key):
                verified += 1
            else:
                failed += 1
        return {
            "total": self.total_entries,
            "verified": verified,
            "failed": failed,
            "intact": failed == 0,
        }

    def register_epitaph_hook(
        self, hook_registry: HookRegistry, writer: EpitaphWriter
    ) -> None:
        def _on_epitaph(event_data: dict[str, Any]) -> HookResult:
            agent_id = event_data.get("agent_id", "")
            epitaph = writer.get_epitaph(agent_id)
            if epitaph is None:
                return HookResult(
                    verdict=HookVerdict.PASS,
                    handler_id="shadow-registry",
                    message="no epitaph found for agent",
                )
            self.from_epitaph(epitaph)
            return HookResult(
                verdict=HookVerdict.PASS,
                handler_id="shadow-registry",
                message=f"registered shadow entry for {agent_id}",
            )

        hook_registry.register(
            MarefTopic.AGENT_EPITAPH_READY,
            _on_epitaph,
            priority=40,
            handler_id="shadow-registry",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "unique_agents": len(self._by_agent),
            "stats": self.aggregated_stats(),
            "integrity": self.verify_integrity(),
            "recent_entries": [e.to_dict() for e in self._entries[-5:]],
        }

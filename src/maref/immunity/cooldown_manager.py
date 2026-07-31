from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maref.recursive.unified_audit import NullAuditStore
from maref.security.decorators import security_critical

if TYPE_CHECKING:
    from maref.immunity.cross_gen_simulator import CrossGenerationImpactSimulator
    from maref.recursive.unified_audit import UnifiedAuditStore
COOLDOWN_DURATION = 86400.0

@dataclass
class CooldownEntry:
    cooldown_id: str
    agent_id: str
    code: str
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = 'cooling'
    submitted_at: float = field(default_factory=time.time)
    evaluated_at: float = 0.0
    contamination_index: float = 0.0
    blocked: bool = False
    merged: bool = False
    force_merged: bool = False

class CooldownManager:

    def __init__(self, simulator: CrossGenerationImpactSimulator | None=None, audit_store: UnifiedAuditStore | None=None, cooldown_seconds: float=COOLDOWN_DURATION) -> None:
        self._entries: dict[str, CooldownEntry] = {}
        self._simulator = simulator
        self._audit_store = audit_store or NullAuditStore()
        self._cooldown_seconds = cooldown_seconds

    @security_critical
    def submit_code(self, agent_id: str, code: str, metadata: dict[str, Any] | None=None) -> str:
        cooldown_id = f'cd_{uuid.uuid4().hex[:8]}'
        entry = CooldownEntry(cooldown_id=cooldown_id, agent_id=agent_id, code=code, metadata=metadata or {})
        self._entries[cooldown_id] = entry
        self._write_audit('submitted', cooldown_id, f'Code submitted for cooldown by {agent_id}')
        return cooldown_id

    def get_status(self, cooldown_id: str) -> dict[str, Any]:
        entry = self._entries.get(cooldown_id)
        if entry is None:
            return {'error': 'cooldown_id not found'}
        elapsed = time.time() - entry.submitted_at
        remaining = max(0.0, self._cooldown_seconds - elapsed)
        cooldown_done = elapsed >= self._cooldown_seconds
        return {'cooldown_id': cooldown_id, 'agent_id': entry.agent_id, 'status': entry.status, 'elapsed_seconds': round(elapsed, 1), 'remaining_seconds': round(remaining, 1), 'cooldown_done': cooldown_done, 'contamination_index': entry.contamination_index, 'blocked': entry.blocked, 'merged': entry.merged, 'force_merged': entry.force_merged}

    @security_critical
    def evaluate(self, cooldown_id: str) -> dict[str, Any]:
        entry = self._entries.get(cooldown_id)
        if entry is None:
            return {'error': 'cooldown_id not found'}
        if self._simulator is None:
            entry.status = 'no_simulator'
            return {'error': 'no simulator attached'}
        report = self._simulator.simulate_contamination(entry.code)
        entry.contamination_index = report.contamination_index
        entry.blocked = report.blocked
        entry.evaluated_at = time.time()
        if report.blocked:
            entry.status = 'blocked'
            self._write_audit('blocked', cooldown_id, f'Contamination index {report.contamination_index} >= 0.7, merge blocked')
        else:
            entry.status = 'cooling'
        return {'cooldown_id': cooldown_id, 'contamination_index': report.contamination_index, 'blocked': report.blocked, 'findings': len(report.findings)}

    @security_critical
    def auto_merge(self, cooldown_id: str) -> dict[str, Any]:
        entry = self._entries.get(cooldown_id)
        if entry is None:
            return {'success': False, 'reason': 'cooldown_id not found'}
        elapsed = time.time() - entry.submitted_at
        if elapsed < self._cooldown_seconds:
            return {'success': False, 'reason': f'cooldown not finished ({elapsed:.0f}s < {self._cooldown_seconds}s)'}
        if entry.blocked:
            return {'success': False, 'reason': 'code is blocked due to contamination'}
        entry.status = 'merged'
        entry.merged = True
        self._write_audit('merged', cooldown_id, 'Code auto-merged after clean cooldown')
        return {'success': True, 'cooldown_id': cooldown_id, 'action': 'auto_merged'}

    @security_critical
    def force_merge(self, cooldown_id: str, actor_id: str, reason: str = 'manual_override') -> dict[str, Any]:
        entry = self._entries.get(cooldown_id)
        if entry is None:
            return {'success': False, 'reason': 'cooldown_id not found'}
        if not reason or not reason.strip():
            return {'success': False, 'reason': 'reason must be non-empty'}
        if not entry.evaluated_at and self._simulator is not None:
            report = self._simulator.simulate_contamination(entry.code)
            entry.contamination_index = report.contamination_index
            entry.blocked = report.blocked
            entry.evaluated_at = time.time()
        if entry.blocked and entry.contamination_index >= 0.7:
            notification = f'FORCE MERGE of contaminated code (index={entry.contamination_index:.2f}) by agent {entry.agent_id}. Reason: {reason}'
        else:
            notification = f'Force merge of clean or unevaluated code by agent {entry.agent_id}. Reason: {reason}'
        entry.status = 'force_merged'
        entry.merged = True
        entry.force_merged = True
        self._write_audit('force_merged', cooldown_id, notification)
        return {'success': True, 'cooldown_id': cooldown_id, 'action': 'force_merged'}

    @security_critical
    def auto_archive_expired(self, max_age_days: int=7) -> list[str]:
        """Auto-archive cooldown entries that have exceeded max_age_days without evaluation.

        Entries in 'cooling' status that were submitted more than max_age_days ago
        are archived (status changed to 'archived').

        Returns list of archived cooldown IDs.
        """
        now = time.time()
        archived = []
        for entry in list(self._entries.values()):
            if entry.status != 'cooling':
                continue
            age_days = (now - entry.submitted_at) / 86400
            if age_days >= max_age_days:
                entry.status = 'archived'
                self._write_audit('cooldown_archived', entry.cooldown_id, f'auto_archive after {max_age_days}d')
                archived.append(entry.cooldown_id)
        return archived

    def get_overdue_entries(self, grace_days: int=7) -> list[CooldownEntry]:
        """Return entries that are past due for evaluation."""
        now = time.time()
        overdue = []
        for entry in self._entries.values():
            if entry.status != 'cooling':
                continue
            age_days = (now - entry.submitted_at) / 86400
            if age_days >= grace_days:
                overdue.append(entry)
        return overdue

    def get_all_entries(self) -> list[CooldownEntry]:
        return list(self._entries.values())

    def get_cooldown_seconds(self) -> float:
        return self._cooldown_seconds

    def _write_audit(self, event_type: str, cooldown_id: str, justification: str) -> None:
        from maref.recursive.unified_audit import UnifiedAuditRecord
        entry = self._entries.get(cooldown_id)
        self._audit_store.append(UnifiedAuditRecord(record_id=f'cooldown_{event_type}_{int(time.time() * 1000)}', timestamp=time.time(), layer='execution', round=0, event_type=f'cooldown_{event_type}', source_module='CooldownManager', target_module=entry.agent_id if entry else 'unknown', decision=event_type.upper(), justification=justification))

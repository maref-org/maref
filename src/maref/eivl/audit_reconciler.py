"""Cross-replica audit reconciliation.

Compares audit logs from multiple replicas to detect inconsistencies
such as missing entries, divergent chain hashes, or tampered records.

Entries are compared by position in the chain (not by random entry ID)
and by content fingerprint: event_type + actor + action + details + timestamp.

Usage::

    reconciler = AuditReconciler()
    reconciler.add_replica("node-1", "/path/to/audit.jsonl")
    reconciler.add_replica("node-2", "/path/to/other.jsonl")
    report = reconciler.reconcile()
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.governance.audit import AuditEntry


def _content_fingerprint(entry: AuditEntry) -> str:
    """Deterministic fingerprint excluding random ID and mutable fields."""
    raw = f"{entry.event_type}|{entry.actor}|{entry.action}|{entry.details}"
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class ReconciliationReport:
    discrepancies: list[dict[str, Any]] = field(default_factory=list)
    replica_summary: dict[str, dict[str, Any]] = field(default_factory=dict)
    total_replicas: int = 0
    total_entries: dict[str, int] = field(default_factory=dict)
    is_consistent: bool = True
    reconciled_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_consistent": self.is_consistent,
            "total_replicas": self.total_replicas,
            "total_entries": self.total_entries,
            "discrepancies": self.discrepancies,
            "replica_summary": self.replica_summary,
            "reconciled_at": self.reconciled_at,
        }


@dataclass
class MerkleSnapshot:
    root_hash: str
    tree_size: int
    timestamp: float


class AuditReconciler:
    """Compare audit logs across replicas for consistency."""

    def __init__(self) -> None:
        self._replicas: dict[str, Path] = {}
        self._entries: dict[str, list[AuditEntry]] = {}
        self._merkle_snapshots: dict[str, MerkleSnapshot] = {}

    @staticmethod
    def _read_log_file(path: Path) -> list[AuditEntry]:
        entries: list[AuditEntry] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(AuditEntry(**data))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        return entries

    def add_replica(
        self,
        replica_id: str,
        log_path: str | Path,
    ) -> None:
        self._replicas[replica_id] = Path(log_path)
        if not self._replicas[replica_id].exists():
            raise FileNotFoundError(f"Audit log not found: {log_path}")
        self._entries[replica_id] = self._read_log_file(self._replicas[replica_id])

    def add_merkle_snapshot(
        self,
        replica_id: str,
        root_hash: str,
        tree_size: int,
    ) -> None:
        self._merkle_snapshots[replica_id] = MerkleSnapshot(
            root_hash=root_hash,
            tree_size=tree_size,
            timestamp=time.time(),
        )

    def reconcile(self) -> ReconciliationReport:
        report = ReconciliationReport()
        report.total_replicas = len(self._replicas)
        report.reconciled_at = time.time()

        replica_ids = list(self._replicas.keys())

        for rid in replica_ids:
            entries = self._entries.get(rid, [])
            report.total_entries[rid] = len(entries)

            fprints = [_content_fingerprint(e) for e in entries]
            report.replica_summary[rid] = {
                "entry_count": len(entries),
                "content_fingerprints": fprints,
            }

        if len(replica_ids) < 2:
            report.is_consistent = True
            return report

        for i in range(len(replica_ids)):
            for j in range(i + 1, len(replica_ids)):
                a_id = replica_ids[i]
                b_id = replica_ids[j]
                self._compare_replicas(a_id, b_id, report)

        critical = [d for d in report.discrepancies if d.get("severity") != "info"]
        report.is_consistent = len(critical) == 0
        return report

    def _compare_replicas(
        self,
        a_id: str,
        b_id: str,
        report: ReconciliationReport,
    ) -> None:
        a_entries = self._entries.get(a_id, [])
        b_entries = self._entries.get(b_id, [])

        min_len = min(len(a_entries), len(b_entries))

        # Compare by position
        for pos in range(min_len):
            a_ent = a_entries[pos]
            b_ent = b_entries[pos]

            # Content comparison via fingerprint
            if _content_fingerprint(a_ent) != _content_fingerprint(b_ent):
                report.discrepancies.append(
                    {
                        "type": "content_mismatch",
                        "position": pos,
                        "replica_a": a_id,
                        "replica_b": b_id,
                        "event_type_a": a_ent.event_type,
                        "event_type_b": b_ent.event_type,
                        "actor_a": a_ent.actor,
                        "actor_b": b_ent.actor,
                        "action_a": a_ent.action,
                        "action_b": b_ent.action,
                        "details": f"Content differs at position {pos} between {a_id} and {b_id}",
                    }
                )

            # Chain hash continuity
            if a_ent.chain_hash != b_ent.chain_hash and _content_fingerprint(
                a_ent
            ) == _content_fingerprint(b_ent):
                report.discrepancies.append(
                    {
                        "type": "chain_hash_mismatch",
                        "severity": "info",
                        "position": pos,
                        "entry_id": a_ent.id,
                        "replica_a": a_id,
                        "replica_b": b_id,
                        "chain_hash_a": a_ent.chain_hash,
                        "chain_hash_b": b_ent.chain_hash,
                    }
                )

            # Signature mismatch (same content, different sig = different key)
            sig_a = a_ent.hmac_signature or a_ent.ed25519_signature or ""
            sig_b = b_ent.hmac_signature or b_ent.ed25519_signature or ""
            if (
                sig_a
                and sig_b
                and sig_a != sig_b
                and _content_fingerprint(a_ent) == _content_fingerprint(b_ent)
            ):
                report.discrepancies.append(
                    {
                        "type": "signature_mismatch",
                        "severity": "info",
                        "position": pos,
                        "entry_id": a_ent.id,
                        "replica_a": a_id,
                        "replica_b": b_id,
                    }
                )

        # Length mismatch
        if len(a_entries) != len(b_entries):
            longer_id = a_id if len(a_entries) > len(b_entries) else b_id
            shorter_id = b_id if len(a_entries) > len(b_entries) else a_id
            diff = abs(len(a_entries) - len(b_entries))
            report.discrepancies.append(
                {
                    "type": "entry_count_mismatch",
                    "replica_a": a_id,
                    "replica_b": b_id,
                    "count_a": len(a_entries),
                    "count_b": len(b_entries),
                    "details": f"{longer_id} has {diff} more entries than {shorter_id}",
                }
            )

        # Merkle snapshot comparison
        if a_id in self._merkle_snapshots and b_id in self._merkle_snapshots:
            ms_a = self._merkle_snapshots[a_id]
            ms_b = self._merkle_snapshots[b_id]
            if ms_a.root_hash != ms_b.root_hash:
                report.discrepancies.append(
                    {
                        "type": "merkle_root_hash_mismatch",
                        "replica_a": a_id,
                        "replica_b": b_id,
                        "root_hash_a": ms_a.root_hash,
                        "root_hash_b": ms_b.root_hash,
                    }
                )
            if ms_a.tree_size != ms_b.tree_size:
                report.discrepancies.append(
                    {
                        "type": "merkle_tree_size_mismatch",
                        "replica_a": a_id,
                        "replica_b": b_id,
                        "tree_size_a": ms_a.tree_size,
                        "tree_size_b": ms_b.tree_size,
                    }
                )

    def print_report(self, report: ReconciliationReport) -> None:
        print(f"\n{'=' * 60}")
        print("  Audit Reconciliation Report")
        print(f"{'=' * 60}")
        print(f"  Replicas: {report.total_replicas}")
        for rid, count in report.total_entries.items():
            print(f"    {rid}: {count} entries")
        print(f"  Consistent: {'✅ Yes' if report.is_consistent else '❌ No'}")
        if report.discrepancies:
            info_count = sum(1 for d in report.discrepancies if d.get("severity") == "info")
            crit_count = len(report.discrepancies) - info_count
            print(
                f"  Discrepancies: {len(report.discrepancies)} "
                f"(critical={crit_count}, info={info_count})"
            )
            for d in report.discrepancies:
                pos = d.get("position", "")
                eid = d.get("entry_id", "")
                dtype = d["type"]
                sev = d.get("severity", "critical")
                detail = d.get("details", "")
                tag = "⚠" if sev == "info" else "❌"
                print(f"    {tag} [{sev}/{dtype}] pos={pos} id={eid}: {detail}")
        print(f"{'=' * 60}\n")


__all__ = [
    "AuditReconciler",
    "ReconciliationReport",
    "MerkleSnapshot",
]

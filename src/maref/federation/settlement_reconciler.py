"""Cross-server settlement reconciliation (Phase 3.2).

Compares the settlement ledgers of two independent servers to detect
inconsistencies — missing entries, diverged amounts, or tampered Merkle
roots — and arbitrates conflicts against the authoritative metering
source.

Entries are matched by :func:`~maref.federation.settlement.billing_charge_key`
(``provider|consumer|task_id``), the shared execution identity both
servers agree on.  Content is compared via
:func:`~maref.federation.settlement.billing_fingerprint`, which excludes
server-local fields so identical charges hash equal.  This makes the
Merkle root computed by each server directly comparable.

Usage::

    reconciler = SettlementReconciler()
    report = reconciler.reconcile(snapshot_a, snapshot_b)
    if not report.is_consistent:
        reconciler.arbitrate(report, authoritative_snapshot_a)
    assert report.arbitration["verdict"] in ("resolved", "unresolved")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

_CRITICAL = "critical"
_ENTRY_LEVEL_TYPES = ("missing_entry", "amount_mismatch")


@dataclass
class SettlementReconciliationReport:
    """Outcome of comparing two servers' settlement ledgers.

    ``is_consistent`` reflects the raw comparison (no discrepancies of
    critical severity).  After :meth:`SettlementReconciler.arbitrate`,
    ``arbitration`` carries per-discrepancy verdicts and corrections.
    """

    is_consistent: bool = True
    server_a: str = ""
    server_b: str = ""
    root_hash_a: str | None = None
    root_hash_b: str | None = None
    tree_size_a: int = 0
    tree_size_b: int = 0
    discrepancies: list[dict[str, Any]] = field(default_factory=list)
    arbitration: dict[str, Any] = field(default_factory=dict)
    reconciled_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_consistent": self.is_consistent,
            "server_a": self.server_a,
            "server_b": self.server_b,
            "root_hash_a": self.root_hash_a,
            "root_hash_b": self.root_hash_b,
            "tree_size_a": self.tree_size_a,
            "tree_size_b": self.tree_size_b,
            "discrepancies": self.discrepancies,
            "arbitration": self.arbitration,
            "reconciled_at": self.reconciled_at,
        }


class SettlementReconciler:
    """Compare and arbitrate settlement ledgers across servers."""

    def reconcile(
        self,
        snapshot_a: dict[str, Any],
        snapshot_b: dict[str, Any],
    ) -> SettlementReconciliationReport:
        """Compare two ledger snapshots and report discrepancies.

        Snapshots have the shape produced by
        :meth:`~maref.federation.settlement.FederatedSettlement.ledger_snapshot`
        plus an optional ``server_id`` label.
        """
        entries_a = {e["charge_key"]: e for e in snapshot_a.get("entries", [])}
        entries_b = {e["charge_key"]: e for e in snapshot_b.get("entries", [])}

        report = SettlementReconciliationReport(
            server_a=snapshot_a.get("server_id", ""),
            server_b=snapshot_b.get("server_id", ""),
            root_hash_a=snapshot_a.get("root_hash"),
            root_hash_b=snapshot_b.get("root_hash"),
            tree_size_a=snapshot_a.get("tree_size", 0),
            tree_size_b=snapshot_b.get("tree_size", 0),
        )

        if report.root_hash_a != report.root_hash_b:
            report.discrepancies.append(
                {
                    "type": "root_hash_mismatch",
                    "severity": _CRITICAL,
                    "details": "settlement Merkle roots differ between the two servers",
                }
            )

        if report.tree_size_a != report.tree_size_b:
            report.discrepancies.append(
                {
                    "type": "tree_size_mismatch",
                    "severity": _CRITICAL,
                    "details": (
                        f"ledger sizes differ ({report.tree_size_a} vs {report.tree_size_b})"
                    ),
                }
            )

        for key in sorted(set(entries_a) | set(entries_b)):
            if key not in entries_a:
                report.discrepancies.append(
                    {
                        "type": "missing_entry",
                        "severity": _CRITICAL,
                        "charge_key": key,
                        "present_side": "b",
                        "details": (
                            f"entry {key} present on {report.server_b or 'b'} "
                            f"but missing on {report.server_a or 'a'}"
                        ),
                    }
                )
            elif key not in entries_b:
                report.discrepancies.append(
                    {
                        "type": "missing_entry",
                        "severity": _CRITICAL,
                        "charge_key": key,
                        "present_side": "a",
                        "details": (
                            f"entry {key} present on {report.server_a or 'a'} "
                            f"but missing on {report.server_b or 'b'}"
                        ),
                    }
                )
            else:
                entry_a = entries_a[key]
                entry_b = entries_b[key]
                if entry_a["fingerprint"] != entry_b["fingerprint"]:
                    report.discrepancies.append(
                        {
                            "type": "amount_mismatch",
                            "severity": _CRITICAL,
                            "charge_key": key,
                            "fingerprint_a": entry_a["fingerprint"],
                            "fingerprint_b": entry_b["fingerprint"],
                            "amount_a": entry_a.get("amount"),
                            "amount_b": entry_b.get("amount"),
                            "details": (
                                f"entry {key} charges differ: "
                                f"{report.server_a or 'a'}={entry_a.get('amount')}, "
                                f"{report.server_b or 'b'}={entry_b.get('amount')}"
                            ),
                        }
                    )

        report.is_consistent = not any(d.get("severity") == _CRITICAL for d in report.discrepancies)
        return report

    def arbitrate(
        self,
        report: SettlementReconciliationReport,
        authoritative_snapshot: dict[str, Any],
    ) -> SettlementReconciliationReport:
        """Resolve each discrepancy against the authoritative source.

        ``authoritative_snapshot`` is typically produced by
        :meth:`~maref.federation.settlement.FederatedSettlement.authoritative_snapshot`
        — a ledger recomputed straight from the metering engine.  For
        every entry-level discrepancy the arbitrator decides which side
        matches the source of truth and what correction is required.

        Mutates and returns ``report``.
        """
        authoritative = {e["charge_key"]: e for e in authoritative_snapshot.get("entries", [])}
        resolutions: list[dict[str, Any]] = []

        for d in report.discrepancies:
            d_type = d["type"]
            key = d.get("charge_key")
            if d_type not in _ENTRY_LEVEL_TYPES or key is None:
                resolutions.append(
                    {
                        "discrepancy_type": d_type,
                        "resolved": False,
                        "verdict": "consequence_of_entry_conflicts"
                        if d_type in ("root_hash_mismatch", "tree_size_mismatch")
                        else "not_arbitrable",
                    }
                )
                continue

            auth_entry = authoritative.get(key)
            if d_type == "missing_entry":
                if auth_entry is None:
                    resolutions.append(
                        {
                            "charge_key": key,
                            "discrepancy_type": d_type,
                            "resolved": True,
                            "verdict": "entry_spurious",
                            "correction": f"remove from {d['present_side']}",
                        }
                    )
                else:
                    missing_side = "b" if d["present_side"] == "a" else "a"
                    resolutions.append(
                        {
                            "charge_key": key,
                            "discrepancy_type": d_type,
                            "resolved": True,
                            "verdict": "entry_valid",
                            "correction": f"add to {missing_side}",
                        }
                    )
            else:  # amount_mismatch
                if auth_entry is None:
                    resolutions.append(
                        {
                            "charge_key": key,
                            "discrepancy_type": d_type,
                            "resolved": True,
                            "verdict": "no_authoritative_record",
                            "correction": "recompute both sides from metering",
                        }
                    )
                else:
                    auth_fp = auth_entry["fingerprint"]
                    if auth_fp == d.get("fingerprint_a"):
                        resolutions.append(
                            {
                                "charge_key": key,
                                "discrepancy_type": d_type,
                                "resolved": True,
                                "verdict": "a_matches_authoritative",
                                "correction": (
                                    f"{report.server_b or 'b'} must adopt amount "
                                    f"{d.get('amount_a')}"
                                ),
                            }
                        )
                    elif auth_fp == d.get("fingerprint_b"):
                        resolutions.append(
                            {
                                "charge_key": key,
                                "discrepancy_type": d_type,
                                "resolved": True,
                                "verdict": "b_matches_authoritative",
                                "correction": (
                                    f"{report.server_a or 'a'} must adopt amount "
                                    f"{d.get('amount_b')}"
                                ),
                            }
                        )
                    else:
                        resolutions.append(
                            {
                                "charge_key": key,
                                "discrepancy_type": d_type,
                                "resolved": True,
                                "verdict": "neither_matches",
                                "correction": (
                                    f"both must adopt authoritative amount "
                                    f"{auth_entry.get('amount')}"
                                ),
                            }
                        )

        entry_resolutions = [r for r in resolutions if r["discrepancy_type"] in _ENTRY_LEVEL_TYPES]
        all_resolved = len(entry_resolutions) > 0 and all(r["resolved"] for r in entry_resolutions)
        if report.is_consistent:
            verdict = "consistent"
        elif all_resolved:
            verdict = "resolved"
        else:
            verdict = "unresolved"

        report.arbitration = {
            "arbitrated": True,
            "arbitrated_at": time.time(),
            "resolutions": resolutions,
            "entry_conflicts": len(entry_resolutions),
            "all_resolved": all_resolved,
            "verdict": verdict,
        }
        return report


__all__ = [
    "SettlementReconciler",
    "SettlementReconciliationReport",
]

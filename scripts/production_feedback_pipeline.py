#!/usr/bin/env python3
"""
Production Audit → Convergence Dashboard + MetaLearner Feedback Pipeline

Transforms production governance audit logs (JSONL) into:

  1. convergence_history.jsonl  ← ConvergenceDashboard.load_history()
  2. MetaLearner DecisionOutcome records  ← ExperienceStore (SQLite)

Usage:
  python scripts/production_feedback_pipeline.py                  # defaults
  python scripts/production_feedback_pipeline.py --audit /path/to/audit.jsonl --cb /path/to/cb.jsonl --output /path/to/output.jsonl
  python scripts/production_feedback_pipeline.py --meta-db /path/to/experience.db
  python scripts/production_feedback_pipeline.py --report         # print convergence report
  python scripts/production_feedback_pipeline.py --plot           # ASCII terminal plot
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Reproduce ConvergenceSnapshot here so the pipeline has zero runtime
# dependencies on the MAREF package.
# ---------------------------------------------------------------------------

@dataclass
class ConvergenceSnapshot:
    round_num: int
    cycle_id: str
    fnr: float
    fpr: float
    kl_drift: float
    perf_score: float
    gain_pct: float
    saturated: bool
    timestamp: float = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round_num,
            "cycle_id": self.cycle_id,
            "fnr": self.fnr,
            "fpr": self.fpr,
            "kl_drift": self.kl_drift,
            "perf_score": self.perf_score,
            "gain_pct": self.gain_pct,
            "saturated": self.saturated,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# DecisionOutcome-compatible record for MetaLearner
# ---------------------------------------------------------------------------

@dataclass
class DecisionRecord:
    timestamp: float
    decision_type: str
    state_before: str
    state_after: str
    entropy_before: int
    entropy_after: int
    reward: float
    context: dict[str, Any]
    role_id: str | None

    def to_tuple(self) -> tuple:
        return (
            self.timestamp, self.decision_type, self.state_before,
            self.state_after, self.entropy_before, self.entropy_after,
            self.reward, json.dumps(self.context), self.role_id,
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class AuditFeedbackPipeline:
    def __init__(
        self,
        audit_path: str = ".worktrees/roi-governance/governance_audit_20260518_113148.jsonl",
        cb_path: str = "recursive_governance_audit.jsonl",
        output_path: str = "data/convergence_history.jsonl",
        meta_db_path: str | None = None,
        window_hours: int = 12,
    ):
        self.audit_path = Path(audit_path)
        self.cb_path = Path(cb_path)
        self.output_path = Path(output_path)
        self.meta_db_path = Path(meta_db_path) if meta_db_path else None
        self.window_hours = window_hours

    def run(self) -> list[ConvergenceSnapshot]:
        if not self.audit_path.exists():
            print(f"[WARN] Audit log not found: {self.audit_path}", file=sys.stderr)
            return []
        if not self.cb_path.exists():
            print(f"[WARN] Circuit-breaker log not found: {self.cb_path}", file=sys.stderr)
            return []

        governance_events = self._load_jsonl(self.audit_path)
        cb_events = self._load_jsonl(self.cb_path)

        print(f"Loaded {len(governance_events)} governance events, {len(cb_events)} circuit-breaker events")

        snapshots = self._build_snapshots(governance_events, cb_events)
        self._write_convergence(snapshots)

        if self.meta_db_path:
            decisions = self._build_decisions(snapshots, governance_events, cb_events)
            self._write_experience_db(decisions)

        print(f"Wrote {len(snapshots)} convergence snapshots to {self.output_path}")
        return snapshots

    @staticmethod
    def _load_jsonl(path: Path) -> list[dict[str, Any]]:
        events = []
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return events

    def _build_snapshots(
        self,
        governance_events: list[dict[str, Any]],
        cb_events: list[dict[str, Any]],
    ) -> list[ConvergenceSnapshot]:
        timestamps = [e["timestamp"] for e in governance_events if "timestamp" in e]
        if not timestamps:
            return []

        window = self.window_hours * 3600
        cursor = min(timestamps)
        end = max(timestamps)

        snapshots = []
        round_num = 0
        prev_ad_ratio: float | None = None

        while cursor < end:
            w_end = cursor + window
            w_e = [e for e in governance_events if cursor <= e.get("timestamp", 0) < w_end]
            w_c = [e for e in cb_events if cursor <= e.get("timestamp", 0) < w_end]

            if not w_e and not w_c:
                cursor = w_end
                continue

            round_num += 1

            decisions = len([e for e in w_e if e.get("event_type") == "governance_decision"])
            anomalies = len([e for e in w_e if e.get("event_type") == "anomaly_detected"])
            depth3 = len([e for e in w_c if e.get("details") == "depth=3"])
            total_cb = len(w_c)
            force_stab = len([e for e in w_e if e.get("action") == "force_stabilize"])

            fnr = depth3 / max(total_cb, 1)
            fpr = depth3 / max(anomalies, 1)
            ad_ratio = anomalies / max(decisions, 1)

            if prev_ad_ratio is not None:
                kl = min(abs(ad_ratio - prev_ad_ratio) / max(prev_ad_ratio, 0.001), 1.0)
            else:
                kl = 0.0
            prev_ad_ratio = ad_ratio

            perf = max(0.0, 1.0 - (
                0.4 * fnr + 0.3 * min(depth3 / 10, 1) + 0.2 * min(force_stab / 100, 1) + 0.1 * kl
            ))

            snapshots.append(ConvergenceSnapshot(
                round_num=round_num,
                cycle_id="c2",
                fnr=round(fnr, 4),
                fpr=round(fpr, 4),
                kl_drift=round(kl, 4),
                perf_score=round(perf, 4),
                gain_pct=round((1 - fnr) * 100, 2),
                saturated=total_cb < 3 and decisions < 10,
            ))

            cursor = w_end

        return snapshots

    def _write_convergence(self, snapshots: list[ConvergenceSnapshot]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            for snap in snapshots:
                f.write(json.dumps(snap.to_dict()) + "\n")

    # -----------------------------------------------------------------------
    # MetaLearner ExperienceStore bridge
    # -----------------------------------------------------------------------

    def _build_decisions(
        self,
        snapshots: list[ConvergenceSnapshot],
        governance_events: list[dict[str, Any]],
        cb_events: list[dict[str, Any]],
    ) -> list[DecisionRecord]:
        records: list[DecisionRecord] = []

        for snap in snapshots:
            reward = 1.0 - (snap.fnr * 2.0)

            records.append(DecisionRecord(
                timestamp=snap.timestamp,
                decision_type="production_audit_window",
                state_before="ANALYZE",
                state_after="STABILIZE" if snap.fnr < 0.3 else "REACT",
                entropy_before=2,
                entropy_after=1,
                reward=reward,
                context={"fnr": snap.fnr, "fpr": snap.fpr, "kl_drift": snap.kl_drift},
                role_id="production_pipeline",
            ))

        # Also extract anomaly events as negative-reward decisions.
        # Production data: all 663,165 anomalies have action=="handle_anomaly";
        # severity=="critical" → strong negative reward
        for ev in governance_events:
            if ev.get("event_type") != "anomaly_detected":
                continue
            meta = ev.get("metadata", {})
            severity = meta.get("severity", "low") if isinstance(meta, dict) else "low"
            reward = -0.8 if severity == "critical" else (-0.3 if severity == "high" else -0.1)

            records.append(DecisionRecord(
                timestamp=ev.get("timestamp", time.time()),
                decision_type="anomaly_handled",
                state_before="MONITOR",
                state_after="PROTECT",
                entropy_before=3,
                entropy_after=2,
                reward=reward,
                context={
                    "anomaly": ev.get("details", ""),
                    "source": ev.get("actor", ""),
                    "severity": severity,
                },
                role_id="production_pipeline",
            ))

        return records

    def _write_experience_db(self, decisions: list[DecisionRecord]) -> None:
        self.meta_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.meta_db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS experience (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                decision_type TEXT,
                state_before TEXT,
                state_after TEXT,
                entropy_before INTEGER,
                entropy_after INTEGER,
                reward REAL,
                context TEXT,
                role_id TEXT
            )
        """)
        count = 0
        for rec in decisions:
            try:
                conn.execute(
                    "INSERT INTO experience (timestamp, decision_type, state_before, state_after, "
                    "entropy_before, entropy_after, reward, context, role_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rec.to_tuple(),
                )
                count += 1
            except sqlite3.IntegrityError:
                continue
        conn.commit()
        conn.close()
        print(f"Wrote {count} decision records to MetaLearner DB: {self.meta_db_path}")


# ---------------------------------------------------------------------------
# Terminal usage
# ---------------------------------------------------------------------------

def print_report(snapshots: list[ConvergenceSnapshot]) -> None:
    if not snapshots:
        print("No data.")
        return
    print(f"Convergence Report — {len(snapshots)} snapshots")
    print(f"  Perf trajectory: {snapshots[0].perf_score:.3f} -> ... -> {snapshots[-1].perf_score:.3f}")
    print(f"  FNR trajectory:  {snapshots[0].fnr:.3f} -> ... -> {snapshots[-1].fnr:.3f}")

    non_sat = [s for s in snapshots if not s.saturated]
    if non_sat:
        print(f"  Best perf:       {max(s.perf_score for s in non_sat):.3f} (round {max(non_sat, key=lambda x: x.perf_score).round_num})")
        print(f"  Worst FNR:       {max(s.fnr for s in non_sat):.3f} (round {max(non_sat, key=lambda x: x.fnr).round_num})")

    print(f"  Windows saturated: {sum(1 for s in snapshots if s.saturated)} / {len(snapshots)}")

    by_cycle: dict[str, list[ConvergenceSnapshot]] = defaultdict(list)
    for s in snapshots:
        by_cycle[s.cycle_id].append(s)
    for cid, snaps in sorted(by_cycle.items()):
        final = snaps[-1]
        print(f"  Cycle {cid}: FNR={final.fnr:.3f} FPR={final.fpr:.3f} Perf={final.perf_score:.3f}")


def print_plot(snapshots: list[ConvergenceSnapshot]) -> None:
    if not snapshots:
        print("No data.")
        return

    by_cycle: dict[str, list[ConvergenceSnapshot]] = defaultdict(list)
    for s in snapshots:
        by_cycle[s.cycle_id].append(s)

    print("=" * 68)
    print("  MAREF Production Feedback — Convergence Plot")
    print("=" * 68)

    for cid, snaps in sorted(by_cycle.items()):
        snaps.sort(key=lambda s: s.round_num)
        print(f"\n  -- {cid} --")
        for label, attr, char in [("FNR", "fnr", "F"), ("FPR", "fpr", "P"),
                                   ("KL ", "kl_drift", "K"), ("Perf", "perf_score", "S"),
                                   ("Gain", "gain_pct", "G")]:
            values = [getattr(s, attr) for s in snaps]
            if len(values) < 2:
                continue
            lo, hi = min(values), max(values)
            rng = hi - lo if hi != lo else 1.0
            last = values[-1]
            trend = "\u2197" if len(values) >= 2 and values[-1] > values[-2] else \
                    ("\u2198" if len(values) >= 2 and values[-1] < values[-2] else "\u2192")
            n = (last - lo) / rng
            bar = "|" * int(n * 40) + "." * (40 - int(n * 40))
            print(f"  {char} [{trend}] {bar} {last:.4f}")

    print(f"\n  Total snapshots: {len(snapshots)}")
    print("=" * 68)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="MAREF Production Feedback Pipeline")
    parser.add_argument("--audit", default=".worktrees/roi-governance/governance_audit_20260518_113148.jsonl",
                        help="Path to governance audit JSONL")
    parser.add_argument("--cb", default="recursive_governance_audit.jsonl",
                        help="Path to circuit-breaker JSONL")
    parser.add_argument("--output", default="data/convergence_history.jsonl",
                        help="Output path for convergence_history.jsonl")
    parser.add_argument("--meta-db", default=None,
                        help="Output path for MetaLearner experience SQLite DB")
    parser.add_argument("--window-hours", type=float, default=12.0,
                        help="Width of time window in hours (default: 12)")
    parser.add_argument("--report", action="store_true",
                        help="Print convergence report after writing")
    parser.add_argument("--plot", action="store_true",
                        help="Print ASCII terminal plot after writing")

    args = parser.parse_args()

    pipeline = AuditFeedbackPipeline(
        audit_path=args.audit,
        cb_path=args.cb,
        output_path=args.output,
        meta_db_path=args.meta_db,
        window_hours=args.window_hours,
    )

    snapshots = pipeline.run()

    if args.report:
        print()
        print_report(snapshots)

    if args.plot:
        print()
        print_plot(snapshots)


if __name__ == "__main__":
    main()

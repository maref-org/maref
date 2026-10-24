#!/usr/bin/env python3
"""Attribute and close archived alert notifications with an evidence trail.

Archived notification files are immutable history. This script does not delete
them. It writes one closure record per archived alert (reason + evidence +
SHA256), and optionally closes matching open alerts in the live
AlertFeedbackTracker.

Default is dry-run.

Usage:
    python3 scripts/triage_archived_alerts.py
    python3 scripts/triage_archived_alerts.py --apply
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_DEFAULT_ARCHIVES = [
    _REPO_ROOT / ".openclaw" / "notifications_archive",
    _REPO_ROOT / ".governance" / "meta" / "notifications" / "archive",
    _REPO_ROOT / ".governance" / "notifications_archive",
]


def _read_json(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
            return json.load(fh)
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_manifest() -> Path | None:
    candidates = sorted(
        (_REPO_ROOT / ".governance" / "audit" / "archive").glob("rebaseline_manifest_*.json")
    )
    return candidates[-1] if candidates else None


def _classify(check_id: str, title: str, manifest: Path | None) -> tuple[str, str, str]:
    if check_id == "audit_chain_integrity":
        evidence = str(manifest) if manifest else "rebaseline manifest not found"
        return (
            "historical_audit_chain_fork",
            "pre-rebaseline audit chain fork alert; chain archived and re-baselined",
            evidence,
        )
    if check_id == "":
        return (
            "legacy_pre_check_id",
            "legacy alert archived before alert check_id tracking existed",
            "check_id absent in archived payload",
        )
    if check_id == "notification_staleness":
        return (
            "historical_feedback_loop",
            "historical M2 feedback-loop staleness alert",
            "archived notification; superseded by current M2 tracker",
        )
    return (
        "archived_alert",
        f"archived notification ({title or 'untitled'}); no matching open tracker alert",
        "archived payload",
    )


def _iter_files(archive_dirs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for directory in archive_dirs:
        if not directory.exists():
            continue
        files.extend(sorted(p for p in directory.rglob("*") if p.is_file()))
    return files


def _load_ledger_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    keys: set[tuple[str, str]] = set()
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            keys.add((str(rec.get("archive_file", "")), str(rec.get("sha256", ""))))
    except OSError:
        pass
    return keys


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage archived alert notifications")
    parser.add_argument(
        "--archive-dir",
        action="append",
        default=[],
        help="Archive directory (repeatable; defaults to known legacy paths)",
    )
    parser.add_argument(
        "--ledger",
        default=str(_REPO_ROOT / ".governance" / "meta" / "archive_closure_ledger.jsonl"),
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--report",
        default="",
        help="Optional JSON summary path (e.g. reports/alert_triage_20261019.json)",
    )
    parser.add_argument(
        "--no-close-open",
        action="store_true",
        help="Only write the ledger; do not close matching open tracker alerts",
    )
    args = parser.parse_args()

    archive_dirs = [Path(p) for p in args.archive_dir] if args.archive_dir else _DEFAULT_ARCHIVES
    files = _iter_files(archive_dirs)
    if not files:
        print("No archived notifications found.")
        return 0

    ledger_path = Path(args.ledger)
    seen = _load_ledger_keys(ledger_path)
    manifest = _find_manifest()

    groups: Counter[str] = Counter()
    by_check: dict[str, list[Path]] = defaultdict(list)
    archive_titles: list[tuple[str, float | None]] = []
    records: list[dict] = []
    skipped = 0

    for path in files:
        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        check_id = str(payload.get("check_id", ""))
        title = str(payload.get("title", ""))
        subsystem = str(payload.get("subsystem", ""))
        timestamp = payload.get("timestamp")
        digest = _sha256(path)
        groups[check_id or "<none>"] += 1
        by_check[check_id].append(path)
        archive_titles.append((title, timestamp if isinstance(timestamp, (int, float)) else None))

        if (str(path), digest) in seen:
            skipped += 1
            continue

        classification, reason, evidence = _classify(check_id, title, manifest)
        records.append(
            {
                "closed_at": time.time(),
                "closed_by": os.environ.get("USER", "unknown"),
                "archive_file": str(path),
                "sha256": digest,
                "check_id": check_id,
                "title": title,
                "subsystem": subsystem,
                "alert_timestamp": timestamp,
                "classification": classification,
                "reason": reason,
                "evidence": evidence,
            }
        )

    summary = {
        "generated_at": time.time(),
        "archive_files": len(files),
        "new_closures": len(records),
        "already_filed": skipped,
        "by_check_id": dict(groups),
        "by_classification": dict(Counter(r["classification"] for r in records)),
        "by_subsystem": dict(Counter(r["subsystem"] for r in records)),
        "ledger": str(ledger_path),
        "manifest": str(manifest) if manifest else None,
    }
    print(f"archive files : {len(files)}")
    print(f"new closures  : {len(records)}")
    print(f"already filed : {skipped}")
    print("by check_id   :")
    for check_id, count in groups.most_common():
        print(f"  {check_id}: {count}")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"report written: {report_path}")

    if not args.apply:
        print("Dry-run: pass --apply to write the ledger and close matching open alerts.")
        return 0

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"ledger appended: {ledger_path}")

    if not args.no_close_open:
        from maref.observability.alert_feedback_tracker import AlertFeedbackTracker

        tracker = AlertFeedbackTracker()
        closed = 0
        for record in tracker.get_open_alerts():
            check_id = record.check_id
            if check_id in by_check and by_check[check_id]:
                evidence = str(manifest) if manifest else "archive closure ledger"
                reason = (
                    "archived alert attributed and closed; see archive_closure_ledger.jsonl"
                )
                if tracker.close_alert(
                    record.alert_id,
                    reason=reason,
                    evidence=evidence,
                    description=reason,
                ):
                    closed += 1
            elif check_id == "":
                # Only close legacy alerts that actually correspond to an
                # archived notification; an unrelated live alert (e.g. M4
                # telemetry) must stay open.
                matches_archive = any(
                    title == record.name
                    and (
                        record.triggered_at is None
                        or ts is None
                        or abs(float(ts) - record.triggered_at) <= 3600
                    )
                    for title, ts in archive_titles
                )
                if matches_archive:
                    reason = "legacy alert without check_id; attributed to archive closure"
                    if tracker.close_alert(
                        record.alert_id,
                        reason=reason,
                        evidence="archive_closure_ledger.jsonl",
                        description=reason,
                    ):
                        closed += 1
        print(f"open alerts closed: {closed}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

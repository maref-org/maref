"""Export labeled episodes as a de-identified attestation corpus."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .normalize import sha16
from .redact import find_leaks

SCHEMA_VERSION = "attestation_v1"


def _payload(row: sqlite3.Row) -> dict[str, Any]:
    fix_ref = str(row["fix_ref"] or "")
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime": row["runtime"],
        "agent_id_hash": sha16(str(row["agent_id"] or "")),
        "model_family": str(row["model"] or "").split("/")[0],
        "task_class": row["task_class"],
        "failure_sig": row["failure_sig"],
        "error_class": row["error_class"],
        "tool": row["tool"],
        "evidence_hashes": [sha16(str(row["failure_event_id"]))],
        "snippet": row["snippet"] or "",
        "repro": {"status": "none", "steps_hash": ""},
        "fix": {"type": row["fix_type"], "ref_hash": sha16(fix_ref) if fix_ref else ""},
        "versions": json.loads(row["versions_json"] or "{}"),
        "outcome": row["outcome"],
        "severity": row["severity"],
        "root_cause": row["root_cause"],
        "reusable": bool(row["reusable"]),
        "label_agreement": row["agree_with_llm"],
        "labeled_by": row["labeled_by"],
    }


def export_attestations(conn: sqlite3.Connection, out: Path) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT e.*, l.root_cause, l.fix_type, l.fix_ref, l.severity AS label_severity,
               l.reusable, l.labeled_by, l.agree_with_llm
        FROM episode e JOIN label l ON l.episode_id = e.id
        WHERE e.label_status = 'labeled'
        ORDER BY e.started_at
        """
    ).fetchall()
    lines: list[str] = []
    leaks: dict[str, int] = {}
    for row in rows:
        payload = _payload(row)
        if row["label_severity"]:
            payload["severity"] = row["label_severity"]
        line = json.dumps(payload, ensure_ascii=False)
        for rule in find_leaks(line):
            leaks[rule] = leaks.get(rule, 0) + 1
        lines.append(line)
    if leaks:
        raise ValueError(f"refusing to export: leaks detected {leaks}")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(out)
    return {"exported": len(lines), "path": str(out), "leaks": leaks}

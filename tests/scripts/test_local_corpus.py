"""Local corpus factory tests: redaction, adapters, linking, export."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.local_corpus import db  # noqa: E402
from scripts.local_corpus.adapters.claude_code import ClaudeCodeAdapter  # noqa: E402
from scripts.local_corpus.adapters.opencode import OpencodeAdapter  # noqa: E402
from scripts.local_corpus.cli import INSERT_EVENT  # noqa: E402
from scripts.local_corpus.export import export_attestations  # noqa: E402
from scripts.local_corpus.label import record_label  # noqa: E402
from scripts.local_corpus.link import link_episodes, relink_signatures  # noqa: E402
from scripts.local_corpus.redact import find_leaks, redact  # noqa: E402


def test_redact_secrets_and_paths() -> None:
    anthropic = "sk-" + "ant-" + "a" * 28
    github = "ghp" + "_" + "b" * 36
    text = f"key={anthropic} mail=a@b.com path=/home/tester/project token={github}"
    result = redact(text)
    assert result.count >= 3
    assert anthropic not in result.text
    assert "a@b.com" not in result.text
    assert "/home/tester" not in result.text
    assert find_leaks(result.text) == []


def test_redact_keeps_normal_text() -> None:
    text = "pytest tests/governance -q returned exit code 1"
    result = redact(text)
    assert result.text == text
    assert result.count == 0


def test_redact_keeps_paths() -> None:
    text = "see /data/reports/2026-10-21-report-v3-final.md"
    result = redact(text)
    assert result.text == text
    assert result.count == 0


def test_redact_high_entropy_token() -> None:
    token = "".join(["Ab3dE5gH7jK9", "mN1pQ3sT5vX7", "zA9cB1dF3"])
    result = redact(f"Authorization: {token}")
    assert token not in result.text
    assert "high_entropy" in result.rules


def _write_claude_log(path: Path) -> None:
    rows = [
        {
            "timestamp": 1000.0,
            "agent_id": "opencode",
            "tool_name": "bash",
            "verdict": "ALLOW",
            "reason": "Permission denied",
            "risk_score": 0.3,
            "project_root": "/tmp/proj",
            "args_hash": "abc",
            "hmac": "sig1",
        },
        {
            "timestamp": 1010.0,
            "agent_id": "opencode",
            "tool_name": "bash",
            "verdict": "ALLOW",
            "reason": "",
            "risk_score": 0.0,
            "project_root": "/tmp/proj",
            "args_hash": "abc",
            "hmac": "sig2",
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_claude_adapter_accepts_iso_timestamps(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    log.write_text(
        json.dumps(
            {
                "timestamp": "2026-10-10T06:31:52Z",
                "tool_name": "bash",
                "verdict": "DENY",
                "reason": "",
                "project_root": "/tmp/proj",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    events = list(ClaudeCodeAdapter(log).iter_events(0.0))
    assert len(events) == 1
    assert events[0].ts > 1_700_000_000


def test_claude_adapter_is_stable(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    _write_claude_log(log)
    adapter = ClaudeCodeAdapter(log)
    first = list(adapter.iter_events(0.0))
    second = list(adapter.iter_events(0.0))
    assert len(first) == 2
    assert [e.source_event_id for e in first] == [e.source_event_id for e in second]
    assert first[0].session_id == second[0].session_id
    assert first[0].error_class == "permission"
    assert first[0].snippet == "Permission denied"


def _make_opencode_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE session(id TEXT PRIMARY KEY, project_id TEXT, directory TEXT, title TEXT);
        CREATE TABLE message(id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part(
            id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
            time_created INTEGER, data TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO session VALUES('s1','p1','/tmp/proj','demo')",
    )
    message = {
        "role": "assistant",
        "time": {"created": 1000000},
        "agent": "build",
        "model": {"providerID": "prov", "modelID": "model-x"},
    }
    conn.execute("INSERT INTO message VALUES('m1','s1',1000000,?)", (json.dumps(message),))
    user_message = {"role": "user", "time": {"created": 1005000}}
    conn.execute("INSERT INTO message VALUES('m2','s1',1005000,?)", (json.dumps(user_message),))
    parts = [
        (
            "p1",
            {
                "type": "tool",
                "tool": "bash",
                "state": {"status": "error", "error": "Permission denied", "input": {"cmd": "rm"}},
            },
        ),
        ("p2", {"type": "text", "text": "还是报错，再试一次"}),
        (
            "p3",
            {
                "type": "tool",
                "tool": "bash",
                "state": {"status": "completed", "output": "ok", "input": {"cmd": "ls"}},
            },
        ),
        ("p4", {"type": "patch", "hash": "h1"}),
    ]
    for offset, (pid, payload) in enumerate(parts):
        message_id = "m2" if pid == "p2" else "m1"
        base = 1005000 if pid == "p2" else 1000000
        conn.execute(
            "INSERT INTO part VALUES(?,?,?,?,?)",
            (pid, message_id, "s1", base + offset * 10000, json.dumps(payload)),
        )
    conn.commit()
    conn.close()


def test_error_signature_ignores_exit_code_header() -> None:
    from scripts.local_corpus.normalize import error_signature

    a = error_signature("Exit code 1\nls: /root: Permission denied")
    b = error_signature("Exit code 1\nModuleNotFoundError: no module named x")
    assert a != b
    assert a == error_signature("Exit code 1\nls: /root: Permission denied")
    tb = 'Traceback (most recent call last):\n  File "x.py", line 1\nRuntimeError: boom'
    assert error_signature(tb) == error_signature("RuntimeError: boom")


def test_output_failure_is_conservative() -> None:
    from scripts.local_corpus.normalize import detect_output_failure

    assert detect_output_failure("no errors found, 3 files changed") == ""
    assert detect_output_failure("Exit code: 1") == "tool_error"
    assert detect_output_failure("2 failed, 10 passed") == "test_fail"
    assert detect_output_failure("Traceback (most recent call last):") == "exception"
    assert detect_output_failure("set timeout to 30s in config") == ""


def test_opencode_adapter(tmp_path: Path) -> None:
    path = tmp_path / "opencode.db"
    _make_opencode_db(path)
    events = list(OpencodeAdapter(path).iter_events(0.0))
    kinds = [e.kind for e in events]
    assert kinds == ["error", "tool_call", "edit", "message"]
    assert events[0].error_class == "permission"
    assert events[0].model == "prov/model-x"
    assert events[-1].error_class == "user_correction"


def _ingest(conn: sqlite3.Connection, event: object) -> None:
    conn.execute(INSERT_EVENT, event.as_row())  # type: ignore[attr-defined]


def test_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAREF_CORPUS_DIR", str(tmp_path / "corpus"))
    db.ensure_dirs()
    conn = db.connect()
    db.init_db(conn)

    claude_log = tmp_path / "audit.jsonl"
    _write_claude_log(claude_log)
    opencode_db = tmp_path / "opencode.db"
    _make_opencode_db(opencode_db)

    for event in ClaudeCodeAdapter(claude_log).iter_events(0.0):
        _ingest(conn, event)
    for event in OpencodeAdapter(opencode_db).iter_events(0.0):
        _ingest(conn, event)
    conn.commit()

    result = link_episodes(conn)
    relink_signatures(conn)
    assert result["created"] >= 2

    episode = conn.execute("SELECT * FROM episode ORDER BY started_at LIMIT 1").fetchone()
    assert episode is not None
    record_label(
        conn,
        str(episode["id"]),
        root_cause="environment",
        fix_type="retry",
        severity="high",
        reusable=True,
        notes="local note with a@b.com should never be exported",
    )

    out = tmp_path / "exports" / "attestation_v1.jsonl"
    exported = export_attestations(conn, out)
    assert exported["exported"] == 1
    line = out.read_text(encoding="utf-8")
    assert "a@b.com" not in line
    payload = json.loads(line)
    assert payload["schema_version"] == "attestation_v1"
    assert payload["severity"] == "high"
    assert payload["root_cause"] == "environment"
    assert payload["reusable"] is True
    conn.close()

    cross = conn_check_cross_runtime(tmp_path / "corpus" / "corpus.db")
    assert cross >= 1


def conn_check_cross_runtime(path: Path) -> int:
    conn = db.connect(path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM signature WHERE json_array_length(runtimes_json) >= 2"
        ).fetchone()
        return int(row["n"]) if row else 0
    finally:
        conn.close()


def test_claude_transcript_adapter(tmp_path: Path) -> None:
    from scripts.local_corpus.adapters.claude_transcript import ClaudeTranscriptAdapter

    root = tmp_path / "projects"
    proj = root / "-tmp-proj"
    proj.mkdir(parents=True)
    records = [
        {
            "type": "user",
            "uuid": "u1",
            "sessionId": "s1",
            "timestamp": "2026-10-01T10:00:00Z",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "还是报错，重新跑一次"}],
            },
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "sessionId": "s1",
            "timestamp": "2026-10-01T10:00:01Z",
            "message": {
                "role": "assistant",
                "model": "m1",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Bash",
                        "input": {"command": "ls /root"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "uuid": "u2",
            "sessionId": "s1",
            "timestamp": "2026-10-01T10:00:02Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "is_error": True,
                        "content": "ls: /root: Permission denied",
                    }
                ],
            },
        },
    ]
    (proj / "s1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    events = list(ClaudeTranscriptAdapter(root).iter_events(0.0))
    assert [e.kind for e in events] == ["message", "tool_call", "error"]
    assert events[0].error_class == "user_correction"
    assert events[2].tool == "Bash"
    assert events[2].error_class == "permission"
    assert "Permission denied" in events[2].snippet


def test_link_distinguishes_retry_from_fix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.local_corpus.normalize import Event

    monkeypatch.setenv("MAREF_CORPUS_DIR", str(tmp_path / "corpus"))
    db.ensure_dirs()
    conn = db.connect()
    db.init_db(conn)

    def ev(sid: str, ts: float, kind: str, tool: str, error: str = "") -> Event:
        return Event(
            source="opencode",
            source_event_id=f"{sid}:{ts}",
            session_id=sid,
            agent_id="a",
            model="m",
            ts=ts,
            kind=kind,
            tool=tool,
            error_class=error,
            error_sig=f"sig-{error}" if error else "",
            snippet=error,
        )

    for event in (
        ev("fixed", 100.0, "error", "bash", "permission"),
        ev("fixed", 150.0, "edit", "Edit"),
        ev("fixed", 200.0, "tool_call", "bash"),
        ev("retried", 100.0, "error", "bash", "permission"),
        ev("retried", 200.0, "tool_call", "bash"),
    ):
        _ingest(conn, event)
    conn.commit()
    link_episodes(conn)
    rows = {
        r["session_id"]: r["outcome"]
        for r in conn.execute("SELECT session_id, outcome FROM episode")
    }
    assert rows == {"fixed": "fixed", "retried": "retried"}
    conn.close()


def test_batch_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.local_corpus.batch import apply_batch, create_batch
    from scripts.local_corpus.normalize import Event

    monkeypatch.setenv("MAREF_CORPUS_DIR", str(tmp_path / "corpus"))
    db.ensure_dirs()
    conn = db.connect()
    db.init_db(conn)
    for index, sig in enumerate(("alpha", "beta", "gamma")):
        _ingest(
            conn,
            Event(
                source="opencode",
                source_event_id=f"e{index}",
                session_id=f"s{index}",
                agent_id="a",
                model="m",
                ts=100.0 + index,
                kind="error",
                tool="bash",
                error_class="tool_error",
                error_sig=sig,
                snippet=f"failure {sig}",
            ),
        )
    conn.commit()
    link_episodes(conn)

    out = tmp_path / "batch.jsonl"
    result = create_batch(conn, out, limit=5)
    assert result["items"] == 3
    assert out.with_suffix(".md").exists()

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    rows[0]["label"] = {
        "root_cause": "logic",
        "fix_type": "code",
        "severity": "medium",
        "reusable": True,
        "notes": "checked by test",
    }
    out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    applied = apply_batch(conn, out)
    assert applied == {"applied": 1, "skipped": 2}
    row = conn.execute("SELECT * FROM label").fetchone()
    assert row is not None
    assert row["root_cause"] == "logic"
    assert row["labeled_by"] == "batch"
    conn.close()


def test_signature_clustering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.local_corpus.cluster import build_clusters, top_clusters
    from scripts.local_corpus.normalize import Event

    monkeypatch.setenv("MAREF_CORPUS_DIR", str(tmp_path / "corpus"))
    db.ensure_dirs()
    conn = db.connect()
    db.init_db(conn)
    samples = [
        ("ModuleNotFoundError: No module named 'requests'", "not_found"),
        ("ModuleNotFoundError: No module named 'numpy'", "not_found"),
        ("permission denied opening config", "permission"),
        ("permission denied opening cache", "permission"),
        ("connection timed out to db", "timeout"),
    ]
    for index, (snippet, error_class) in enumerate(samples):
        _ingest(
            conn,
            Event(
                source="opencode",
                source_event_id=f"c{index}",
                session_id=f"s{index}",
                agent_id="a",
                model="m",
                ts=100.0 + index,
                kind="error",
                tool="bash",
                error_class=error_class,
                error_sig=f"sig{index}",
                snippet=snippet,
            ),
        )
    conn.commit()
    link_episodes(conn)
    result = build_clusters(conn, threshold=0.5)
    assert result == {"clusters": 3, "families": 3, "signatures": 5}
    clusters = top_clusters(conn)
    assert clusters[0]["signatures"] == 2
    conn.close()


def test_llm_consensus_and_tie() -> None:
    from scripts.local_corpus.prelabel import consensus, parse_vote

    agree = parse_vote(
        '```json\n{"root_cause":"logic","fix_type":"code","severity":"high","reusable":true}\n```'
    )
    assert agree == {
        "root_cause": "logic",
        "fix_type": "code",
        "severity": "high",
        "reusable": True,
    }
    result = consensus({"a": agree, "b": agree, "c": agree})
    assert result["unanimous_fields"] == 4
    assert result["agreement"] == 1.0
    assert result["root_cause"] == "logic"
    tie = consensus(
        {
            "a": agree,
            "b": {**agree, "root_cause": "tool"},
            "c": {**agree, "root_cause": "environment"},
        }
    )
    assert tie["root_cause"] is None
    assert tie["unanimous_fields"] == 3


def test_prelabel_run_writes_silver_and_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.local_corpus import prelabel
    from scripts.local_corpus.normalize import Event

    monkeypatch.setenv("MAREF_CORPUS_DIR", str(tmp_path / "corpus"))
    db.ensure_dirs()
    conn = db.connect()
    db.init_db(conn)
    for index, snippet in enumerate(("alpha permission denied", "beta odd failure")):
        _ingest(
            conn,
            Event(
                source="opencode",
                source_event_id=f"p{index}",
                session_id=f"s{index}",
                agent_id="a",
                model="m",
                ts=100.0 + index,
                kind="error",
                tool="bash",
                error_class="permission",
                error_sig=f"sig{index}",
                snippet=snippet,
            ),
        )
    conn.commit()
    link_episodes(conn)
    episode_ids = [str(r["id"]) for r in conn.execute("SELECT id FROM episode ORDER BY started_at")]
    batch = tmp_path / "b.jsonl"
    batch.write_text(
        "\n".join(
            json.dumps({"id": eid, "snippet": snip, "runtime": "opencode"})
            for eid, snip in zip(
                episode_ids, ("alpha permission denied", "beta odd failure"), strict=True
            )
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_ask(model: Any, prompt: str, timeout: int = 90, retries: int = 2) -> dict[str, object]:
        if "alpha" in prompt:
            return {
                "root_cause": "environment",
                "fix_type": "config",
                "severity": "high",
                "reusable": True,
            }
        return {
            "root_cause": {"deepseek": "logic", "qwen": "tool", "glm": "environment"}[model.name],
            "fix_type": "code",
            "severity": "medium",
            "reusable": False,
        }

    monkeypatch.setattr(prelabel, "ask", fake_ask)
    result = prelabel.run(conn, str(batch), ["deepseek", "qwen", "glm"], workers=2, write=True)
    assert result["stats"]["accepted"] == 1
    assert result["stats"]["needs_review"] == 1
    labeled = conn.execute("SELECT * FROM label WHERE episode_id=?", (episode_ids[0],)).fetchone()
    assert labeled is not None
    assert labeled["labeled_by"].startswith("llm-consensus:")
    assert labeled["llm_suggestion_json"] != "{}"
    review = conn.execute(
        "SELECT label_status FROM episode WHERE id=?", (episode_ids[1],)
    ).fetchone()
    assert review["label_status"] == "needs_review"
    conn.close()


def test_classifier_prefers_informative_line() -> None:
    from scripts.local_corpus.normalize import classify_error

    assert classify_error("from PermissionMatrix import X\nNameError: name 'os'") == "type"
    assert (
        classify_error("Traceback (most recent call last):\n  File 'x'\nNameError: boom") == "type"
    )
    assert classify_error("permission denied writing /etc/hosts") == "permission"


def test_calibration_flags_class_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.local_corpus.calibrate import report
    from scripts.local_corpus.normalize import Event

    monkeypatch.setenv("MAREF_CORPUS_DIR", str(tmp_path / "corpus"))
    db.ensure_dirs()
    conn = db.connect()
    db.init_db(conn)
    specs = [
        ("permission denied writing /etc/hosts", "permission", "environment"),
        ("permission denied opening file", "permission", "environment"),
        ("permission denied reading socket", "permission", "tool"),
    ]
    for index, (snippet, error_class, _cause) in enumerate(specs):
        _ingest(
            conn,
            Event(
                source="opencode",
                source_event_id=f"cal{index}",
                session_id=f"cal{index}",
                agent_id="a",
                model="m",
                ts=100.0 + index,
                kind="error",
                tool="bash",
                error_class=error_class,
                error_sig=f"calsig{index}",
                snippet=snippet,
            ),
        )
    conn.commit()
    link_episodes(conn)
    for index, (_, _, cause) in enumerate(specs):
        episode = conn.execute(
            "SELECT id FROM episode WHERE session_id=?", (f"cal{index}",)
        ).fetchone()
        record_label(
            conn,
            str(episode["id"]),
            root_cause=cause,
            fix_type="config",
            severity="medium",
            reusable=False,
            labeled_by="llm-consensus:test",
        )
        conn.execute(
            "UPDATE label SET agree_with_llm=100 WHERE episode_id=?", (str(episode["id"]),)
        )
    conn.commit()
    data = report(conn, top=5)
    assert data["labeled"] == 3
    assert len(data["mismatches"]) == 1
    family = data["families"][0]
    assert family["family"] == "permission"
    assert family["purity"] == 0.67
    conn.close()

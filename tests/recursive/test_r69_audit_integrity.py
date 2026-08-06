from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from maref.recursive.audit_schema import (
    AuditEntry,
    AuditReader,
    AuditSeverity,
    AuditWriter,
)
from maref.recursive.integrity_baseline import IntegrityBaseline
from maref.recursive.permission_matrix import (
    PermissionEntry,
    PermissionMatrix,
)


class TestAuditEntry:
    def test_to_dict_contains_all_fields(self) -> None:
        entry = AuditEntry(
            event_type="role_invoke",
            severity=AuditSeverity.WARN,
            layer=3,
            from_hexagram=10,
            to_hexagram=20,
            entropy_value=2.5,
            agent_did="did:maref:test/agent/v1",
            agent_role="Executor",
            trust_score=0.85,
            trigger_type="manual",
            decision="allow",
            hook_chain_results=[{"handler_id": "h1", "verdict": "pass"}],
            duration_ms=150,
            correlation_ids={"span_id": "span-123", "audit_id": "aud-456"},
        )
        d = entry.to_dict()
        assert d["event_type"] == "role_invoke"
        assert d["severity"] == "WARN"
        assert d["layer"] == 3
        assert d["agent_did"] == "did:maref:test/agent/v1"
        assert len(d["hook_chain_results"]) == 1

    def test_to_jsonl_is_valid_json(self) -> None:
        entry = AuditEntry(event_type="test")
        line = entry.to_jsonl()
        parsed = json.loads(line)
        assert parsed["event_type"] == "test"

    def test_default_values(self) -> None:
        entry = AuditEntry()
        assert len(entry.event_id) > 0
        assert entry.severity == AuditSeverity.INFO


class TestAuditWriter:
    def test_write_and_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            writer = AuditWriter(log_path)
            entry = AuditEntry(event_type="role_invoke", severity=AuditSeverity.INFO)
            writer.write(entry)

            reader = AuditReader(log_path)
            results = reader.query()
            assert len(results) == 1
            assert results[0].event_type == "role_invoke"

    def test_write_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            writer = AuditWriter(log_path)
            entries = [
                AuditEntry(event_type="test", severity=AuditSeverity.INFO),
                AuditEntry(event_type="test", severity=AuditSeverity.WARN),
            ]
            writer.write_batch(entries)

            reader = AuditReader(log_path)
            results = reader.query()
            assert len(results) == 2


class TestAuditReader:
    def test_query_by_severity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            writer = AuditWriter(log_path)
            writer.write(AuditEntry(event_type="test", severity=AuditSeverity.INFO))
            writer.write(AuditEntry(event_type="test", severity=AuditSeverity.FATAL))
            writer.write(AuditEntry(event_type="test", severity=AuditSeverity.WARN))

            reader = AuditReader(log_path)
            fatals = reader.query(severity="FATAL")
            assert len(fatals) == 1

    def test_query_by_time_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            writer = AuditWriter(log_path)
            now = time.time()
            old = AuditEntry(
                event_type="test",
                timestamp=now - 1000,
            )
            recent = AuditEntry(
                event_type="test",
                timestamp=now,
            )
            writer.write(old)
            writer.write(recent)

            reader = AuditReader(log_path)
            results = reader.query(time_range=(now - 1, now + 1))
            assert len(results) == 1

    def test_query_by_event_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            writer = AuditWriter(log_path)
            writer.write(AuditEntry(event_type="role_invoke"))
            writer.write(AuditEntry(event_type="tool_call"))

            reader = AuditReader(log_path)
            results = reader.query(event_type="tool_call")
            assert len(results) == 1

    def test_query_by_agent_did(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            writer = AuditWriter(log_path)
            writer.write(AuditEntry(event_type="test", agent_did="did:a"))
            writer.write(AuditEntry(event_type="test", agent_did="did:b"))

            reader = AuditReader(log_path)
            results = reader.query(agent_did="did:a")
            assert len(results) == 1

    def test_query_nonexistent_file(self) -> None:
        reader = AuditReader(Path("/nonexistent/audit.jsonl"))
        results = reader.query()
        assert len(results) == 0

    def test_trace_decision_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            writer = AuditWriter(log_path)
            e1 = AuditEntry(
                event_id="e1",
                event_type="test",
                correlation_ids={},
            )
            e2 = AuditEntry(
                event_id="e2",
                event_type="test",
                correlation_ids={"upstream_event_id": "e1"},
            )
            e3 = AuditEntry(
                event_id="e3",
                event_type="test",
                correlation_ids={"upstream_event_id": "e2"},
            )
            writer.write(e1)
            writer.write(e2)
            writer.write(e3)

            reader = AuditReader(log_path)
            chain = reader.trace_decision_chain("e3")
            assert len(chain) == 3
            assert chain[0].event_id == "e3"

    def test_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            writer = AuditWriter(log_path)
            for _i in range(10):
                writer.write(AuditEntry(event_type="test"))

            reader = AuditReader(log_path)
            results = reader.query(limit=5)
            assert len(results) == 5


class TestIntegrityBaseline:
    def test_register_and_verify_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / ".maref/integrity"
            baseline = IntegrityBaseline(storage)

            # Create a test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("print('hello')", encoding="utf-8")

            baseline.register([str(test_file)])
            ok, failures = baseline.verify()
            assert ok
            assert len(failures) == 0

    def test_verify_detects_modified_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / ".maref/integrity"
            baseline = IntegrityBaseline(storage)

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("print('hello')", encoding="utf-8")
            baseline.register([str(test_file)])

            test_file.write_text("print('modified')", encoding="utf-8")
            ok, failures = baseline.verify()
            assert not ok
            assert any("MISMATCH" in f for f in failures)

    def test_verify_detects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / ".maref/integrity"
            baseline = IntegrityBaseline(storage)

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("print('hello')", encoding="utf-8")
            baseline.register([str(test_file)])

            test_file.unlink()
            ok, failures = baseline.verify()
            assert not ok
            assert any("MISSING" in f for f in failures)

    def test_update_refreshes_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / ".maref/integrity"
            baseline = IntegrityBaseline(storage)

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("version1", encoding="utf-8")
            baseline.register([str(test_file)])

            test_file.write_text("version2", encoding="utf-8")
            ok, _ = baseline.update(str(test_file))
            assert ok

            ok2, _ = baseline.verify()
            assert ok2

    def test_save_and_load_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / ".maref/integrity"
            baseline = IntegrityBaseline(storage)

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("data", encoding="utf-8")
            baseline.register([str(test_file)])

            # Create a new instance and load
            baseline2 = IntegrityBaseline(storage)
            baseline2.load()
            ok, _ = baseline2.verify()
            assert ok

    def test_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / ".maref/integrity"
            baseline = IntegrityBaseline(storage)

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("data", encoding="utf-8")
            baseline.register([str(test_file)])
            baseline.clear()

            ok, failures = baseline.verify()
            assert ok
            assert len(failures) == 0

    def test_update_nonexistent_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / ".maref/integrity"
            baseline = IntegrityBaseline(storage)
            ok, msg = baseline.update("/nonexistent/file.py")
            assert not ok

    def test_register_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / ".maref/integrity"
            baseline = IntegrityBaseline(storage)

            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "a.py").write_text("a", encoding="utf-8")
            (subdir / "b.py").write_text("b", encoding="utf-8")
            (subdir / ".hidden").write_text("hidden", encoding="utf-8")

            records = baseline.register([str(subdir)])
            assert len(records) == 2
            ok, failures = baseline.verify()
            assert ok

    def test_load_non_dict_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / ".maref/integrity"
            baseline_file = storage / "baseline.yaml"
            storage.mkdir(parents=True, exist_ok=True)
            baseline_file.write_text("- list_item\n- not_a_dict\n", encoding="utf-8")

            baseline = IntegrityBaseline(storage)
            baseline.load()
            ok, _ = baseline.verify()
            assert ok

    def test_storage_dir_property(self) -> None:
        baseline = IntegrityBaseline(Path("/tmp/test_integrity"))
        assert baseline.storage_dir == Path("/tmp/test_integrity")

    def test_register_nonexistent_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / ".maref/integrity"
            baseline = IntegrityBaseline(storage)
            records = baseline.register(["/nonexistent/path/xyz"])
            assert len(records) == 0


class TestPermissionMatrix:
    def test_default_permissions_exists(self) -> None:
        matrix = PermissionMatrix()
        assert len(matrix.get_all_permissions()) >= 5

    def test_check_allowed_tool(self) -> None:
        matrix = PermissionMatrix()
        assert matrix.check("坎", "search")

    def test_check_denied_tool(self) -> None:
        matrix = PermissionMatrix()
        assert not matrix.check("坎", "write_to_file")

    def test_check_entropy_exceeds(self) -> None:
        matrix = PermissionMatrix()
        assert not matrix.check("坤", "store", entropy=10.0)

    def test_check_operation_forbidden(self) -> None:
        matrix = PermissionMatrix()
        assert not matrix.check_operation("震", "rm -rf /tmp")

    def test_check_operation_allowed(self) -> None:
        matrix = PermissionMatrix()
        assert matrix.check_operation("坎", "search files")

    def test_get_permissions_existing(self) -> None:
        matrix = PermissionMatrix()
        entry = matrix.get_permissions("离")
        assert entry is not None
        assert "review" in entry.allowed_tools

    def test_get_permissions_nonexistent(self) -> None:
        matrix = PermissionMatrix()
        assert matrix.get_permissions("nonexistent") is None

    def test_custom_permissions(self) -> None:
        custom = [
            PermissionEntry(role="custom", hexagram=-1, allowed_tools=["do_something"]),
        ]
        matrix = PermissionMatrix(custom)
        assert matrix.check("custom", "do_something")
        assert not matrix.check("坎", "search")

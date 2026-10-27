"""审计外部锚定（P1-T3）——批量 Merkle 锚点与离线校验。"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.audit_anchor import (
    TSA_FAILURE_EVENT,
    AnchorRecord,
    AuditAnchor,
    merkle_root,
    record_leaf_hash,
    verify_anchors,
)
from maref.governance.audit_chain_verify import verify_audit_chain

HMAC_KEY = "test-anchor-key"


def _logger(tmp_path: Path) -> AuditLogger:
    return AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key=HMAC_KEY)


def _fill(logger: AuditLogger, count: int) -> None:
    for index in range(count):
        logger.log(
            event_type="governance_decision",
            actor="test-suite",
            action=f"decision-{index}",
            details=f"ALLOW: step {index}",
            metadata={"step": index, "risk": "low"},
        )


def _anchor(tmp_path: Path, **overrides) -> AuditAnchor:
    options = {
        "audit_path": tmp_path / "audit.jsonl",
        "anchors_path": tmp_path / "anchors.jsonl",
        "batch_size": 100,
        "batch_seconds": 3600.0,
    }
    options.update(overrides)
    return AuditAnchor(**options)


def _ids(path: Path) -> list[str]:
    return [
        json.loads(line)["id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resign_chain(records: list[dict]) -> None:
    """按审计日志的算法重算 chain_hash 与 HMAC，模拟攻击者重建整条链。"""
    for index, record in enumerate(records):
        record.setdefault("previous_hash", "")
        payload = {
            "id": record["id"],
            "timestamp": record["timestamp"],
            "event_type": record["event_type"],
            "actor": record["actor"],
            "action": record["action"],
            "details": record["details"],
            "metadata": record["metadata"],
            "previous_hash": record["previous_hash"],
        }
        for optional in ("parent_action_id", "tenant_id", "layer", "round"):
            if record.get(optional):
                payload[optional] = record[optional]
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode(
            "utf-8"
        )
        record["chain_hash"] = hashlib.sha256(
            record["previous_hash"].encode("utf-8") + encoded
        ).hexdigest()
        record["hmac_signature"] = hmac.new(
            HMAC_KEY.encode("utf-8"), encoded, hashlib.sha256
        ).hexdigest()
        if index + 1 < len(records):
            records[index + 1]["previous_hash"] = record["chain_hash"]


class TestBatching:
    def test_count_batch_anchors_when_full(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 7)
        anchor = _anchor(tmp_path, batch_size=3, batch_seconds=10_000, audit=logger)

        first = anchor.maybe_anchor(now=1000.0)

        assert first is not None
        assert first.event_count == 3
        assert anchor.pending_count == 4
        second = anchor.maybe_anchor(now=1001.0)
        assert second is not None
        assert second.event_count == 3
        assert anchor.pending_count == 1
        assert anchor.maybe_anchor(now=1002.0) is None

    def test_anchor_now_flushes_remaining_in_batches(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 5)
        anchor = _anchor(tmp_path, batch_size=2)
        ids = _ids(tmp_path / "audit.jsonl")

        records = anchor.anchor_now(now=1000.0)

        assert [record.event_count for record in records] == [2, 2, 1]
        assert records[0].batch_start_id == ids[0]
        assert records[1].batch_start_id == ids[2]
        assert records[-1].batch_end_id == ids[-1]
        assert anchor.pending_count == 0

    def test_time_batch_anchors_after_window(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 2)
        anchor = _anchor(tmp_path, batch_size=100, batch_seconds=60, now=lambda: 500.0)

        assert anchor.maybe_anchor() is None

        record = anchor.maybe_anchor(now=560.0)

        assert record is not None
        assert record.event_count == 2
        assert record.anchored_at == 560.0

    def test_invalid_batching_config_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            _anchor(tmp_path, batch_size=0)
        with pytest.raises(ValueError):
            _anchor(tmp_path, batch_seconds=0)


class TestMerkle:
    def test_merkle_root_binds_content_and_order(self):
        first = {"id": "audit-1", "details": "ALLOW"}
        second = {"id": "audit-2", "details": "DENY"}
        tampered = {"id": "audit-2", "details": "ALLOW"}

        assert merkle_root([]) == ""
        assert merkle_root([first]) == record_leaf_hash(first)
        assert merkle_root([first, second]) != merkle_root([second, first])
        assert merkle_root([first, second]) != merkle_root([first, tampered])

    def test_leaf_hash_uses_canonical_json(self):
        record = {"id": "audit-1", "metadata": {"b": 2, "a": 1}}

        canonical = json.dumps(
            record, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
        assert record_leaf_hash(record) == hashlib.sha256(canonical).hexdigest()

    def test_anchor_record_round_trip(self):
        record = AnchorRecord(
            batch_start_id="audit-1",
            batch_end_id="audit-3",
            merkle_root="a" * 64,
            event_count=3,
            tsa_token="example",
            anchored_at=1234.5,
        )

        assert AnchorRecord.from_dict(record.to_dict()) == record


class TestVerification:
    def test_clean_anchors_verify(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 5)
        _anchor(tmp_path, batch_size=2).anchor_now(now=1000.0)

        report = verify_anchors(tmp_path / "audit.jsonl", tmp_path / "anchors.jsonl")

        assert report.ok is True
        assert report.issues == []
        assert report.anchor_count == 3
        assert report.total_events == 5
        assert report.anchored_events == 5
        assert report.uncovered_events == 0

    def test_deleted_middle_event_fails(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 6)
        _anchor(tmp_path, batch_size=6).anchor_now(now=1000.0)
        lines = _read_lines(tmp_path / "audit.jsonl")
        del lines[3]
        _write_lines(tmp_path / "audit.jsonl", lines)

        report = verify_anchors(tmp_path / "audit.jsonl", tmp_path / "anchors.jsonl")

        assert report.ok is False
        assert any("expected" in issue for issue in report.issues)

    def test_modified_payload_fails(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 6)
        _anchor(tmp_path, batch_size=6).anchor_now(now=1000.0)
        lines = _read_lines(tmp_path / "audit.jsonl")
        record = json.loads(lines[2])
        record["details"] = "ALLOW: tampered"
        record["metadata"]["step"] = 99
        lines[2] = json.dumps(record, ensure_ascii=False)
        _write_lines(tmp_path / "audit.jsonl", lines)

        report = verify_anchors(tmp_path / "audit.jsonl", tmp_path / "anchors.jsonl")

        assert report.ok is False
        assert any("merkle root mismatch" in issue for issue in report.issues)

    def test_modified_payload_fails_even_with_recomputed_chain(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 6)
        _anchor(tmp_path, batch_size=6).anchor_now(now=1000.0)
        audit_path = tmp_path / "audit.jsonl"
        records = [json.loads(line) for line in _read_lines(audit_path)]
        records[2]["details"] = "ALLOW: tampered"
        records[2]["metadata"]["step"] = 99
        _resign_chain(records)
        _write_lines(audit_path, [json.dumps(record, ensure_ascii=False) for record in records])

        chain = verify_audit_chain(audit_path, hmac_key=HMAC_KEY)

        assert chain.integrity_intact is True
        report = verify_anchors(audit_path, tmp_path / "anchors.jsonl")
        assert report.ok is False
        assert any("merkle root mismatch" in issue for issue in report.issues)

    def test_rewritten_history_fails_even_with_valid_chain(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 6)
        _anchor(tmp_path, batch_size=6).anchor_now(now=1000.0)
        audit_path = tmp_path / "audit.jsonl"
        audit_path.write_text("", encoding="utf-8")
        _fill(_logger(tmp_path), 6)

        chain = verify_audit_chain(audit_path, hmac_key=HMAC_KEY)

        assert chain.integrity_intact is True
        report = verify_anchors(audit_path, tmp_path / "anchors.jsonl")
        assert report.ok is False
        assert any("not found" in issue for issue in report.issues)

    def test_missing_anchors_file_fails(self, tmp_path):
        _fill(_logger(tmp_path), 2)

        report = verify_anchors(tmp_path / "audit.jsonl", tmp_path / "missing.jsonl")

        assert report.ok is False
        assert any("anchors file not found" in issue for issue in report.issues)

    def test_empty_anchors_file_fails(self, tmp_path):
        _fill(_logger(tmp_path), 2)
        (tmp_path / "anchors.jsonl").write_text("", encoding="utf-8")

        report = verify_anchors(tmp_path / "audit.jsonl", tmp_path / "anchors.jsonl")

        assert report.ok is False
        assert any("no anchor records" in issue for issue in report.issues)

    def test_tampered_merkle_root_fails(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 4)
        _anchor(tmp_path, batch_size=4).anchor_now(now=1000.0)
        anchors_path = tmp_path / "anchors.jsonl"
        entries = _read_lines(anchors_path)
        record = json.loads(entries[0])
        record["merkle_root"] = "0" * 64
        _write_lines(anchors_path, [json.dumps(record, ensure_ascii=False)])

        report = verify_anchors(tmp_path / "audit.jsonl", anchors_path)

        assert report.ok is False
        assert any("merkle root mismatch" in issue for issue in report.issues)

    def test_deleted_anchor_record_breaks_contiguity(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 6)
        _anchor(tmp_path, batch_size=2).anchor_now(now=1000.0)
        anchors_path = tmp_path / "anchors.jsonl"
        entries = _read_lines(anchors_path)
        del entries[1]
        _write_lines(anchors_path, entries)

        report = verify_anchors(tmp_path / "audit.jsonl", anchors_path)

        assert report.ok is False
        assert any("contiguous" in issue for issue in report.issues)

    def test_malformed_anchor_record_fails(self, tmp_path):
        logger = _logger(tmp_path)
        _fill(logger, 2)
        _anchor(tmp_path, batch_size=2).anchor_now(now=1000.0)
        anchors_path = tmp_path / "anchors.jsonl"
        lines = _read_lines(anchors_path)
        lines.append('{"batch_start_id": "audit-1"}')
        _write_lines(anchors_path, lines)

        report = verify_anchors(tmp_path / "audit.jsonl", anchors_path)

        assert report.ok is False
        assert any("invalid anchor record" in issue for issue in report.issues)


class TestTSAFailure:
    def test_tsa_unavailable_is_fail_open(self, tmp_path):
        alerts: list[str] = []

        def offline_tsa(root: str) -> str:
            raise RuntimeError("tsa offline")

        logger = _logger(tmp_path)
        _fill(logger, 3)
        anchor = _anchor(
            tmp_path,
            batch_size=10,
            tsa=offline_tsa,
            alert=alerts.append,
            audit=logger,
        )

        records = anchor.anchor_now(now=1000.0)

        assert len(records) == 1
        assert records[0].event_count == 3
        assert records[0].tsa_token == ""
        assert alerts and "TSA" in alerts[0]
        events = logger.read_filtered(event_type=TSA_FAILURE_EVENT)
        assert len(events) == 1
        assert events[0].metadata["priority"] == "high"
        assert events[0].metadata["merkle_root"] == records[0].merkle_root

        report = verify_anchors(tmp_path / "audit.jsonl", tmp_path / "anchors.jsonl")
        assert report.ok is True
        assert report.uncovered_events == 1
        chain = verify_audit_chain(tmp_path / "audit.jsonl", hmac_key=HMAC_KEY)
        assert chain.integrity_intact is True

        logger.log(
            event_type="governance_decision",
            actor="pipeline",
            action="decide",
            details="DENY: budget exhausted",
        )
        assert len(logger.read_all(max_entries=None)) == 5

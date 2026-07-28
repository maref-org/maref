from __future__ import annotations

import time

from maref.governance.audit import AuditLogger
from maref.reporting.generator import ReportGenerator
from maref.reporting.models import SystemStateSnapshot
from maref.signing.signing_key import ReportSigningKey


class TestReportGenerator:
    def test_generate_empty_audit_log(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()
        assert report.audit_summary.total_events == 0
        assert report.merkle_root == ""
        assert report.signer_fingerprint == key.fingerprint
        assert report.signature != ""
        assert report.verify_signature(key.public_key_pem) is True

    def test_generate_with_entries(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "approved transfer")
        logger.log("decision", "agent-b", "reject", "risk too high")
        logger.log("verify", "agent-a", "check", "verified ok")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()
        assert report.audit_summary.total_events == 3
        assert report.audit_summary.event_types == {"decision": 2, "verify": 1}
        assert report.audit_summary.actor_counts == {"agent-a": 2, "agent-b": 1}
        assert report.audit_summary.time_range_start is not None
        assert report.audit_summary.time_range_end is not None
        assert report.merkle_root != ""
        assert report.signer_fingerprint == key.fingerprint
        assert report.verify_signature(key.public_key_pem) is True

    def test_generate_incremental(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "first")
        time.sleep(0.02)
        mid = time.time()
        time.sleep(0.02)
        logger.log("decision", "agent-b", "reject", "second")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report_since = gen.from_audit_log(since_timestamp=mid)
        assert report_since.audit_summary.total_events == 1
        assert report_since.audit_summary.actor_counts == {"agent-b": 1}

    def test_generate_full_and_incremental_differ(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "first")
        time.sleep(0.02)
        t1 = time.time()
        time.sleep(0.02)
        logger.log("decision", "agent-b", "reject", "second")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        full = gen.from_audit_log()
        incr = gen.from_audit_log(since_timestamp=t1)
        assert full.audit_summary.total_events == 2
        assert incr.audit_summary.total_events == 1
        assert full.report_id != incr.report_id

    def test_system_state_override(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        override = SystemStateSnapshot(
            governance_state="VERIFY",
            active_agents_count=5,
            merkle_tree_size=999,
            version="v0.39.0-test",
        )
        report = gen.from_audit_log(system_state_override=override)
        assert report.system_state.governance_state == "VERIFY"
        assert report.system_state.active_agents_count == 5
        assert report.system_state.merkle_tree_size == 999

    def test_generator_without_logger_raises(self) -> None:
        key = ReportSigningKey.generate()
        gen = ReportGenerator(signing_key=key)
        try:
            gen.from_audit_log()
            raise AssertionError("should have raised")
        except ValueError as e:
            assert "AuditLogger required" in str(e)

    def test_passed_logger_overrides_constructor(self) -> None:
        key = ReportSigningKey.generate()
        logger1 = AuditLogger()
        logger2 = AuditLogger()
        logger2.log("decision", "agent-x", "override", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger1)
        report = gen.from_audit_log(audit_logger=logger2)
        assert report.audit_summary.total_events == 1

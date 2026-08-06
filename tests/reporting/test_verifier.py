from __future__ import annotations

from maref.governance.audit import AuditLogger
from maref.reporting.generator import ReportGenerator
from maref.reporting.verifier import ReportVerifier
from maref.signing.signing_key import ReportSigningKey


class TestReportVerifier:
    def test_verify_valid_report(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()
        result = ReportVerifier.verify_report(report, key.public_key_pem)
        assert result.passed is True
        assert result.checks["has_signature"] is True
        assert result.checks["valid_signature"] is True
        assert result.checks["fingerprint_match"] is True

    def test_verify_tampered_report(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()
        tampered = report.model_copy(update={"merkle_root": "tampered"})
        result = ReportVerifier.verify_report(tampered, key.public_key_pem)
        assert result.passed is False
        assert result.checks["valid_signature"] is False
        assert result.details is not None

    def test_verify_wrong_key(self) -> None:
        key1 = ReportSigningKey.generate()
        key2 = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key1, audit_logger=logger)
        report = gen.from_audit_log()
        result = ReportVerifier.verify_report(report, key2.public_key_pem)
        assert result.passed is False
        assert result.checks["valid_signature"] is False

    def test_verify_no_signature(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()
        unsigned = report.model_copy(update={"signature": ""})
        result = ReportVerifier.verify_report(unsigned, key.public_key_pem)
        assert result.passed is False
        assert result.checks["has_signature"] is False

    def test_verify_fingerprint_mismatch(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()
        wrong_fp = report.model_copy(update={"signer_fingerprint": "deadbeef"})
        result = ReportVerifier.verify_report(wrong_fp, key.public_key_pem)
        assert result.passed is False
        assert result.checks["fingerprint_match"] is False

    def test_verify_empty_report_passes_basic(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()
        result = ReportVerifier.verify_report(report, key.public_key_pem)
        assert result.passed is True

    def test_verify_with_audit_log(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "first")
        logger.log("verify", "agent-b", "check", "second")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()

        result = ReportVerifier.verify_report_with_audit_log(
            report, key.public_key_pem, logger
        )
        assert result.passed is True
        assert result.checks["event_count_matches"] is True
        assert result.checks["merkle_root_matches"] is True

    def test_verify_with_audit_log_count_mismatch(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger()
        logger.log("decision", "agent-a", "approve", "first")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()

        logger2 = AuditLogger()
        logger2.log("decision", "agent-a", "approve", "first")
        logger2.log("extra", "agent-c", "extra", "second")

        result = ReportVerifier.verify_report_with_audit_log(
            report, key.public_key_pem, logger2
        )
        assert result.passed is False
        assert result.checks["event_count_matches"] is False

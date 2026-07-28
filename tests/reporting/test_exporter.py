from __future__ import annotations

import tempfile
from pathlib import Path

from maref.governance.audit import AuditLogger
from maref.reporting.exporter import ReportExporter
from maref.reporting.generator import ReportGenerator
from maref.reporting.models import SystemStateSnapshot
from maref.signing.signing_key import ReportSigningKey


class TestReportExporter:
    def test_export_report_html(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger(hmac_key="test")
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.html"
            exporter = ReportExporter()
            result = exporter.export_report(report, out)
            assert result == out
            assert out.exists()
            html = out.read_text("utf-8")
            assert "MAREF Governance Report" in html
            assert report.report_id[:8] in html
            assert report.signer_fingerprint in html
            assert "downloadJson" in html
            assert "decision" in html

    def test_export_empty_report_html(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger(hmac_key="test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "empty.html"
            exporter = ReportExporter()
            exporter.export_report(report, out)
            html = out.read_text("utf-8")
            assert "MAREF Governance Report" in html
            assert "audit events" in html
            assert "empty" in html.lower()

    def test_export_report_with_custom_template_dir(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger(hmac_key="test")
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()

        with tempfile.TemporaryDirectory() as tmp:
            custom_tmpl = Path(tmp) / "templates"
            custom_tmpl.mkdir()
            (custom_tmpl / "report.html").write_text(
                "<h1>Custom Report</h1><p>$${report_id}</p>"
            )
            out = Path(tmp) / "out.html"
            exporter = ReportExporter(template_dir=custom_tmpl)
            exporter.export_report(report, out)
            html = out.read_text("utf-8")
            assert "Custom Report" in html
            assert "${report_id}" in html  # safe_substitute leaves unknown vars

    def test_export_index_empty_dir(self) -> None:
        key = ReportSigningKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "index.html"
            exporter = ReportExporter()
            exporter.export_index(Path(tmp), out, signer_fingerprint=key.fingerprint)
            assert out.exists()
            html = out.read_text("utf-8")
            assert "MAREF Governance Reports" in html
            assert key.fingerprint in html

    def test_export_index_with_reports(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger(hmac_key="test")
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()

        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            report_path.write_text(report.to_json())

            exporter = ReportExporter()
            out = Path(tmp) / "index.html"
            exporter.export_index(Path(tmp), out, signer_fingerprint=key.fingerprint)
            html = out.read_text("utf-8")
            assert "report.json" in html or report.report_id[:8] in html

    def test_export_and_reimport_html(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger(hmac_key="test")
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        report = gen.from_audit_log()

        with tempfile.TemporaryDirectory() as tmp:
            exporter = ReportExporter()
            out = Path(tmp) / "report.html"
            exporter.export_report(report, out)
            exporter.export_index(Path(tmp), Path(tmp) / "index.html", signer_fingerprint=key.fingerprint)

            index_html = (Path(tmp) / "index.html").read_text("utf-8")
            assert "MAREF Governance Reports" in index_html
            assert key.fingerprint in index_html

    def test_system_state_in_html(self) -> None:
        key = ReportSigningKey.generate()
        logger = AuditLogger(hmac_key="test")
        logger.log("decision", "agent-a", "approve", "test")
        gen = ReportGenerator(signing_key=key, audit_logger=logger)
        override = SystemStateSnapshot(
            governance_state="VERIFY", active_agents_count=3, version="v0.39.0-test"
        )
        report = gen.from_audit_log(system_state_override=override)

        with tempfile.TemporaryDirectory() as tmp:
            exporter = ReportExporter()
            out = Path(tmp) / "report.html"
            exporter.export_report(report, out)
            html = out.read_text("utf-8")
            assert "VERIFY" in html
            assert "v0.39.0-test" in html

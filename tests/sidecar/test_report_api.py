from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from maref.reporting.generator import ReportGenerator
from maref.signing.signing_key import ReportSigningKey


def _setup_report_dir(tmp: Path) -> tuple[ReportSigningKey, Path]:
    from maref.governance.audit import AuditLogger

    logger = AuditLogger(hmac_key="test")
    logger.log("decision", "agent-a", "approve", "test event")
    key = ReportSigningKey.generate()
    gen = ReportGenerator(signing_key=key, audit_logger=logger)
    report = gen.from_audit_log()
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "latest.json").write_text(report.to_json())
    (tmp / f"{report.report_id[:8]}.json").write_text(report.to_json())
    return key, report


class TestReportAPI:
    def test_latest_report(self) -> None:
        import sidecar.report_router as report_router

        with tempfile.TemporaryDirectory() as tmp:
            report_router._REPORT_DIR = Path(tmp)
            _setup_report_dir(Path(tmp))

            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(report_router.router)

            client = TestClient(app)
            resp = client.get("/api/v1/report/latest")
            assert resp.status_code == 200
            data = resp.json()
            assert "report_id" in data
            assert "signer_fingerprint" in data
            assert "signature" in data

    def test_latest_no_report(self) -> None:
        import sidecar.report_router as report_router

        with tempfile.TemporaryDirectory() as tmp:
            report_router._REPORT_DIR = Path(tmp)

            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(report_router.router)

            client = TestClient(app)
            resp = client.get("/api/v1/report/latest")
            assert resp.status_code == 404

    def test_report_by_id(self) -> None:
        import sidecar.report_router as report_router

        with tempfile.TemporaryDirectory() as tmp:
            report_router._REPORT_DIR = Path(tmp)
            _, report = _setup_report_dir(Path(tmp))
            short_id = report.report_id[:8]

            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(report_router.router)

            client = TestClient(app)
            resp = client.get(f"/api/v1/report/{short_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["report_id"] == report.report_id

    def test_report_by_id_not_found(self) -> None:
        import sidecar.report_router as report_router

        with tempfile.TemporaryDirectory() as tmp:
            report_router._REPORT_DIR = Path(tmp)

            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(report_router.router)

            client = TestClient(app)
            resp = client.get("/api/v1/report/nonexistent")
            assert resp.status_code == 404

    def test_generate_report(self) -> None:
        import sidecar.report_router as report_router

        with tempfile.TemporaryDirectory() as tmp:
            report_router._REPORT_DIR = Path(tmp)

            from maref.governance.audit import AuditLogger

            audit_log = Path(tmp) / "test-audit.jsonl"
            logger = AuditLogger(log_path=audit_log, hmac_key="test")
            logger.log("decision", "agent-a", "approve", "test")

            key = ReportSigningKey.generate()
            key_path = Path(tmp) / "signing.pem"
            key.save_private_key(key_path)

            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(report_router.router)

            client = TestClient(app)
            resp = client.post(
                "/api/v1/report/generate",
                params={"signing_key": str(key_path), "audit_log": str(audit_log)},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "report_id" in data
            assert data["signer_fingerprint"] == key.fingerprint

    def test_generate_report_no_key_ephemeral(self) -> None:
        import sidecar.report_router as report_router

        with tempfile.TemporaryDirectory() as tmp:
            report_router._REPORT_DIR = Path(tmp)

            from maref.governance.audit import AuditLogger

            audit_log = Path(tmp) / "test-audit.jsonl"
            logger = AuditLogger(log_path=audit_log, hmac_key="test")
            logger.log("decision", "agent-a", "approve", "test")

            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(report_router.router)

            client = TestClient(app)
            resp = client.post(
                "/api/v1/report/generate",
                params={"audit_log": str(audit_log)},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "report_id" in data
            assert data["signature"] != ""

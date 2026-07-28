"""Governance Report API — Sidecar REST endpoints for report access and generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/report")

_REPORT_DIR = Path("docs/verify")


def _find_report(id_suffix: str) -> Path | None:
    if not _REPORT_DIR.exists():
        return None
    for f in _REPORT_DIR.iterdir():
        if f.suffix == ".json" and id_suffix in f.stem:
            return f
    return None


@router.get("/latest")
def report_latest() -> dict[str, Any]:
    latest = _REPORT_DIR / "latest.json"
    if not latest.exists():
        raise HTTPException(status_code=404, detail="No reports available")
    try:
        return json.loads(latest.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read report: {e}") from e


@router.get("/{report_id}")
def report_by_id(report_id: str) -> dict[str, Any]:
    path = _find_report(report_id)
    if path is None:
        raise HTTPException(
            status_code=404, detail=f"Report not found: {report_id}"
        )
    try:
        return json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read report: {e}") from e


@router.post("/generate")
def report_generate(
    signing_key: str = "",
    audit_log: str = "",
) -> dict[str, Any]:
    from maref.governance.audit import AuditLogger
    from maref.governance.state_machine import _default_audit_log_path
    from maref.reporting.generator import ReportGenerator
    from maref.signing.signing_key import ReportSigningKey

    log_path = Path(audit_log) if audit_log else _default_audit_log_path()
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"Audit log not found: {log_path}")

    key: ReportSigningKey | None = None
    if signing_key:
        key_path = Path(signing_key)
        if not key_path.exists():
            raise HTTPException(
                status_code=400, detail=f"Signing key not found: {signing_key}"
            )
        try:
            key = ReportSigningKey.from_private_key_file(key_path)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to load signing key: {e}"
            ) from e
    else:
        key = ReportSigningKey.generate()

    logger = AuditLogger(log_path=log_path, hmac_key="")
    gen = ReportGenerator(signing_key=key)
    report = gen.from_audit_log(audit_logger=logger)
    return json.loads(report.to_json())

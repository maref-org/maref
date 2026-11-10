"""Regression tests for verifying exported audit packages offline."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.governance.audit import AuditLogger
from maref_lite.cli import _load_audit_package_entries, app


def _build_log(tmp_path: Path) -> tuple[Path, Path, AuditLogger]:
    keypair = Ed25519KeyPair.generate()
    pub_path = tmp_path / "signer.pub.pem"
    pub_path.write_text(keypair.public_key_pem, encoding="utf-8")
    log_path = tmp_path / "audit.jsonl"
    logger = AuditLogger(log_path=log_path, ed25519_keypair=keypair)
    for index in range(3):
        logger.log("demo", "agent-a", "tool_call", f"step {index}")
    return log_path, pub_path, logger


def _export_package(logger: AuditLogger, path: Path) -> dict:
    package = {
        "entry_count": len(logger.read_all()),
        "entries": [entry.to_dict() for entry in logger.read_all()],
    }
    path.write_text(json.dumps(package, indent=2), encoding="utf-8")
    return package


def test_exported_package_verifies(tmp_path: Path) -> None:
    _, pub_path, logger = _build_log(tmp_path)
    package_path = tmp_path / "audit-package.json"
    _export_package(logger, package_path)

    result = CliRunner().invoke(
        app,
        ["audit", "verify", "-f", str(package_path), "-k", str(pub_path)],
    )

    assert result.exit_code == 0
    assert "VERIFIED: 3/3" in result.output


def test_tampered_package_fails(tmp_path: Path) -> None:
    _, pub_path, logger = _build_log(tmp_path)
    package_path = tmp_path / "audit-package.json"
    package = _export_package(logger, package_path)
    package["entries"][1]["details"] = "step X"
    package_path.write_text(json.dumps(package, indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["audit", "verify", "-f", str(package_path), "-k", str(pub_path)],
    )

    assert result.exit_code == 1
    assert "FAILED" in result.output


def test_raw_jsonl_log_verifies(tmp_path: Path) -> None:
    log_path, pub_path, _ = _build_log(tmp_path)

    result = CliRunner().invoke(
        app,
        ["audit", "verify", "-f", str(log_path), "-k", str(pub_path)],
    )

    assert result.exit_code == 0
    assert "VERIFIED: 3/3" in result.output


def test_package_loader_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")

    assert _load_audit_package_entries(path) is None


def test_package_loader_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "array.json"
    path.write_text("[]", encoding="utf-8")

    assert _load_audit_package_entries(path) is None


def test_package_loader_rejects_missing_entries(tmp_path: Path) -> None:
    path = tmp_path / "no-entries.json"
    path.write_text('{"foo": 1}', encoding="utf-8")

    assert _load_audit_package_entries(path) is None


def test_package_loader_filters_non_objects(tmp_path: Path) -> None:
    path = tmp_path / "mixed.json"
    path.write_text('{"entries": [{"id": "a"}, "bad"]}', encoding="utf-8")

    assert _load_audit_package_entries(path) == [{"id": "a"}]


def test_missing_audit_file_fails(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["audit", "verify", "-f", str(tmp_path / "missing.jsonl")],
    )

    assert result.exit_code == 1
    assert "Audit log not found" in result.output


def test_missing_public_key_fails(tmp_path: Path) -> None:
    log_path, _, _ = _build_log(tmp_path)

    result = CliRunner().invoke(
        app,
        ["audit", "verify", "-f", str(log_path), "-k", str(tmp_path / "missing.pem")],
    )

    assert result.exit_code == 1
    assert "Public key file not found" in result.output


def test_verify_without_pubkey_fails_for_ed25519(tmp_path: Path) -> None:
    log_path, _, _ = _build_log(tmp_path)

    result = CliRunner().invoke(
        app,
        ["audit", "verify", "-f", str(log_path)],
    )

    assert result.exit_code == 1
    assert "no signatures could be verified" in result.output

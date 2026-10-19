from __future__ import annotations

from pathlib import Path

import pytest

import maref._paths as paths


def test_governance_base_is_absolute(monkeypatch):
    monkeypatch.delenv("MAREF_AUDIT_PATH", raising=False)
    monkeypatch.delenv("MAREF_RUNTIME_DIR", raising=False)
    base = paths.get_governance_base()
    assert base.is_absolute()
    assert base.name == ".governance"


def test_audit_path_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MAREF_AUDIT_PATH", str(tmp_path / "audit"))
    assert paths.get_governance_base() == (tmp_path / "audit").resolve()
    assert paths.get_audit_dir() == (tmp_path / "audit").resolve()


def test_meta_base_default_has_no_external_dependency(monkeypatch):
    monkeypatch.delenv("MAREF_META_PATH", raising=False)
    base = paths.get_meta_base()
    assert base.is_absolute()
    assert base == (paths.get_project_root() / ".governance" / "meta").resolve()


def test_meta_base_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MAREF_META_PATH", str(tmp_path / "meta"))
    assert paths.get_meta_base() == (tmp_path / "meta").resolve()


def test_no_ip_kingdom_photo_coupling():
    assert not hasattr(paths, "get_photo_dir")
    assert not hasattr(paths, "get_photography_root")
    assert not hasattr(paths, "get_dreamina_output_dir")


def test_legacy_audit_paths_are_absolute():
    for path in paths.get_legacy_audit_paths():
        assert isinstance(path, Path)
        assert path.is_absolute()


@pytest.mark.parametrize(
    "module",
    [
        "maref.observability.meta_monitor",
        "maref.observability.health_snapshot",
        "maref.observability.alert_feedback_tracker",
        "maref.observability.audit_paths",
        "maref.infra.state",
        "maref.governance.state_machine",
    ],
)
def test_paths_dependent_modules_import(module: str):
    __import__(module)

"""sync_version 的发布窗口语义。

回归背景（2026-11-21）：升级 0.55.3 时只改了 pyproject / `__init__` / README / Dockerfile /
CHANGELOG，漏掉 `otel_middleware.py`（3 处 tracer 版本）与 `mcp_bridge.py`，CI 的
`test_otel_middleware.py` 直接抓到 0.55.2 != 0.55.3。项目本来就有 `scripts/sync_version.py`
统一管理这些位点——正确做法是先跑它，而不是逐个 grep。

现在它还必须理解发布窗口：`pending_release` 与目标版本一致时算已同步，
且**绝不**把未发布的版本写成 `current_release`。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_PATH = REPO_ROOT / "scripts" / "sync_version.py"


def _load_sync():
    spec = importlib.util.spec_from_file_location("maref_sync_version", SYNC_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = _load_sync()


def _fake_repo(tmp_path: Path, state_text: str) -> dict:
    (tmp_path / "pyproject.toml").write_text('version = "1.1.0"\n', encoding="utf-8")
    (tmp_path / "STATE.yaml").write_text(state_text, encoding="utf-8")
    return {
        "pyproject.toml": {
            "path": tmp_path / "pyproject.toml",
            "pattern": r'^version\s*=\s*"([^"]+)"',
            "replacement": 'version = "{version}"',
            "priority": "source",
        },
        "STATE.yaml": {
            "path": tmp_path / "STATE.yaml",
            "pattern": r"^  current_release:\s*([^\s#]+)",
            "replacement": "  current_release: {version}",
            "priority": "derived",
        },
    }


def test_pending_release_counts_as_synced(tmp_path: Path, monkeypatch) -> None:
    state = "project:\n  current_release: 1.0.0\n  pending_release: 1.1.0\n"
    monkeypatch.setattr(sync, "VERSION_FILES", _fake_repo(tmp_path, state))

    results, source, mismatches = sync.check_versions()

    assert source == "1.1.0"
    assert mismatches == {}
    assert results["STATE.yaml"] == "1.1.0 (pending)"


def test_pending_mismatch_is_reported(tmp_path: Path, monkeypatch) -> None:
    state = "project:\n  current_release: 1.0.0\n  pending_release: 9.9.9\n"
    monkeypatch.setattr(sync, "VERSION_FILES", _fake_repo(tmp_path, state))

    _, _, mismatches = sync.check_versions()

    assert mismatches == {"STATE.yaml": "1.0.0"}


def test_sync_never_promotes_pending_to_current(tmp_path: Path, monkeypatch) -> None:
    state = "project:\n  current_release: 1.0.0\n  pending_release: 1.0.0\n"
    monkeypatch.setattr(sync, "VERSION_FILES", _fake_repo(tmp_path, state))
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    monkeypatch.setattr(sync, "date", pytest.importorskip("datetime").date)

    sync.sync_version("1.1.0")

    text = (tmp_path / "STATE.yaml").read_text(encoding="utf-8")
    assert "current_release: 1.0.0" in text
    assert "pending_release: 1.1.0" in text


def test_readme_badge_with_v_prefix_is_synced(tmp_path: Path, monkeypatch) -> None:
    """README 徽章形如 `badge/version-v1.0.0-blue`；v 前缀必须被识别。

    回归（2026-11-22）：旧正则要求 `version-` 后直接是数字，遇到 `v` 前缀
    `re.search` 静默不匹配——`--check` 仍打印 OK，徽章却停在旧版本。
    """
    readme = tmp_path / "README.md"
    readme.write_text(
        "![version](https://img.shields.io/badge/version-v1.0.0-blue)\n", encoding="utf-8"
    )
    config = _fake_repo(tmp_path, "project:\n  current_release: 1.0.0\n")
    badge_cfg = dict(sync.VERSION_FILES["README.md"])
    badge_cfg["path"] = readme
    config["README.md"] = badge_cfg
    monkeypatch.setattr(sync, "VERSION_FILES", config)
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    monkeypatch.setattr(sync, "date", pytest.importorskip("datetime").date)

    _, _, mismatches = sync.check_versions()
    assert mismatches.get("README.md") == "1.0.0"

    sync.sync_version("1.1.0")

    assert "version-v1.1.0-blue" in readme.read_text(encoding="utf-8")

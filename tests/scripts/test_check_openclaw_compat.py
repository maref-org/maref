"""OpenClaw 兼容性检查回归测试.

回归点: maref-governance/ 被 .gitignore 排除，干净 checkout 下必然缺失。
缺失必须判定为 SOURCE_UNAVAILABLE(3)，不能判定为 BREAKING(2) —— 后者会让
每日定时 workflow 假红，并在上游真实 breaking 时掩盖信号。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_openclaw_compat as compat  # noqa: E402


def test_missing_sources_empty_in_full_checkout():
    assert compat.missing_governance_sources() == []


def test_missing_sources_reports_paths_outside_repo(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg" / "package.json"
    src = tmp_path / "src" / "index.ts"
    monkeypatch.setattr(compat, "GOVERNANCE_PKG", pkg)
    monkeypatch.setattr(compat, "GOVERNANCE_SRC", src)

    assert compat.missing_governance_sources() == [str(pkg), str(src)]


def test_main_returns_source_unavailable_not_breaking(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(compat, "GOVERNANCE_PKG", tmp_path / "pkg.json")
    monkeypatch.setattr(compat, "GOVERNANCE_SRC", tmp_path / "index.ts")
    monkeypatch.setattr(sys, "argv", ["check_openclaw_compat.py", "--quiet"])

    code = compat.main()

    assert code == compat.SOURCE_UNAVAILABLE == 3
    assert "SKIP" in capsys.readouterr().err


def test_compatible_sources_return_zero(tmp_path, monkeypatch):
    governance = tmp_path / "maref-governance"
    (governance / "src").mkdir(parents=True)
    (governance / "package.json").write_text(
        json.dumps({"peerDependencies": {"openclaw": ">=2026.7.2"}})
    )
    (governance / "src" / "index.ts").write_text(
        "before_tool_call session_start session_end llm_input llm_output"
    )
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"@maref-org/sdk": "^0.2.0"},
                "devDependencies": {"typescript": "^5.5"},
            }
        )
    )
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    (sdk / "package.json").write_text(json.dumps({"version": "0.2.0"}))

    monkeypatch.setattr(compat, "GOVERNANCE_PKG", governance / "package.json")
    monkeypatch.setattr(compat, "GOVERNANCE_SRC", governance / "src" / "index.ts")
    monkeypatch.setattr(compat, "PLUGIN_PKG", plugin / "package.json")
    monkeypatch.setattr(compat, "SDK_PKG", sdk / "package.json")
    monkeypatch.setattr(sys, "argv", ["check_openclaw_compat.py", "--quiet"])

    assert compat.main() == 0

"""claim_integrity_gate 单元测试。

覆盖: C1 版本三角 / C2 引用存在性 / C3 implemented 符号 / C4 宪法版本 / C5 钩子声称。
运行: .venv/bin/python3 -m pytest tests/cli/test_claim_integrity_gate.py --no-cov -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import claim_integrity_gate as gate


def _write_repo(tmp: Path, state: dict, *, pyproject_ver="1.0.0",
                changelog_ver="1.0.0", constitution_ver="v1.0",
                hook=True, src_impl=None) -> Path:
    (tmp / "pyproject.toml").write_text(f'version = "{pyproject_ver}"\n', encoding="utf-8")
    (tmp / "CHANGELOG.md").write_text(f"## [v{changelog_ver}] - 2026-01-01\n", encoding="utf-8")
    (tmp / "docs").mkdir(exist_ok=True)
    (tmp / "docs" / "CONSTITUTION.md").write_text(f"# Constitution {constitution_ver}\n", encoding="utf-8")
    if hook:
        (tmp / ".githooks").mkdir(exist_ok=True)
        (tmp / ".githooks" / "pre-push").write_text("#!/bin/bash\n", encoding="utf-8")
    if src_impl:
        (tmp / "src").mkdir(exist_ok=True)
        (tmp / "src" / "bridge.py").write_text(src_impl, encoding="utf-8")
    (tmp / "STATE.yaml").write_text(yaml.safe_dump(state, allow_unicode=True), encoding="utf-8")
    return tmp


BASE_STATE = {
    "version": 1,
    "project": {
        "current_release": "1.0.0",
        "constitution_version": "v1.0",
    },
    "track_b": {"pre_push_hook": "present"},
}


def test_all_clean(tmp_path):
    repo = _write_repo(tmp_path, dict(BASE_STATE), src_impl='name="tool_a"')
    result = gate.run_all(repo)
    assert result["ok"] is True
    assert result["errors"] == 0


def test_c1_pyproject_drift(tmp_path):
    state = dict(BASE_STATE, project={**BASE_STATE["project"], "current_release": "2.0.0"})
    repo = _write_repo(tmp_path, state)
    result = gate.run_all(repo)
    assert result["ok"] is False
    assert any(f["check"] == "C1" and "pyproject" in f["detail"] for f in result["findings"])


def test_c1_changelog_drift(tmp_path):
    repo = _write_repo(tmp_path, dict(BASE_STATE), changelog_ver="0.9.0")
    result = gate.run_all(repo)
    assert any(f["check"] == "C1" and "CHANGELOG" in f["detail"] and f["severity"] == "ERROR"
               for f in result["findings"])


def test_c2_missing_referenced_path(tmp_path):
    state = dict(BASE_STATE, project={**BASE_STATE["project"], "rsi_report": "docs/missing-report.md"})
    repo = _write_repo(tmp_path, state)
    result = gate.run_all(repo)
    assert any(f["check"] == "C2" and "docs/missing-report.md" in f["detail"]
               for f in result["findings"])


def test_c2_ignores_urls_and_home(tmp_path):
    state = dict(BASE_STATE, project={**BASE_STATE["project"],
                                      "public_repo": "https://example.com/x.md",
                                      "local_hook": "~/.claude/hooks/x.py"})
    repo = _write_repo(tmp_path, state)
    result = gate.run_all(repo)
    assert not any(f["check"] == "C2" for f in result["findings"])


def test_c3_implemented_symbol_missing(tmp_path):
    state = dict(BASE_STATE, project={**BASE_STATE["project"],
                                      "tool": {"name": "ghost_tool", "status": "implemented"}})
    repo = _write_repo(tmp_path, state, src_impl='name="other"')
    result = gate.run_all(repo)
    assert any(f["check"] == "C3" and "ghost_tool" in f["detail"] for f in result["findings"])


def test_c3_implemented_symbol_present(tmp_path):
    state = dict(BASE_STATE, project={**BASE_STATE["project"],
                                      "tool": {"name": "real_tool", "status": "implemented"}})
    repo = _write_repo(tmp_path, state, src_impl='name="real_tool"')
    result = gate.run_all(repo)
    assert not any(f["check"] == "C3" for f in result["findings"])


def test_c4_constitution_drift(tmp_path):
    state = dict(BASE_STATE, project={**BASE_STATE["project"], "constitution_version": "v9.9"})
    repo = _write_repo(tmp_path, state)
    result = gate.run_all(repo)
    assert any(f["check"] == "C4" and f["severity"] == "ERROR" for f in result["findings"])


def test_c5_hook_claim_unmet(tmp_path):
    repo = _write_repo(tmp_path, dict(BASE_STATE), hook=False)
    result = gate.run_all(repo)
    assert any(f["check"] == "C5" and "pre-push" in f["detail"] for f in result["findings"])


def test_advisory_mode_always_zero(tmp_path):
    state = dict(BASE_STATE, project={**BASE_STATE["project"], "current_release": "9.9.9"})
    repo = _write_repo(tmp_path, state)
    result = gate.run_all(repo)
    assert result["ok"] is False  # 非 advisory 下应报错
    # advisory exit code 逻辑
    old_argv = sys.argv
    sys.argv = ["claim_integrity_gate.py", "--root", str(repo), "--advisory"]
    try:
        assert gate.main() == 0
    finally:
        sys.argv = old_argv


def test_real_repo_smoke():
    """对本仓真实 STATE.yaml 跑一遍——只允许 WARNING，不允许崩溃。"""
    root = Path(__file__).resolve().parents[2]
    if not (root / "STATE.yaml").exists():
        pytest.skip("STATE.yaml 不在预期位置")
    result = gate.run_all(root)
    assert "ok" in result and "findings" in result

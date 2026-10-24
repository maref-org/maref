"""疫苗编译的写入去抖测试。

每日定时编译只刷新 compiled_at 会让工作区永久 dirty；内容未变时应跳过写入。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

MODULE_PATH = SCRIPTS_DIR / "vaccine_pipeline" / "04_compile_vaccines.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("vaccine_compile", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_patterns(path: Path, trigger: str = "rm -rf") -> None:
    path.write_text(json.dumps([{
        "pattern_id": "P1",
        "attack_class": "destructive",
        "trigger": trigger,
    }]))


def _prepare(tmp_path: Path, monkeypatch):
    module = _load_module()
    patterns = tmp_path / "patterns.json"
    vaccines = tmp_path / "vaccines.json"
    _write_patterns(patterns)
    monkeypatch.setattr(module, "PATTERNS_FILE", str(patterns))
    monkeypatch.setattr(module, "vaccine_path", lambda _name: vaccines)
    return module, patterns, vaccines


def test_compile_skips_write_when_content_unchanged(tmp_path, monkeypatch):
    module, _patterns, vaccines = _prepare(tmp_path, monkeypatch)

    module.compile_vaccines()
    first = json.loads(vaccines.read_text())
    stamp = first[0]["batch"]["compiled_at"]

    module.compile_vaccines()
    second = json.loads(vaccines.read_text())

    assert second == first
    assert second[0]["batch"]["compiled_at"] == stamp


def test_compile_rewrites_when_pattern_changes(tmp_path, monkeypatch):
    module, patterns, vaccines = _prepare(tmp_path, monkeypatch)

    module.compile_vaccines()
    _write_patterns(patterns, "drop table")
    module.compile_vaccines()

    updated = json.loads(vaccines.read_text())
    assert updated[0]["product"]["safetygate_rule"]["pattern"] == "drop table"


def test_compile_handles_corrupt_existing_file(tmp_path, monkeypatch):
    module, _patterns, vaccines = _prepare(tmp_path, monkeypatch)
    vaccines.write_text("{not json")

    module.compile_vaccines()

    assert json.loads(vaccines.read_text())[0]["vaccine_id"] == "VAX-0001"

"""`maref conformance` — 尺子必须有 pip 可用的入口。

回归背景（2026-11-21 复盘）：conformance 包进了 wheel，但运行它需要的
``scripts/conformance_run.py`` 与 ``conformance/examples/`` 不在 wheel 里，
根 README 也没有任何提及——"10 分钟快速开始"实际只有 git clone 一条路。

本测试锁死三件事：
1. CLI 入口存在且能跑内置 fixture（不依赖仓库文件）；
2. 退出码 0/1/2 与语义一致；
3. 签名报告可被第三方用同一密钥验证（错误的密钥必须 exit 1）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from maref_lite.cli import app

runner = CliRunner()


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_demo_good_is_conformant() -> None:
    result = runner.invoke(app, ["conformance", "--demo", "good"])
    output = _plain(result.output)

    assert result.exit_code == 0, output
    assert "VERDICT conformant" in output
    assert "10 pass / 0 fail" in output


def test_demo_bad_fails_closed() -> None:
    result = runner.invoke(app, ["conformance", "--demo", "bad"])
    output = _plain(result.output)

    assert result.exit_code == 1, output
    assert "VERDICT" in output
    assert "fail" in output


def test_no_input_is_usage_error() -> None:
    result = runner.invoke(app, ["conformance"])

    assert result.exit_code == 2
    assert "exactly one of --trace or --demo" in _plain(result.output)


def test_trace_and_demo_together_is_usage_error(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    trace.write_text("{}\n", encoding="utf-8")

    result = runner.invoke(app, ["conformance", "--demo", "good", "--trace", str(trace)])

    assert result.exit_code == 2


def test_missing_trace_is_exit_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["conformance", "--trace", str(tmp_path / "absent.jsonl")])

    assert result.exit_code == 2


def test_signed_report_can_be_verified(tmp_path: Path) -> None:
    report = tmp_path / "report.json"

    produced = runner.invoke(
        app,
        ["conformance", "--demo", "good", "--key", "secret", "--out", str(report), "--quiet"],
    )
    assert produced.exit_code == 0, _plain(produced.output)
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["signature"], "报告必须带签名"

    verified = runner.invoke(app, ["conformance", "--verify", str(report), "--key", "secret"])
    output = _plain(verified.output)
    assert verified.exit_code == 0, output
    assert "signature valid" in output


def test_verify_with_wrong_key_is_exit_1(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    runner.invoke(
        app,
        ["conformance", "--demo", "good", "--key", "secret", "--out", str(report), "--quiet"],
    )

    result = runner.invoke(app, ["conformance", "--verify", str(report), "--key", "wrong"])
    output = _plain(result.output)

    assert result.exit_code == 1, output
    assert "INVALID" in output


def test_verify_without_key_is_exit_2(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    runner.invoke(
        app,
        ["conformance", "--demo", "good", "--key", "secret", "--out", str(report), "--quiet"],
    )

    result = runner.invoke(app, ["conformance", "--verify", str(report)])
    output = _plain(result.output)

    assert result.exit_code == 2, output
    assert "required" in output


def test_export_trace_roundtrip(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"

    exported = runner.invoke(
        app, ["conformance", "--demo", "good", "--export-trace", str(trace), "--quiet"]
    )
    assert exported.exit_code == 0, _plain(exported.output)
    assert trace.is_file()

    rerun = runner.invoke(app, ["conformance", "--trace", str(trace), "--quiet"])
    assert rerun.exit_code == 0, _plain(rerun.output)


@pytest.mark.parametrize("module", ["maref.conformance", "maref.conformance.cli"])
def test_module_is_importable(module: str) -> None:
    import importlib

    assert importlib.import_module(module) is not None

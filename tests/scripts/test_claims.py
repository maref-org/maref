"""Claim ledger regression: the gate must fail closed on drift.

These tests exercise the ledger engine itself, not the project's claims.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "scripts" / "claims.py"


def _load_ledger():
    spec = importlib.util.spec_from_file_location("maref_claim_ledger", LEDGER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ledger = _load_ledger()


def _write_claims(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "claims.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_all_claims_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_claims(
        tmp_path,
        """
claims:
  - id: answer
    statement: fixed value
    command: [python3, -c, "print('42')"]
    expect: {equals: "42"}
""",
    )
    assert ledger.main(["--file", str(path), "--check"]) == 0
    assert "1 pass, 0 fail" in capsys.readouterr().out


def test_drift_exits_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_claims(
        tmp_path,
        """
claims:
  - id: answer
    statement: drifted value
    command: [python3, -c, "print('41')"]
    expect: {equals: "42"}
""",
    )
    assert ledger.main(["--file", str(path), "--check"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_same_as_resolves_order_independently(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_claims(
        tmp_path,
        """
claims:
  - id: left
    statement: left
    command: [python3, -c, "print('same')"]
    expect: {same_as: right}
  - id: right
    statement: right
    command: [python3, -c, "print('same')"]
    expect: {same_as: left}
""",
    )
    assert ledger.main(["--file", str(path), "--check"]) == 0
    assert "2 pass" in capsys.readouterr().out


def test_min_is_a_floor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_claims(
        tmp_path,
        """
claims:
  - id: count
    statement: count floor
    command: [python3, -c, "print('10')"]
    expect: {min: 9}
  - id: too_low
    statement: count below floor
    command: [python3, -c, "print('8')"]
    expect: {min: 9}
""",
    )
    assert ledger.main(["--file", str(path), "--check"]) == 1
    out = capsys.readouterr().out
    assert "count" in out and "PASS" in out
    assert "too_low" in out and "FAIL" in out


def test_missing_extract_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_claims(
        tmp_path,
        """
claims:
  - id: missing
    statement: no match
    command: [python3, -c, "print('abc')"]
    extract: "([0-9]+)"
    expect: {equals: "1"}
""",
    )
    assert ledger.main(["--file", str(path), "--check"]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_only_pulls_same_as_targets(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_claims(
        tmp_path,
        """
claims:
  - id: a
    statement: a
    command: [python3, -c, "print('x')"]
    expect: {equals: "x"}
  - id: b
    statement: b
    command: [python3, -c, "print('x')"]
    expect: {same_as: a}
""",
    )
    assert ledger.main(["--file", str(path), "--only", "b"]) == 0
    out = capsys.readouterr().out
    assert "a" in out and "b" in out


def test_repo_claims_are_green(capsys: pytest.CaptureFixture[str]) -> None:
    """The repository's own claims must hold in a clean checkout."""
    assert ledger.main(["--check"]) == 0, capsys.readouterr().out


def test_unknown_expect_key_fails_closed() -> None:
    """拼错的 expect 键必须 FAIL，不能静默通过（2026-11-24 审计）。
    
    expect={"equal": "1"} 中的 "equal" 是 "equals" 的拼写错误，
    不应被视为有效期望键，必须返回 FAIL 而非静默通过。
    """
    claim = ledger.Claim(
        id="test-unknown-key",
        statement="test",
        command=["echo", "1"],
        expect={"equal": "1"},  # 故意拼写错误，应视为未知键
        value="1",
    )
    result = ledger.evaluate([claim], 5)
    assert result[0].status == "FAIL", f"期望 status=FAIL 但得到 {result[0].status}: {result[0].detail}"

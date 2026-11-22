#!/usr/bin/env python3
"""Deterministic probes used by ``claims.yaml``.

Every probe prints exactly one machine-readable line.  The claim ledger
(``scripts/claims.py``) is the only consumer; humans should read
``docs/claims.md`` instead of parsing this output.

Design rules:
- no network access;
- deterministic (fixed keys, fixed fixtures);
- fail loud with a non-zero exit code instead of printing a guessed value.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

_VERSION_RE = r"([0-9]+\.[0-9]+\.[0-9]+)"


def _load_source(name: str, relative: str):
    """Load a stdlib-only module by path.

    ``import maref.governance.audit`` would execute the governance package
    ``__init__`` and pull the full dependency tree (structlog, pydantic, ...).
    The audit modules themselves are stdlib-only, so the probe loads them
    directly.  This keeps ``claims.py --check`` runnable in a clean CI job.
    """
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise SystemExit(f"probe: cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def readme_badge() -> str:
    """Version advertised by the shields.io badge in README.md."""
    match = re.search(rf"badge/version-v?{_VERSION_RE}-blue", _readme())
    if not match:
        raise SystemExit("probe readme_badge: badge not found")
    return match.group(1)


def readme_citation() -> str:
    """Version advertised by the BibTeX citation block in README.md."""
    match = re.search(rf"version\s*=\s*\{{{_VERSION_RE}\}}", _readme())
    if not match:
        raise SystemExit("probe readme_citation: citation version not found")
    return match.group(1)


def citation_version() -> str:
    """Version declared in CITATION.cff (a public-facing claim surface)."""
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"?([0-9]+\.[0-9]+\.[0-9]+)"?', text, re.MULTILINE)
    if not match:
        raise SystemExit("probe citation_version: version field not found")
    return match.group(1)


def _tracked_test_files() -> list[Path]:
    """tests/ 下的测试文件；优先取 git 索引，保证本地与 CI 数出同一个值。

    2026-11-22 事故：本地多了一个未跟踪的草稿测试文件，`tests.functions` 从
    16,400 变成 16,398，`--check-docs` 在 CI 上直接判红——声称账本被本地草稿污染。
    声称必须是"仓库里有什么"，不是"我这台机器上有什么"。
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", "tests"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return sorted((ROOT / "tests").rglob("test_*.py"))
    names = [p for p in out.decode("utf-8", "replace").split("\0") if p.endswith(".py")]
    return [ROOT / name for name in names if Path(name).name.startswith("test_")]


def count_tests() -> str:
    """Number of ``def test_*`` functions under tests/ (a floor, not pytest's count)."""
    total = 0
    for path in _tracked_test_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        total += len(re.findall(r"^\s*def (test_[A-Za-z0-9_]*)\s*\(", text, re.MULTILINE))
    return str(total)


def count_deps() -> str:
    """Number of direct runtime dependencies declared in pyproject.toml."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(len(data["project"]["dependencies"]))


def coverage_gate() -> str:
    """Coverage floor enforced by pytest-cov."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["tool"]["coverage"]["report"]["fail_under"])


def readme_tests_floor() -> str:
    """README 对外声明的测试数量下限（必须与 claims.yaml 的地板一致）。

    规则：README 只允许写"N,NNN+ test functions"这种**下限**表述，
    不接受"15,387 passing tests"这类绑定到某个旧 commit 的精确数——
    它一过期就变成不可复算的对外数字。
    """
    match = re.search(r"([0-9][0-9,]*)\+?\s*test functions", _readme())
    if not match:
        raise SystemExit("probe readme_tests_floor: 'N,NNN+ test functions' 未找到")
    return str(int(match.group(1).replace(",", "")))


def coverage_state() -> str:
    """STATE.yaml 记录的最近一次实测综合覆盖率（两位小数）。"""
    text = (ROOT / "STATE.yaml").read_text(encoding="utf-8")
    match = re.search(r"coverage\.py\s*综合\s*([0-9]+(?:\.[0-9]+)?)%", text)
    if not match:
        raise SystemExit("probe coverage_state: STATE.yaml 未记录 coverage.py 综合覆盖率")
    return f"{float(match.group(1)):.2f}"


def coverage_readme_badge() -> str:
    """README 健康表徽章的覆盖率（必须等于 STATE.yaml 的实测值）。

    同时拒绝把"~87% test coverage"这类无来源聚合数重新写回 README。
    """
    text = _readme()
    stale = re.search(r"~\s*[0-9]{1,3}\s*%\s*test coverage", text, re.IGNORECASE)
    if stale:
        raise SystemExit(f"probe coverage_readme_badge: 发现无来源聚合数 {stale.group(0)!r}")
    match = re.search(r"badge/coverage-([0-9]+(?:\.[0-9]+)?)", text)
    if not match:
        raise SystemExit("probe coverage_readme_badge: coverage 徽章未找到")
    return f"{float(match.group(1)):.2f}"


def _audit_fixture(directory: str, key: str) -> Path:
    audit = _load_source("_claim_audit", "src/maref/governance/audit.py")
    path = Path(directory) / "audit.jsonl"
    log = audit.AuditLogger(path, hmac_key=key)
    for index in range(3):
        log.log(
            event_type="policy_check",
            actor=f"agent-{index}",
            action="tool_call",
            layer="orchestration",
        )
    return path


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def formal_tlc_jobs() -> str:
    """CI 里**真正跑 TLC** 的任务数（不是仓库里 .tla 文件数）。"""
    return str(len(re.findall(r"tlc2\.TLC", _workflow("formal-verify.yml"))))


_SKIP_DIRS = {".git", ".venv", "node_modules", "dist", "build", "__pycache__"}


def _count_suffix(suffix: str) -> int:
    """仓库内（含 gray-code-fsm/ 与 src/formal/）某后缀的文件数，跳过构建目录。"""
    return sum(1 for path in ROOT.rglob(f"*{suffix}") if not _SKIP_DIRS & set(path.parts))


def formal_specs() -> str:
    return str(_count_suffix(".tla"))


def formal_cfg() -> str:
    return str(_count_suffix(".cfg"))


def conformance_controls() -> str:
    """conformance 套件的控制项条数（文本计数，避免导入 maref 运行时依赖）。"""
    text = (ROOT / "src" / "maref" / "conformance" / "controls.py").read_text(encoding="utf-8")
    return str(len(re.findall(r"^\s+Control\(", text, re.MULTILINE)))


def owasp_risks() -> str:
    text = (ROOT / "docs" / "security" / "owasp-agentic-top10-mapping.md").read_text(
        encoding="utf-8"
    )
    return str(len(re.findall(r"^## Risk \d+:", text, re.MULTILINE)))


def owasp_tla_specs() -> str:
    """README 与 mapping 文档的交叉一致性锚点（防 13 vs 4 这类漂移）。"""
    text = (ROOT / "docs" / "security" / "owasp-agentic-top10-mapping.md").read_text(
        encoding="utf-8"
    )
    match = re.search(r"TLA\+ formal specification\s*\|\s*[^|\n]*?(\d+)/10", text)
    if not match:
        raise SystemExit("mapping 文档缺少 'TLA+ formal specification | N/10' 行")
    return match.group(1)


def audit_tamper() -> str:
    """A modified payload must be reported as tampering, not silently accepted."""
    verify = _load_source("_claim_audit_verify", "src/maref/governance/audit_chain_verify.py")

    key = "claim-probe-tamper"
    with tempfile.TemporaryDirectory() as directory:
        path = _audit_fixture(directory, key)
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        rows[1]["action"] = "exfiltrate"
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        report = verify.verify_audit_chain(path, hmac_key=key)
    ok = not report.integrity_intact and len(report.hash_invalid) >= 1
    return "detected" if ok else "missed"


def audit_rotation() -> str:
    """A wrong/rotated key must not be reported as tampering."""
    verify = _load_source("_claim_audit_verify", "src/maref/governance/audit_chain_verify.py")

    key = "claim-probe-rotation"
    with tempfile.TemporaryDirectory() as directory:
        path = _audit_fixture(directory, key)
        report = verify.verify_audit_chain(path, hmac_key="a-different-key")
    ok = (
        report.integrity_intact
        and report.key_status == "rotated_or_wrong"
        and not report.signature_invalid
    )
    return "unverifiable" if ok else "mislabelled"


PROBES = {
    "readme_badge": readme_badge,
    "readme_citation": readme_citation,
    "citation_version": citation_version,
    "count_tests": count_tests,
    "count_deps": count_deps,
    "coverage_gate": coverage_gate,
    "readme_tests_floor": readme_tests_floor,
    "coverage_state": coverage_state,
    "coverage_readme_badge": coverage_readme_badge,
    "formal_tlc_jobs": formal_tlc_jobs,
    "formal_specs": formal_specs,
    "formal_cfg": formal_cfg,
    "conformance_controls": conformance_controls,
    "owasp_risks": owasp_risks,
    "owasp_tla_specs": owasp_tla_specs,
    "audit_tamper": audit_tamper,
    "audit_rotation": audit_rotation,
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in PROBES:
        print(f"usage: {Path(__file__).name} <{'|'.join(PROBES)}>", file=sys.stderr)
        return 2
    try:
        print(PROBES[argv[0]]())
    except SystemExit as exc:  # pragma: no cover - probe-config errors
        print(f"probe error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

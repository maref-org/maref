#!/usr/bin/env python3
"""Verify that **built artifacts** contain what the docs promise.

Why this exists (2026-11-21 review): the unit tests that claimed to check
"`[all]` is the union" and "the conformance suite is published" only read
`pyproject.toml` and the source tree. They would stay green even if the build
backend dropped the self-reference (making `[all]` empty) or excluded
`conformance/cli.py` from the wheel. This script inspects the wheel/sdist
themselves; CI runs it after `python -m build`.

Usage:
    python scripts/verify_artifacts.py --wheel dist/*.whl --sdist dist/*.tar.gz

Exit codes: 0 = all checks pass, 1 = contract violation, 2 = usage error.
"""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_BASE_DEPS = ("gmssl", "cryptography")
REQUIRED_WHEEL_FILES = (
    "maref/conformance/cli.py",
    "maref/conformance/runner.py",
    "maref/conformance/controls.py",
    "maref_lite/cli.py",
)
REQUIRED_SDIST_FILES = (
    "conformance/examples/good_trace.jsonl",
    "conformance/examples/bad_trace.jsonl",
    "conformance/SPEC.md",
    "scripts/conformance_run.py",
)
# 复盘实测：sdist 36.9MB，其中 28.2MB 是宣传 mp4。排除后应远低于此阈值。
MAX_SDIST_BYTES = 15 * 1024 * 1024

_EXTRA_RE = re.compile(r"""extra\s*==\s*['"]([^'"]+)['"]""")


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _norm(req: str) -> str:
    """Normalize a requirement for set comparison (names are case-insensitive)."""
    req = req.strip()
    match = re.match(r"([A-Za-z0-9_.\-]+)(.*)", req)
    if not match:
        return req.lower()
    return match.group(1).lower() + match.group(2).replace(" ", "")


def parse_requirements(lines: list[str]) -> dict[str | None, set[str]]:
    """Split ``Requires-Dist`` lines into {extra or None: {normalized requirement}}."""
    result: dict[str | None, set[str]] = {}
    for line in lines:
        if not line.startswith("Requires-Dist:"):
            continue
        spec = line.split(":", 1)[1].strip()
        requirement, _, marker = spec.partition(";")
        extra_match = _EXTRA_RE.search(marker)
        extra = extra_match.group(1) if extra_match else None
        result.setdefault(extra, set()).add(_norm(requirement))
    return result


def check_wheel(path: Path) -> list[str]:
    """Return a list of contract violations for one wheel."""
    problems: list[str] = []
    project = _pyproject()["project"]
    version = project["version"]
    declared_extras = set(project.get("optional-dependencies", {}))

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata_name = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        if metadata_name is None:
            return [f"{path.name}: 没有 METADATA（不是 wheel？）"]
        metadata = archive.read(metadata_name).decode("utf-8").splitlines()
        entry_points = next((n for n in names if n.endswith("entry_points.txt")), None)
        entry_text = archive.read(entry_points).decode("utf-8") if entry_points else ""

    for required in REQUIRED_WHEEL_FILES:
        if required not in names:
            problems.append(f"{path.name}: 缺少 {required}")

    if not re.search(r"^Version:\s*" + re.escape(version) + r"\s*$", "\n".join(metadata), re.M):
        problems.append(f"{path.name}: METADATA 版本不是 {version}")

    if not re.search(r"^maref\s*=\s*maref_lite\.cli:main\s*$", entry_text, re.M):
        problems.append(f"{path.name}: entry_points 缺少 `maref = maref_lite.cli:main`")

    requirements = parse_requirements(metadata)
    base = requirements.get(None, set())
    for dep in REQUIRED_BASE_DEPS:
        if not any(item.startswith(dep) for item in base):
            problems.append(f"{path.name}: base 依赖缺少 {dep}（装完 CLI 会起不来）")

    provides = {
        line.split(":", 1)[1].strip() for line in metadata if line.startswith("Provides-Extra:")
    }
    missing_extras = sorted(declared_extras - provides)
    if missing_extras:
        problems.append(f"{path.name}: 缺少 extra 声明 {missing_extras}")

    per_extra = {extra: reqs for extra, reqs in requirements.items() if extra is not None}
    all_extra = per_extra.get("all")
    if not all_extra:
        problems.append(
            f"{path.name}: `[all]` 在产物里是空的——构建后端没有展开自引用，"
            "`pip install maref[all]` 将不安装任何可选依赖"
        )
    else:
        union: set[str] = set()
        for extra, reqs in per_extra.items():
            if extra != "all":
                union |= reqs
        if all_extra != union:
            missing = sorted(union - all_extra)
            surplus = sorted(all_extra - union)
            problems.append(
                f"{path.name}: `[all]` 与各 extra 的并集不一致"
                f"（漏: {missing[:5]}；多: {surplus[:5]}）"
            )

    return problems


def check_sdist(path: Path) -> list[str]:
    """Return a list of contract violations for one sdist."""
    problems: list[str] = []
    size = path.stat().st_size
    if size > MAX_SDIST_BYTES:
        problems.append(
            f"{path.name}: {size / 1048576:.1f} MB 超过 {MAX_SDIST_BYTES / 1048576:.0f} MB "
            "（宣传视频不应进入 sdist）"
        )

    with tarfile.open(path, "r:gz") as archive:
        names = [member.name.split("/", 1)[-1] for member in archive.getmembers()]
        video_members = [n for n in names if n.startswith("website/public/videos/")]

    for required in REQUIRED_SDIST_FILES:
        if required not in names:
            problems.append(f"{path.name}: 缺少 {required}")

    if video_members:
        problems.append(
            f"{path.name}: 仍包含宣传视频 {video_members[:2]}（共 {len(video_members)} 个）"
        )

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify built MAREF artifacts")
    parser.add_argument("--wheel", action="append", default=[], help="wheel path (repeatable)")
    parser.add_argument("--sdist", action="append", default=[], help="sdist path (repeatable)")
    args = parser.parse_args(argv)

    if not args.wheel and not args.sdist:
        parser.print_usage(sys.stderr)
        return 2

    problems: list[str] = []
    for item in args.wheel:
        path = Path(item)
        if not path.is_file():
            problems.append(f"wheel 不存在: {item}")
            continue
        problems.extend(check_wheel(path))
    for item in args.sdist:
        path = Path(item)
        if not path.is_file():
            problems.append(f"sdist 不存在: {item}")
            continue
        problems.extend(check_sdist(path))

    if problems:
        print("ARTIFACT CONTRACT VIOLATED:", file=sys.stderr)
        for problem in problems:
            print(f"  ✗ {problem}", file=sys.stderr)
        return 1

    print(f"artifact contract OK ({len(args.wheel)} wheel / {len(args.sdist)} sdist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

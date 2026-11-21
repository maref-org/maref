"""产物契约校验器（scripts/verify_artifacts.py）的回归测试。

为什么需要它：2026-11-21 复盘发现，两个"看起来在测发布"的测试其实只读源码树——
`[all]` 即使被构建后端丢成空 extra、`conformance/cli.py` 即使没进 wheel，它们也会绿。
本文件用合成的 wheel/sdist 锁住校验器本身的判断逻辑；真实产物由 CI 构建后校验。
"""

from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_artifacts.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("maref_verify_artifacts", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


def _fake_project(tmp_path: Path, extras: dict[str, list[str]] | None = None) -> Path:
    extras = extras or {
        "a": ["alpha>=1"],
        "b": ["beta>=2"],
        "all": ["maref[a,b]"],
    }
    lines = [
        "[project]",
        'name = "maref"',
        'version = "1.2.3"',
        'dependencies = ["gmssl>=3.2.2", "cryptography>=42.0"]',
        "",
        "[project.optional-dependencies]",
    ]
    for name, deps in extras.items():
        rendered = ", ".join(f'"{dep}"' for dep in deps)
        lines.append(f"{name} = [{rendered}]")
    (tmp_path / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


def _make_wheel(tmp_path: Path, requires: list[str], extras: list[str]) -> Path:
    metadata = [
        "Metadata-Version: 2.1",
        "Name: maref",
        "Version: 1.2.3",
    ]
    metadata += [f"Provides-Extra: {extra}" for extra in extras]
    metadata += [f"Requires-Dist: {req}" for req in requires]
    wheel = tmp_path / "maref-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("maref-1.2.3.dist-info/METADATA", "\n".join(metadata) + "\n")
        archive.writestr(
            "maref-1.2.3.dist-info/entry_points.txt",
            "[console_scripts]\nmaref = maref_lite.cli:main\n",
        )
        for name in verifier.REQUIRED_WHEEL_FILES:
            archive.writestr(name, "")
    return wheel


def test_parse_requirements_splits_extras() -> None:
    parsed = verifier.parse_requirements(
        [
            "Metadata-Version: 2.1",
            "Requires-Dist: gmssl>=3.2.2",
            "Requires-Dist: alpha>=1; extra == 'a'",
            'Requires-Dist: beta>=2; extra == "all"',
        ]
    )

    assert parsed[None] == {"gmssl>=3.2.2"}
    assert parsed["a"] == {"alpha>=1"}
    assert parsed["all"] == {"beta>=2"}


def test_wheel_with_empty_all_extra_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(verifier, "ROOT", _fake_project(tmp_path))
    wheel = _make_wheel(
        tmp_path,
        requires=["gmssl>=3.2.2", "cryptography>=42.0"],
        extras=["a", "b", "all"],
    )

    problems = verifier.check_wheel(wheel)

    assert any("`[all]` 在产物里是空的" in problem for problem in problems), problems


def test_wheel_with_expanded_all_extra_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(verifier, "ROOT", _fake_project(tmp_path))
    wheel = _make_wheel(
        tmp_path,
        requires=[
            "gmssl>=3.2.2",
            "cryptography>=42.0",
            "alpha>=1; extra == 'a'",
            "beta>=2; extra == 'b'",
            "alpha>=1; extra == 'all'",
            "beta>=2; extra == 'all'",
        ],
        extras=["a", "b", "all"],
    )

    assert verifier.check_wheel(wheel) == []


def test_wheel_missing_conformance_cli_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(verifier, "ROOT", _fake_project(tmp_path))
    wheel = _make_wheel(
        tmp_path,
        requires=[
            "gmssl>=3.2.2",
            "cryptography>=42.0",
            "alpha>=1; extra == 'a'",
            "beta>=2; extra == 'b'",
            "alpha>=1; extra == 'all'",
            "beta>=2; extra == 'all'",
        ],
        extras=["a", "b", "all"],
    )
    # 重写一个不含 conformance/cli.py 的 wheel
    tmp_wheel = tmp_path / "broken.whl"
    with zipfile.ZipFile(wheel) as source, zipfile.ZipFile(tmp_wheel, "w") as target:
        for name in source.namelist():
            if name == "maref/conformance/cli.py":
                continue
            target.writestr(name, source.read(name))

    problems = verifier.check_wheel(tmp_wheel)

    assert any("conformance/cli.py" in problem for problem in problems)


def test_wheel_missing_base_crypto_dep_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(verifier, "ROOT", _fake_project(tmp_path))
    wheel = _make_wheel(
        tmp_path,
        requires=[
            "cryptography>=42.0",
            "alpha>=1; extra == 'a'",
            "beta>=2; extra == 'b'",
            "alpha>=1; extra == 'all'",
            "beta>=2; extra == 'all'",
        ],
        extras=["a", "b", "all"],
    )

    problems = verifier.check_wheel(wheel)

    assert any("缺少 gmssl" in problem for problem in problems), problems


def _make_sdist(tmp_path: Path, with_video: bool) -> Path:
    path = tmp_path / "maref-1.2.3.tar.gz"
    files = dict.fromkeys(verifier.REQUIRED_SDIST_FILES, b"")
    if with_video:
        files["website/public/videos/demo.mp4"] = b"x" * 1024
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in files.items():
            info = tarfile.TarInfo(f"maref-1.2.3/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return path


def test_sdist_with_video_is_rejected(tmp_path: Path) -> None:
    problems = verifier.check_sdist(_make_sdist(tmp_path, with_video=True))

    assert any("宣传视频" in problem for problem in problems), problems


def test_sdist_without_video_passes(tmp_path: Path) -> None:
    assert verifier.check_sdist(_make_sdist(tmp_path, with_video=False)) == []

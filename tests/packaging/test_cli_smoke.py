"""发布面冒烟测试：CLI 必须能启动，版本必须只有一个源头。

回归背景（2026-11-21 实测）：
1. `pip install maref==0.55.2` 后 `maref --version` 直接 ImportError（gmssl 只在 [identity]，
   而 maref.crypto 在包导入时就无条件加载 SM2）——安装完成 ≠ 可运行。
2. `maref --version` 打印 0.55.0，而包/README/STATE 都是 0.55.2（第五处版本串，无人覆盖）。
3. 公开仓曾有空的 `src/maref/conformance/` 目录：`import maref.conformance` 会因
   namespace package 而"成功"，但里面什么都没有——假通过比失败更危险。
"""

from __future__ import annotations

import re
from pathlib import Path

import tomllib
from typer.testing import CliRunner

import maref

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _plain(text: str) -> str:
    """去掉 rich 的 ANSI 样式，避免版本号被加粗打断。"""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_cli_version_exits_zero() -> None:
    """README 的第一条命令必须能跑：退出码 0，且不出现模块导入错误。"""
    from maref_lite.cli import app

    result = CliRunner().invoke(app, ["--version"])
    output = _plain(result.output)

    assert result.exit_code == 0, output
    assert "ModuleNotFoundError" not in output
    assert "ImportError" not in output
    assert maref.__version__ in output, output


def test_version_is_single_sourced() -> None:
    """pyproject / maref / maref_lite / README 徽章 必须是同一个版本。"""
    declared = _pyproject()["project"]["version"]

    from maref_lite import __version__ as lite_version

    assert maref.__version__ == declared, "maref.__version__ 与 pyproject 漂移"
    assert lite_version == declared, "maref_lite.__version__ 与 pyproject 漂移"

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    badges = set(re.findall(r"badge/version-v?(\d+\.\d+\.\d+)", readme))
    assert badges == {declared}, f"README 版本徽章漂移: {badges} != {declared}"


def test_runtime_crypto_dependencies_are_in_base() -> None:
    """gmssl / cryptography 是导入期或运行时硬依赖，必须在 base dependencies 里。"""
    deps = _pyproject()["project"]["dependencies"]
    missing = [
        name for name in ("gmssl", "cryptography") if not any(d.startswith(name) for d in deps)
    ]
    assert missing == [], (
        f"缺少 base 依赖 {missing}：maref.crypto 在包导入期加载 SM2/SM3/SM4（gmssl），"
        "审计链 Ed25519 与 a2a_secure_transport 用 cryptography；"
        "缺失会让 `pip install maref` 产出一个起不来的 CLI"
    )


def test_all_extra_declares_every_extra() -> None:
    """源码树口径：`[all]` 的声明必须覆盖所有 extra。

    注意：这只证明 pyproject 的**意图**。构建后端是否真的把自引用展开进
    wheel 元数据，由 `scripts/verify_artifacts.py` 在 CI 构建产物后检查——
    源码树测试无法发现"声明了但产物里是空 extra"这类回归。
    """
    extras = _pyproject()["project"]["optional-dependencies"]
    match = re.search(r"maref\[([^\]]+)\]", " ".join(extras["all"]))
    assert match, "'all' extra 未声明任何引用"
    declared = {name.strip() for name in match.group(1).split(",")}

    missing = sorted(set(extras) - {"all"} - declared)
    assert missing == [], f"'all' 不是并集，缺少: {missing}"


def test_conformance_suite_files_exist_in_repo() -> None:
    """仓库口径：conformance 不是空 namespace，且在 repo 内可跑。

    "已发布"由 `scripts/verify_artifacts.py` 对 wheel 断言
    （`maref/conformance/cli.py` 必须在 wheel 内）；本测试只守仓库内容。
    """
    import maref.conformance

    assert maref.conformance.__file__ is not None, "conformance 是空的 namespace package"
    assert (REPO_ROOT / "conformance" / "SPEC.md").is_file()
    assert (REPO_ROOT / "scripts" / "conformance_run.py").is_file()

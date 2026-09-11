"""B2 修复：递归深度环境变量覆盖 — 独立文件避免 importlib.reload 导致 Enum 比较失败。

test_r5_meta.py 中的原测试使用 importlib.reload() 修改 _MAX_RECURSION_DEPTH，
但 reload 会重新创建 Enum 类，导致同模块后续测试的 MetaBreakerState 比较失败。
此文件使用单独的子进程隔离测试环境变量效果。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_env_override_increases_max_depth() -> None:
    """MAREF_MAX_RECURSION_DEPTH=5 增加递归深度上限。"""
    src_dir = str(Path(__file__).parents[2] / "src")
    code = (
        "import os\n"
        "os.environ['MAREF_MAX_RECURSION_DEPTH'] = '5'\n"
        "import importlib\n"
        "import maref.recursive.meta_governance as mg\n"
        "importlib.reload(mg)\n"
        "print(mg._MAX_RECURSION_DEPTH)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": src_dir, "MAREF_MAX_RECURSION_DEPTH": "5"},
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    output = result.stdout.strip()
    assert output == "5", f"预期 5 实际 {output}"


def test_env_override_accepts_depth_4() -> None:
    """MAREF_MAX_RECURSION_DEPTH=5 允许 depth=4。"""
    src_dir = str(Path(__file__).parents[2] / "src")
    code = (
        "import os\n"
        "os.environ['MAREF_MAX_RECURSION_DEPTH'] = '5'\n"
        "import importlib\n"
        "import maref.recursive.meta_governance as mg\n"
        "importlib.reload(mg)\n"
        "g = mg.MetaGovernance(depth=4)\n"
        "print(g.depth)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": src_dir, "MAREF_MAX_RECURSION_DEPTH": "5"},
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    output = result.stdout.strip()
    assert output == "4", f"预期 4 实际 {output}"


def test_env_override_rejects_depth_6() -> None:
    """MAREF_MAX_RECURSION_DEPTH=5 拒绝 depth=6（超出限制）。"""
    src_dir = str(Path(__file__).parents[2] / "src")
    code = (
        "import os\n"
        "os.environ['MAREF_MAX_RECURSION_DEPTH'] = '5'\n"
        "import importlib\n"
        "import maref.recursive.meta_governance as mg\n"
        "importlib.reload(mg)\n"
        "try:\n"
        "    mg.MetaGovernance(depth=6)\n"
        "    print('NO_ERROR')\n"
        "except mg.RecursionDepthExceededError:\n"
        "    print('EXPECTED_ERROR')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": src_dir, "MAREF_MAX_RECURSION_DEPTH": "5"},
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "EXPECTED_ERROR" in result.stdout, f"预期错误未抛出: {result.stdout}"

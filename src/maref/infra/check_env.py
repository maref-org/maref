#!/usr/bin/env python3
"""
Environment Checker — validate runtime assumptions before any daemon starts.

Checks:
  1. Volume mount — external drive is mounted and accessible
  2. Python imports — critical modules can be imported
  3. Command availability — required CLI tools exist
  4. sys.path — src/ is on the module search path
  5. Credentials — .env and/or Keychain token accessible
  6. Platform assumptions — ps column format, shell behavior

Usage:
    from maref.infra.check_env import check_environment, EnvResult

    result = check_environment()
    if not result.ok:
        print(result.summary())
        sys.exit(78)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


class EnvResult:
    """Result of environment checks."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self._ok = True

    def add_check(self, name: str, passed: bool, message: str = "") -> None:
        self.checks.append({"name": name, "passed": passed, "message": message})
        if not passed:
            self._ok = False

    @property
    def ok(self) -> bool:
        return self._ok

    @property
    def failures(self) -> list[dict[str, Any]]:
        return [c for c in self.checks if not c["passed"]]

    def summary(self) -> str:
        lines: list[str] = []
        lines.append(f"环境检查: {'✅ 全部通过' if self.ok else '❌ 存在失败'}")
        lines.append("")
        for c in self.checks:
            icon = "✅" if c["passed"] else "❌"
            msg = f"  {icon} {c['name']}"
            if c["message"]:
                msg += f": {c['message']}"
            lines.append(msg)
        if self.failures:
            lines.append("")
            lines.append("请修复上述问题后重试")
        return "\n".join(lines)

    def exit_if_fail(self, exit_code: int = 78) -> None:
        if not self.ok:
            print(self.summary(), file=sys.stderr)
            sys.exit(exit_code)


def _check_volume(path: str | Path) -> tuple[bool, str]:
    """Check if a path is mounted and accessible."""
    p = Path(path)
    if not p.exists():
        return False, f"路径不存在: {p}"
    try:
        next(p.iterdir(), None)
        return True, ""
    except PermissionError:
        return False, f"无权限访问: {p}"
    except OSError as e:
        return False, f"IO 错误: {e}"


def _check_commands(names: list[str]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    for name in names:
        path = shutil.which(name)
        if path:
            results.append((name, True, path))
        else:
            results.append((name, False, "未找到"))
    return results


def _check_ps_format() -> tuple[bool, str]:
    """Verify ps output format on macOS."""
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,ppid,user,state,command"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False, f"ps 命令返回非零: {result.stderr.strip()}"
        lines = result.stdout.strip().splitlines()
        if len(lines) < 2:
            return False, "ps 输出为空"
        header = lines[0]
        for col in ["PID", "PPID", "USER", "STAT"]:
            if col not in header:
                return False, f"ps 输出缺少列 '{col}': {header}"
        for data_line in lines[1:]:
            parts = data_line.split(None, 4)
            if len(parts) >= 5:
                break
        else:
            return False, "ps 输出没有可解析的数据行"
        return True, ""
    except FileNotFoundError:
        return False, "ps 命令不存在"
    except subprocess.TimeoutExpired:
        return False, "ps 命令超时"
    except Exception as e:
        return False, f"ps 检查异常: {e}"


def _check_python_imports(module_names: list[str]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    for name in module_names:
        try:
            __import__(name)
            results.append((name, True, ""))
        except ImportError as e:
            results.append((name, False, str(e)))
    return results


def _check_sys_path(expected_substring: str = "src") -> tuple[bool, str]:
    for p in sys.path:
        if expected_substring in p:
            return True, ""
    return False, f"sys.path 中没有包含 '{expected_substring}' 的路径: {sys.path}"


def _check_git_repo(path: Path) -> tuple[bool, str]:
    git_dir = path / ".git"
    if git_dir.is_dir():
        return True, ""
    return False, f"不是 git 仓库: {path}"


def check_environment(
    project_root: str | Path | None = None,
    extra_checks: list[tuple[str, Callable[[], tuple[bool, str]]]] | None = None,
) -> EnvResult:
    """Run all environment checks."""
    result = EnvResult()
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent.parent
    project_root = Path(project_root)

    # 1. Platform
    system = platform.system()
    result.add_check("操作系统", system == "Darwin", f"当前: {system}, 期望: Darwin (macOS)")

    # 2. Volume mount
    vol_ok, vol_msg = _check_volume(project_root)
    result.add_check("项目卷挂载", vol_ok, vol_msg)

    # 3. sys.path
    sp_ok, sp_msg = _check_sys_path("src")
    result.add_check("sys.path 包含 src", sp_ok, sp_msg)

    # 4. Standard library imports
    stdlib_check = _check_python_imports(["json", "sqlite3", "logging", "pathlib"])
    all_stdlib_ok = all(r[1] for r in stdlib_check)
    failed_stdlib = [r[0] for r in stdlib_check if not r[1]]
    result.add_check("标准库导入", all_stdlib_ok, f"失败: {failed_stdlib}" if failed_stdlib else "")

    # 5. CLI commands
    for name, found, path in _check_commands(["git", "ps", "bash", "python3"]):
        result.add_check(f"命令: {name}", found, f"路径: {path}" if found else path)
    for name, found, _path in _check_commands(["security", "msmtp", "launchctl"]):
        if not found:
            result.add_check(f"命令: {name} (可选)", True, "未找到 (将跳过相关功能)")

    # 6. ps format
    ps_ok, ps_msg = _check_ps_format()
    result.add_check("ps 输出格式 (macOS)", ps_ok, ps_msg)

    # 7. Git repo
    git_ok, git_msg = _check_git_repo(project_root)
    result.add_check("Git 仓库", git_ok, git_msg)

    # 8. .env
    dotenv = project_root / ".env"
    if dotenv.exists():
        try:
            dotenv.read_bytes()
            result.add_check(".env 文件", True)
        except (OSError, PermissionError) as e:
            result.add_check(".env 文件", False, str(e))
    else:
        result.add_check(".env 文件", True, "不存在 (可能仅使用 Keychain)")

    # 9. Keychain token
    try:
        kr = subprocess.run(
            ["security", "find-generic-password", "-w", "-a", os.environ.get("USER", ""),
             "-s", "env/GITHUB_TOKEN"],
            capture_output=True, text=True, timeout=10,
        )
        if kr.returncode == 0 and kr.stdout.strip():
            result.add_check("Keychain GITHUB_TOKEN", True)
        else:
            result.add_check("Keychain GITHUB_TOKEN", True, "未找到 (可能仅在 .env 中)")
    except FileNotFoundError:
        result.add_check("Keychain GITHUB_TOKEN", True, "security 命令不可用")
    except Exception as e:
        result.add_check("Keychain GITHUB_TOKEN", True, f"检查异常: {e}")

    # 10. Python version
    py_version = sys.version_info
    py_ok = py_version >= (3, 10)
    result.add_check("Python 版本 ≥ 3.10", py_ok, f"当前: {sys.version.split()[0]}")

    # Extra checks
    if extra_checks:
        for name, check_fn in extra_checks:
            try:
                ok, msg = check_fn()
                result.add_check(name, ok, msg)
            except Exception as e:
                result.add_check(name, False, str(e))

    return result


def require_env() -> EnvResult:
    """Convenience: run all checks and exit on failure."""
    result = check_environment()
    result.exit_if_fail()
    return result


if __name__ == "__main__":
    result = check_environment()
    print(result.summary())
    sys.exit(0 if result.ok else 78)

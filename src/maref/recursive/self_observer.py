from __future__ import annotations

import ast
import re
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.observation.probes import (
    EntropyProbe,
    ProbeReading,
)


@dataclass
class SystemSnapshot:
    timestamp: float = field(default_factory=time.time)
    module_graph: dict[str, list[str]] = field(default_factory=dict)
    test_stats: dict[str, int] = field(default_factory=dict)
    git_stats: dict[str, Any] = field(default_factory=dict)
    state_machine_status: dict[str, Any] = field(default_factory=dict)
    probe_readings: list[ProbeReading] = field(default_factory=list)
    source_file_count: int = 0
    total_lines: int = 0


class SelfObserver:
    def __init__(self, root_path: str | Path | None = None) -> None:
        if root_path is None:
            root_path = Path(__file__).resolve().parent.parent.parent.parent
        self._root = Path(root_path)

    def observe_codebase(self, root_path: str | None = None) -> dict[str, list[str]]:
        src = self._root / "src" if root_path is None else Path(root_path)
        module_graph: dict[str, list[str]] = {}
        self._source_file_count = 0
        self._total_lines = 0

        for py_file in src.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            rel = str(py_file.relative_to(self._root)).replace("/", ".").replace(".py", "")
            module_graph[rel] = []
            try:
                with open(py_file) as f:
                    content = f.read()
                self._total_lines += len(content.splitlines())
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            module_graph[rel].append(alias.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        module_graph[rel].append(node.module.split(".")[0])
                self._source_file_count += 1
            except (OSError, SyntaxError, UnicodeDecodeError):
                pass

        return module_graph

    def observe_tests(self, collect_only: bool = False) -> dict[str, int]:
        """观察测试状态。

        Args:
            collect_only: True 时仅收集不运行（快速但无 pass/fail 信号）；
                          False 时实际运行测试（默认，提供真实失败信号）。
        """
        t0 = time.monotonic()
        cmd = ["python3", "-m", "pytest", "tests/", "-q", "--no-header"]
        if collect_only:
            cmd.append("--co")
        # 实际运行测试需要更长超时（与巡检间隔 300s 匹配）
        timeout = 60 if collect_only else 300
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired as e:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            output = (e.stdout or "") + (e.stderr or "") if isinstance(e.stdout, str) else ""
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "coverage_pct": 0,
                "duration_ms": elapsed_ms,
                "timeout": True,
            }

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        stats: dict[str, int] = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "coverage_pct": 0,
            "duration_ms": elapsed_ms,
        }

        if collect_only:
            # collect-only 模式：从 "X tests collected" 提取 total
            collected_match = re.search(r"(\d+)\s+tests?\s+collected", output)
            if collected_match:
                stats["total"] = int(collected_match.group(1))
        else:
            # 实际运行模式：从总结行提取 passed/failed/errors
            # 格式: "5659 passed, 10 errors in 19.47s"
            # 或: "3 failed, 5656 passed, 10 errors in 19.47s"
            passed_match = re.search(r"(\d+)\s+passed", output)
            failed_match = re.search(r"(\d+)\s+failed", output)
            errors_match = re.search(r"(\d+)\s+errors?", output)
            collected_match = re.search(r"(\d+)\s+tests?\s+collected", output)

            if passed_match:
                stats["passed"] = int(passed_match.group(1))
            if failed_match:
                stats["failed"] = int(failed_match.group(1))
            if errors_match:
                stats["errors"] = int(errors_match.group(1))
            if collected_match:
                stats["total"] = int(collected_match.group(1))
            else:
                # 无 "collected" 行时，total = passed + failed + errors
                stats["total"] = stats["passed"] + stats["failed"] + stats["errors"]

        return stats

    def observe_git(self) -> dict[str, Any]:
        git_stats: dict[str, Any] = {"commits_30d": 0, "tags": [], "hot_files": []}

        tags_result = subprocess.run(
            ["git", "tag", "--sort=-creatordate"],
            cwd=str(self._root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if tags_result.returncode == 0:
            git_stats["tags"] = [
                t.strip() for t in tags_result.stdout.strip().split("\n") if t.strip()
            ]

        commit_count_result = subprocess.run(
            ["git", "rev-list", "--count", "--since=30.days", "HEAD"],
            cwd=str(self._root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if commit_count_result.returncode == 0 and commit_count_result.stdout.strip():
            git_stats["commits_30d"] = int(commit_count_result.stdout.strip())

        hot_files_result = subprocess.run(
            ["git", "log", "--format=", "--name-only", "-n", "50"],
            cwd=str(self._root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if hot_files_result.returncode == 0:
            file_counts: dict[str, int] = defaultdict(int)
            for line in hot_files_result.stdout.strip().split("\n"):
                line = line.strip()
                if line and line.endswith(".py"):
                    file_counts[line] += 1
            git_stats["hot_files"] = sorted(
                file_counts, key=lambda x: file_counts[x], reverse=True
            )[:5]

        return git_stats

    def _build_state_machine_status(self) -> dict[str, Any]:
        try:
            from maref.governance.state_machine import GovernanceStateMachine

            sm = GovernanceStateMachine()
            return {
                "current_state": str(sm.current_state),
                "entropy": sm.get_entropy_trend(),
                "transition_count": sm.transition_count,
            }
        except Exception:
            return {"error": "failed_to_create_state_machine"}

    def snapshot(self) -> SystemSnapshot:
        module_graph = self.observe_codebase()
        test_stats = self.observe_tests()
        git_stats = self.observe_git()
        state_machine_status = self._build_state_machine_status()

        entropy_probe = EntropyProbe(primary_threshold=3.0, shadow_threshold=1.5)
        failed = test_stats.get("failed", 0)
        total = max(test_stats.get("total", 1), 1)
        readings = entropy_probe.read(entropy=failed / total * 10.0)

        return SystemSnapshot(
            timestamp=time.time(),
            module_graph=module_graph,
            test_stats=test_stats,
            git_stats=git_stats,
            state_machine_status=state_machine_status,
            probe_readings=readings,
            source_file_count=getattr(self, "_source_file_count", 0),
            total_lines=getattr(self, "_total_lines", 0),
        )

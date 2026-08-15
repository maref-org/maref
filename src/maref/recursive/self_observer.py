from __future__ import annotations

import ast
import re
import subprocess
import sys
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
    test_pass_rate: float = 0.0
    coverage_pct: float = 0.0
    test_count: int = 0


class SelfObserver:
    # Fast benchmark subset — 10 curated test files that complete in <30s each,
    # keeping the aggregate runtime well under the 60s latency threshold.
    # Used as the default when ``collect_only=False`` to avoid the 300s full
    # suite latency that triggers system health HALTs (streak >= 3).
    _FAST_TEST_FILES: list[str] = [
        "tests/recursive/test_r12_audit.py",
        "tests/recursive/test_r14_r17.py",
        "tests/recursive/test_r7_kg.py",
        "tests/recursive/test_r36_signed_agent_cards.py",
        "tests/recursive/test_r47_orchestration_perf.py",
        "tests/recursive/test_r80_hitl_v2.py",
        "tests/recursive/test_self_optimizer.py",
        "tests/recursive/test_self_diagnostician.py",
        "tests/recursive/test_skill_schema.py",
        "tests/recursive/test_r61_skill_schema_loader.py",
    ]

    def __init__(
        self,
        root_path: str | Path | None = None,
        test_paths: list[str] | None = None,
    ) -> None:
        if root_path is None:
            root_path = Path(__file__).resolve().parent.parent.parent.parent
        self._root = Path(root_path)
        # Default to fast subset so metrics/diagnosis stay under 30s.
        # Callers can override via ``snapshot(test_paths=…)`` for a full scan.
        self._test_paths = test_paths or list(self._FAST_TEST_FILES)

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

    def observe_tests(
        self,
        collect_only: bool = False,
        test_paths: list[str] | None = None,
    ) -> dict[str, int]:
        """观察测试状态。

        Args:
            collect_only: True 时仅收集不运行（快速但无 pass/fail 信号）；
                          False 时实际运行测试（默认，提供真实失败信号）。
            test_paths: 要运行的测试路径列表。默认为 ``self._test_paths``
                        （即快速基准子集 10 个文件）以控制延迟在 30s 以内。
        """
        t0 = time.monotonic()
        paths = test_paths if test_paths is not None else self._test_paths
        # Collect-only mode: scan all of ``tests/`` for an accurate total
        # count (fast since --co only collects, doesn't execute).
        if collect_only and test_paths is None:
            paths = ["tests/"]
        # Fix 10: use sys.executable instead of "python3" — the latter
        # resolves to /usr/bin/python3 (system Python) which has no pytest
        # installed, causing observe_tests to silently return total=0.
        cmd = [sys.executable, "-m", "pytest"] + paths + ["-q", "--no-header", "--no-cov"]
        # Fix 10: a single collection error (e.g. duplicate test module name
        # across tests/execution and tests/executor) interrupts the whole
        # run and reports total=1 errors=1. Continue so we still get real
        # pass/fail counts for the rest of the suite.
        cmd.append("--continue-on-collection-errors")
        if collect_only:
            cmd.append("--co")
        else:
            # Fix 10: exclude slow integration/chaos/benchmark tests so the
            # metrics phase stays within the 15-min cycle budget (matches CI).
            cmd.extend(["-m", "not integration and not chaos and not benchmark"])
        # Timeout: fast subset (10 files) completes in <30s; with overhead,
        # 60s is a safe bound for collect-only. Run mode (full filtered suite)
        # needs 600s (Fix 10b) — the old 300s caused 48h cycle-1 to report
        # test_count=0 because the ~10k-test suite exceeded it.
        # 60s → 120s (Fix 10c): CI 冷启动收集整个 tests/ 实测 ~45s (本地无缓存，
        # 带 --cov 更慢)，并行 runner 下可能超 60s。内层 --no-cov 减负后更低。
        timeout = 120 if collect_only else 600
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

    def snapshot(self, collect_only: bool = False) -> SystemSnapshot:
        module_graph = self.observe_codebase()
        test_stats = self.observe_tests(collect_only=collect_only)
        git_stats = self.observe_git()
        state_machine_status = self._build_state_machine_status()

        entropy_probe = EntropyProbe(primary_threshold=3.0, shadow_threshold=1.5)
        failed = test_stats.get("failed", 0)
        total = max(test_stats.get("total", 1), 1)
        readings = entropy_probe.read(entropy=failed / total * 10.0)

        total_count = test_stats.get("total", 0)
        passed_count = test_stats.get("passed", 0)
        test_pass_rate = passed_count / total_count if total_count > 0 else 0.0
        coverage_pct = float(test_stats.get("coverage_pct", 0.0))

        return SystemSnapshot(
            timestamp=time.time(),
            module_graph=module_graph,
            test_stats=test_stats,
            git_stats=git_stats,
            state_machine_status=state_machine_status,
            probe_readings=readings,
            source_file_count=getattr(self, "_source_file_count", 0),
            total_lines=getattr(self, "_total_lines", 0),
            test_pass_rate=test_pass_rate,
            coverage_pct=coverage_pct,
            test_count=total_count,
        )

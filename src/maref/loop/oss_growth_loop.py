"""OSSGrowthLoop — 开源仓库增长治理循环。

将 MAREF 开源仓库的"发布即分发"升级为受 GovernedLoop 治理的自动化：

  check release → distribute channels → verify reachable → completeness gate
      ↓ 未达标 → 循环继续（补发/重试）
      ↓ 达标   → 审计签收 → 增长记录

与 GitHubAgentLoop 的区别:
  - GitHubAgentLoop 治理 CI/CD workflow 运行（技术循环）
  - OSSGrowthLoop 治理开源增长分发（增长循环）——验证目标从
    "workflow 跑完"换成"分发成功 + 链接可达 + star 增量"。

依赖:
  - gh CLI (GitHub CLI)
  - scripts/browser_publish.py（Dev.to/Twitter 等分发，复用 AGENTS.md 工具链）
  - scripts/preflight_posting_check.py（链接可达性验证）
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maref.loop.governed import GovernedLoop
from maref.loop.halting import AnyOf, CompletenessGate, HaltingCondition
from maref.loop.state import LoopConfig
from maref.loop.verification import CompletenessVerifier, VerificationCriterion, VerificationSpec

logger = logging.getLogger("maref.loop.oss_growth_loop")

# 渠道类型 → 分发脚本映射（复用 AGENTS.md 工具链，禁止手写替代发布器）
CHANNEL_SCRIPT = {
    "devto": "browser_publish.py",
    "twitter": "browser_publish.py",
    "bilibili": "browser_publish.py",
    "xiaohongshu": "phone_publish.py",
}


# ── 数据模型 ───────────────────────────────────────────────────────


@dataclass
class OSSGrowthTaskSpec:
    """开源增长任务定义。

    Attributes:
        repo:            仓库全名 (e.g. "maref-org/maref")
        release_tag:     要分发的 release tag（None 则取最新 release）
        channels:        目标分发渠道 ["devto", "twitter", "bilibili", "xiaohongshu"]
        target_star_growth: 本轮目标 star 增量（应记，不阻塞）
        timeout_minutes: 循环总超时（分钟）
    """

    repo: str
    release_tag: str | None = None
    channels: list[str] = field(default_factory=list)
    target_star_growth: int = 100
    timeout_minutes: int = 30

    def display_name(self) -> str:
        tag = self.release_tag or "latest"
        return f"{self.repo}@{tag}"


# ── 配置 ───────────────────────────────────────────────────────────


@dataclass
class OSSGrowthLoopConfig:
    """增长循环运行配置。"""

    max_iterations: int = 5
    poll_interval_seconds: float = 30.0
    timeout_seconds: float = 1800.0
    enable_audit: bool = True

    def to_loop_config(self, name: str = "oss_growth") -> LoopConfig:
        conditions: list[HaltingCondition] = [CompletenessGate()]
        if self.max_iterations:
            from maref.loop.halting import MaxIterations

            conditions.append(MaxIterations(self.max_iterations))
        if self.timeout_seconds:
            from maref.loop.policy import GracefulTimeout

            conditions.append(GracefulTimeout(self.timeout_seconds))
        return LoopConfig(
            check_interval_seconds=self.poll_interval_seconds,
            halting_condition=AnyOf(*conditions),
            max_errors=3,
            enable_audit=self.enable_audit,
            name=name,
        )


# ── OSS Growth Loop ────────────────────────────────────────────────


class OSSGrowthLoop(GovernedLoop):
    """开源仓库增长治理循环。

    每周期（_run_governed_cycle）:
      1. 检查目标 release 已发布
      2. 分发到各渠道（复用 scripts/ 分发脚本）
      3. 验证各渠道发布成功 + 链接可达
      4. 完整度审计 + CompletenessGate 决策
    """

    def __init__(
        self,
        task: OSSGrowthTaskSpec,
        config: OSSGrowthLoopConfig | None = None,
        governance: Any = None,
    ) -> None:
        self._task = task
        self._cl_config = config or OSSGrowthLoopConfig()

        self._verifier = CompletenessVerifier()
        self._spec = self._build_verification_spec()

        # 运行状态
        self._release_tag: str | None = task.release_tag
        self._release_url: str = ""
        self._distribution: dict[str, dict[str, Any]] = {}  # channel -> {ok, url, error}
        self._cycle_results: list[dict[str, Any]] = []
        self._last_report: dict[str, Any] | None = None
        self._base_stars: int | None = None

        # 审计
        self._audit_bridge: Any = None
        try:
            from maref.loop.code_agent_loop import _AuditBridge

            self._audit_bridge = _AuditBridge()
        except Exception:
            logger.debug("_AuditBridge not available (code_agent_loop not loaded)")

        loop_config = self._cl_config.to_loop_config(name=f"oss_{task.repo.replace('/', '_')}")
        super().__init__(loop_config=loop_config, governance=governance)

    # ── 公共属性 ──────────────────────────────────────────────────

    @property
    def task(self) -> OSSGrowthTaskSpec:
        return self._task

    @property
    def release_tag(self) -> str | None:
        return self._release_tag

    @property
    def release_url(self) -> str:
        return self._release_url

    @property
    def distribution(self) -> dict[str, dict[str, Any]]:
        return dict(self._distribution)

    @property
    def cycle_results(self) -> list[dict[str, Any]]:
        return list(self._cycle_results)

    # ── 验证规格 ──────────────────────────────────────────────────

    def _build_verification_spec(self) -> VerificationSpec:
        spec = VerificationSpec()

        # Release 必须已发布
        spec.add(VerificationCriterion(
            criterion_id="release_published",
            description=f"release 已发布 ({self._task.display_name()})",
            severity="must",
            check_fn=self._check_release_published,
        ))

        # 各渠道分发必须成功
        if self._task.channels:
            spec.add(VerificationCriterion(
                criterion_id="channels_distributed",
                description=f"分发到 {len(self._task.channels)} 个渠道",
                severity="must",
                check_fn=self._check_channels_distributed,
            ))

        # 分发链接可达（复用 preflight_posting_check 思路）
        spec.add(VerificationCriterion(
            criterion_id="links_reachable",
            description="分发链接可访问",
            severity="should",
            check_fn=self._check_links_reachable,
        ))

        return spec

    # ── gh 封装 ───────────────────────────────────────────────────

    def _query_latest_release(self) -> dict[str, Any] | None:
        """查询最新 release，失败返回 None。"""
        try:
            if self._task.release_tag:
                cmd = ["gh", "release", "view", self._task.release_tag,
                       "--repo", self._task.repo,
                       "--json", "tagName,url,name,publishedAt"]
            else:
                cmd = ["gh", "release", "view", "--repo", self._task.repo,
                       "--json", "tagName,url,name,publishedAt"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.warning("gh release view failed: %s", result.stderr[:200])
                return None
            return json.loads(result.stdout)
        except Exception as exc:
            logger.warning("gh release view exception: %s", exc)
            return None

    def _query_stars(self) -> int | None:
        """查询仓库 star 数。"""
        try:
            result = subprocess.run(
                ["gh", "repo", "view", self._task.repo,
                 "--json", "stargazerCount"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            return int(data.get("stargazerCount", 0))
        except Exception:
            return None

    # ── 验证检查 ──────────────────────────────────────────────────

    def _check_release_published(self, _unused: Path) -> tuple[bool, str]:
        data = self._query_latest_release()
        if data is None:
            return False, "release_not_found"
        self._release_tag = data.get("tagName", self._release_tag)
        self._release_url = data.get("url", "")
        return True, f"release_{self._release_tag}"

    def _check_channels_distributed(self, _unused: Path) -> tuple[bool, str]:
        """分发到各渠道，复用 scripts/ 分发脚本。"""
        failed: list[str] = []
        for channel in self._task.channels:
            if channel in self._distribution and self._distribution[channel].get("ok"):
                continue
            result = self._distribute_channel(channel)
            self._distribution[channel] = result
            if not result.get("ok"):
                failed.append(f"{channel}:{result.get('error', 'unknown')}")
        if failed:
            return False, "; ".join(failed)
        return True, f"all_{len(self._task.channels)}_distributed"

    def _distribute_channel(self, channel: str) -> dict[str, Any]:
        """分发单渠道（幂等：已成功则跳过）。"""
        script = CHANNEL_SCRIPT.get(channel)
        if script is None:
            return {"ok": False, "error": f"unsupported_channel:{channel}"}
        try:
            script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / script
            if not script_path.exists():
                return {"ok": False, "error": f"script_not_found:{script}"}
            cmd = [sys.executable, str(script_path), "--publish",
                   "--channel", channel,
                   "--tag", self._release_tag or "latest",
                   "--repo", self._task.repo]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            output = (result.stdout or "") + (result.stderr or "")
            if result.returncode != 0:
                return {"ok": False, "error": output[:300]}
            return {"ok": True, "url": self._extract_url(output)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300]}

    @staticmethod
    def _extract_url(output: str) -> str:
        """从分发输出中提取第一个 http(s) URL。"""
        import re

        m = re.search(r"https?://[^\s\"']+", output)
        return m.group(0) if m else ""

    def _check_links_reachable(self, _unused: Path) -> tuple[bool, str]:
        """验证分发链接可达 + release 页面可访问。"""
        import urllib.request

        urls: list[str] = []
        for _ch, info in self._distribution.items():
            if info.get("url"):
                urls.append(info["url"])
        if self._release_url:
            urls.append(self._release_url)
        if not urls:
            return True, "no_links"

        failed: list[str] = []
        for url in urls:
            try:
                resp = urllib.request.urlopen(url, timeout=15)
                if resp.status >= 400:
                    failed.append(f"{url}={resp.status}")
            except Exception as exc:
                failed.append(f"{url}={exc}")
        if failed:
            return False, "; ".join(failed)
        return True, f"all_{len(urls)}_reachable"

    # ── 生命周期钩子 ─────────────────────────────────────────────

    def _on_start(self) -> None:
        super()._on_start()
        self._base_stars = self._query_stars()
        logger.info(
            "OSSGrowthLoop[%s] started | release=%s channels=%s base_stars=%s",
            self._task.repo, self._release_tag or "latest",
            self._task.channels, self._base_stars,
        )

    # ── 核心周期 ─────────────────────────────────────────────────

    async def _run_governed_cycle(self, iteration: int) -> dict[str, Any]:
        """单周期：确认 release + 分发 + 验证 + 审计。"""
        cycle_start = time.time()

        tmpdir = Path("/tmp") / f"maref_oss_{self._task.repo.replace('/', '_')}"
        tmpdir.mkdir(parents=True, exist_ok=True)
        report = await asyncio.to_thread(self._verifier.verify, tmpdir, self._spec)
        self._last_report = report.to_dict()

        failures = [
            {"id": c.criterion_id, "detail": c.detail}
            for c in report.failed_must_items()
        ]

        self._audit_cycle(iteration, report, failures)

        cycle_duration = (time.time() - cycle_start) * 1000
        stars_now = self._query_stars()
        star_delta = (stars_now - self._base_stars) if (stars_now is not None and self._base_stars is not None) else None
        summary = {
            "iteration": iteration,
            "release": self._release_tag,
            "release_url": self._release_url,
            "distribution": dict(self._distribution),
            "cycle_duration_ms": round(cycle_duration, 1),
            "must_pass": report.must_pass_count,
            "must_total": report.must_total,
            "must_fail": report.must_fail_count,
            "all_must_pass": report.all_must_pass,
            "star_delta": star_delta,
            "failures": failures,
            "verification_report": report.to_dict(),
        }
        self._cycle_results.append(summary)

        logger.info(
            "Cycle %d: release=%s must=%d/%d failures=%d star_delta=%s",
            iteration, self._release_tag or "pending",
            report.must_pass_count, report.must_total,
            len(failures), star_delta,
        )

        return summary

    # ── 审计 ─────────────────────────────────────────────────────

    def _audit_cycle(
        self, iteration: int, report: Any, failures: list[dict[str, Any]],
    ) -> None:
        if self._audit_bridge is None:
            return
        self._audit_bridge.record_cycle(
            task_id=f"oss_{self._task.repo}",
            iteration=iteration,
            adapter_name="OSSGrowth",
            report=report,
            failures=failures,
        )

    # ── 状态摘要 ─────────────────────────────────────────────────

    def get_status_summary(self) -> dict[str, Any]:
        base = super().get_status_summary()
        last = self._cycle_results[-1] if self._cycle_results else {}
        base.update({
            "repo": self._task.repo,
            "release": self._release_tag,
            "release_url": self._release_url,
            "channels": self._task.channels,
            "distribution": dict(self._distribution),
            "cycles": len(self._cycle_results),
            "all_must_pass": last.get("all_must_pass", False),
            "must_pass": last.get("must_pass", 0),
            "must_total": last.get("must_total", 0),
            "must_fail": last.get("must_fail", 0),
            "star_delta": last.get("star_delta"),
        })
        return base

    def _get_state_snapshot(self) -> dict[str, Any]:
        base = super()._get_state_snapshot()
        if self._last_report:
            base["verification_report"] = self._last_report
        return base

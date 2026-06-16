"""
MAREF Self-Healing Loop — 观察→诊断→修复 闭环调度器

将 SelfObserver → SelfDiagnostician → SelfHealer 连接为定期运行的自愈流水线。
这是 P0 修复：把\"发火钥匙拧上\"。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("maref.self_healing_loop")


@dataclass
class SelfHealingConfig:
    """自愈循环配置."""

    check_interval_seconds: float = 300.0  # 每 5 分钟巡检一次
    max_heal_iterations: int = 3
    enable_architecture_proposals: bool = True
    arch_proposal_interval_cycles: int = 12  # 每 12 次巡检（约 1 小时）做一次架构提案
    log_dir: str = ".self_healing_logs"
    enable_audit: bool = True


@dataclass
class HealingCycleReport:
    """单次自愈循环的报告."""

    cycle_id: int
    timestamp: float
    risk_level: str
    risk_matrix: dict[str, str]
    problems_found: list[str]
    actions_taken: list[dict[str, Any]]
    converged: bool
    final_state: str
    duration_ms: float
    proposals_generated: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level,
            "risk_matrix": self.risk_matrix,
            "problems_found": self.problems_found,
            "actions_taken": self.actions_taken,
            "converged": self.converged,
            "final_state": self.final_state,
            "duration_ms": round(self.duration_ms, 2),
            "proposals_generated": self.proposals_generated,
        }


class SelfHealingLoop:
    """自愈循环主引擎。

    按 config.check_interval_seconds 定期执行：

        1. SelfObserver.snapshot()       → 系统快照
        2. SelfDiagnostician.diagnose()  → 风险诊断
        3. SelfHealer.heal_cycle()       → 修复执行
        4. SelfArchitect.propose_all()   → 架构改进（可选，低频）
        5. UnifiedAuditStore.append()    → 审计记录

    用法:

        loop = SelfHealingLoop()
        await loop.run()          # 阻塞运行
        loop.stop()               # 在另一个 coro 中停止
    """

    def __init__(
        self,
        config: SelfHealingConfig | None = None,
        root_path: str | Path | None = None,
    ) -> None:
        self._config = config or SelfHealingConfig()
        self._root_path = Path(root_path) if root_path else Path.cwd()
        self._running = False
        self._cycle_count = 0
        self._history: list[HealingCycleReport] = []

        # 延迟导入 — 避免模块加载时的循环依赖
        self._observer = None
        self._diagnostician = None
        self._healer = None
        self._architect = None
        self._audit_store = None

    # ── 生命周期 ────────────────────────────────────────────────

    async def run(self) -> None:
        """启动自愈循环，阻塞直到 stop() 被调用."""
        self._running = True
        self._lazy_init()

        logger.info(
            "SelfHealingLoop started | interval=%ss root=%s",
            self._config.check_interval_seconds,
            self._root_path,
        )

        try:
            while self._running:
                cycle_start = time.time()
                self._cycle_count += 1

                try:
                    report = await self._run_one_cycle()
                    self._history.append(report)
                    self._log_cycle_result(report)
                except Exception as exc:
                    logger.error("Cycle %d failed: %s", self._cycle_count, exc, exc_info=True)

                elapsed = time.time() - cycle_start
                sleep_time = max(0.0, self._config.check_interval_seconds - elapsed)
                if self._running and sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("SelfHealingLoop cancelled")
        finally:
            self._running = False

    def stop(self) -> None:
        """请求停止循环."""
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def history(self) -> list[HealingCycleReport]:
        return list(self._history)

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    # ── 内部实现 ────────────────────────────────────────────────

    def _lazy_init(self) -> None:
        """延迟初始化 Self-* 智能体.

        放在首次 run() 时初始化，避免 __init__ 时加载所有依赖。
        """
        if self._observer is not None:
            return

        from maref.recursive.self_architect import SelfArchitect
        from maref.recursive.self_diagnostician import SelfDiagnostician
        from maref.recursive.self_healer import SelfHealer
        from maref.recursive.self_observer import SelfObserver
        from maref.recursive.unified_audit import UnifiedAuditStore

        self._observer = SelfObserver(root_path=str(self._root_path))
        self._diagnostician = SelfDiagnostician()
        self._healer = SelfHealer(max_iterations=self._config.max_heal_iterations)
        self._audit_store = UnifiedAuditStore()
        self._architect = SelfArchitect(audit_store=self._audit_store)

    async def _run_one_cycle(self) -> HealingCycleReport:
        """执行一次完整的观察→诊断→修复循环."""
        cycle_start = time.time()
        start_ts = cycle_start

        # ── 1. 观察 ─────────────────────────────────────────────
        snapshot = self._observer.snapshot()
        logger.debug(
            "Cycle %d: snapshot taken — %d files, %d tests",
            self._cycle_count,
            snapshot.source_file_count,
            snapshot.test_stats.get("total", 0),
        )

        # ── 2. 诊断 ─────────────────────────────────────────────
        report = self._diagnostician.diagnose(snapshot)
        risk_level = report.overall_risk.value
        risk_matrix = {k: v.value for k, v in report.risk_matrix.items()}
        logger.info(
            "Cycle %d: risk=%s matrix=%s",
            self._cycle_count,
            risk_level,
            risk_matrix,
        )

        # ── 3. 修复 ─────────────────────────────────────────────
        problems = self._healer.triage(report)
        actions_taken: list[dict[str, Any]] = []
        converged = True
        final_state = "HEALTHY"

        if problems and problems != ["unknown"]:
            logger.info(
                "Cycle %d: problems detected=%s — starting heal cycle",
                self._cycle_count,
                problems,
            )

            healing_record = self._healer.heal_cycle(
                report=report,
                auto_re_diagnose=True,
                _observer=self._observer,
                _diagnostician=self._diagnostician,
            )
            converged = healing_record.converged
            final_state = healing_record.final_state

            for action in healing_record.actions:
                actions_taken.append({
                    "problem_type": action.problem_type,
                    "strategy": action.strategy,
                    "success": action.success,
                    "detail": action.detail[:200],
                    "exit_code": action.exit_code,
                })

            logger.info(
                "Cycle %d: heal result — converged=%s final_state=%s actions=%d",
                self._cycle_count,
                converged,
                final_state,
                len(actions_taken),
            )

            # 审计记录
            if self._config.enable_audit:
                for record in healing_record.to_unified(round_num=self._cycle_count):
                    self._audit_store.append(record)

        # ── 4. 架构提案（低频） ──────────────────────────────────
        proposals_generated = 0
        if (
            self._config.enable_architecture_proposals
            and self._cycle_count % self._config.arch_proposal_interval_cycles == 0
        ):
            try:
                proposals = self._architect.propose_all()
                proposals_generated = len(proposals)
                if proposals:
                    logger.info(
                        "Cycle %d: %d architecture proposals generated",
                        self._cycle_count,
                        proposals_generated,
                    )
            except Exception as exc:
                logger.warning("Architecture proposal failed: %s", exc)

        # ── 5. 完整的审计记录 ────────────────────────────────────
        if self._config.enable_audit:
            from maref.recursive.unified_audit import UnifiedAuditRecord, make_record_id

            audit_record = UnifiedAuditRecord(
                record_id=make_record_id(
                    "heal_cycle", hash((self._cycle_count, start_ts)) % 100000
                ),
                timestamp=start_ts,
                layer="evolution",
                round=self._cycle_count,
                event_type="self_healing_cycle",
                source_module="SelfHealingLoop",
                target_module="system",
                decision=risk_level,
                justification=(
                    f"risk={risk_level} problems={problems} "
                    f"converged={converged} final={final_state} "
                    f"actions={len(actions_taken)}"
                ),
                outcome="success" if converged else "failure",
                context_refs=[str(self._root_path)],
            )
            self._audit_store.append(audit_record)

        duration_ms = (time.time() - cycle_start) * 1000.0

        return HealingCycleReport(
            cycle_id=self._cycle_count,
            timestamp=start_ts,
            risk_level=risk_level,
            risk_matrix=risk_matrix,
            problems_found=problems,
            actions_taken=actions_taken,
            converged=converged,
            final_state=final_state,
            duration_ms=duration_ms,
            proposals_generated=proposals_generated,
        )

    def _log_cycle_result(self, report: HealingCycleReport) -> None:
        """打印一次循环的结果摘要. 使用 logger.info."""
        status = "✅" if report.converged else "❌"
        logger.info(
            "%s Cycle %d | risk=%s | actions=%d | converged=%s | duration=%.0fms",
            status,
            report.cycle_id,
            report.risk_level,
            len(report.actions_taken),
            report.converged,
            report.duration_ms,
        )

    # ── 工具方法 ────────────────────────────────────────────────

    def get_status_summary(self) -> dict[str, Any]:
        """获取自愈循环的状态摘要."""
        recent = self._history[-5:] if self._history else []
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "config": {
                "check_interval_seconds": self._config.check_interval_seconds,
                "max_heal_iterations": self._config.max_heal_iterations,
                "enable_architecture_proposals": self._config.enable_architecture_proposals,
            },
            "recent_cycles": [r.to_dict() for r in recent],
            "audit_record_count": (
                self._audit_store.count() if self._audit_store else 0
            ),
        }

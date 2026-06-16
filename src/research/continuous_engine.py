"""
MAREF Continuous AutoResearch Engine

Integrates all components for 24/7 unattended research:
- Experiment Registry (unified Phase 8-10 experiments)
- Knowledge Graph (persistent findings storage)
- Discovery Engine (cross-temporal analysis)
- Orchestrator (dynamic experiment selection)
- Fault Recovery (error handling)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv

logger = structlog.get_logger(__name__)

load_dotenv()  # Automatically loads .env / .env.local

from research.dashscope_client import DashScopeClient  # noqa: E402
from research.discovery_engine import DiscoveryEngine  # noqa: E402
from research.experiment_registry import ExperimentRegistry  # noqa: E402
from research.fault_recovery import FaultRecovery  # noqa: E402
from research.knowledge_graph import KnowledgeGraph  # noqa: E402
from research.orchestrator import ExperimentOrchestrator, StoppingCriteria  # noqa: E402
from research.vector_store import VectorKnowledgeStore  # noqa: E402


@dataclass
class ContinuousReport:
    """Report from a continuous research batch."""

    timestamp: str
    batch_id: int
    experiments_run: int
    findings_count: int
    experiments_by_type: dict[str, int]
    top_findings: list[str]
    insights: list[str]
    knowledge_graph_stats: dict[str, Any]
    orchestrator_stats: dict[str, Any]
    recovery_stats: dict[str, Any]
    llm_analysis: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContinuousAutoResearch:
    """
    Main engine for continuous autoresearch.
    Runs experiments, collects findings, and generates insights 24/7.
    """

    def __init__(
        self,
        output_dir: Path,
        experiments_per_batch: int = 50,
        batch_interval_minutes: float = 10.0,
        enable_llm_analysis: bool = True,
        llm_model: str | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._experiments_per_batch = experiments_per_batch
        self._batch_interval = batch_interval_minutes * 60.0
        self._batch_count = 0
        self._enable_llm_analysis = enable_llm_analysis
        self._llm_client: DashScopeClient | None = None
        self._llm_model = llm_model

        # Initialize components
        # Save knowledge graph in project output dir for persistence
        kg_path = self._output_dir / "knowledge_graph.json"
        self._kg = KnowledgeGraph(storage_path=kg_path)

        # Vector knowledge store (semantic search layer on top of KG)
        self._vks = VectorKnowledgeStore(path=self._output_dir)

        self._registry = ExperimentRegistry()
        self._orchestrator = ExperimentOrchestrator(
            registry=self._registry,
            criteria=StoppingCriteria(
                max_consecutive_no_findings=5,
                max_experiments_per_batch=experiments_per_batch,
            ),
            vector_store=self._vks,
        )
        self._discovery = DiscoveryEngine(knowledge_graph=self._kg)
        self._recovery = FaultRecovery()

    async def _ensure_llm_client(self) -> DashScopeClient | None:
        """Lazy initialization of LLM client."""
        if not self._enable_llm_analysis:
            return None
        if self._llm_client is None:
            try:
                self._llm_client = DashScopeClient(model=self._llm_model)
            except ValueError:
                logger.warning("DASHSCOPE_API_KEY not set, LLM analysis disabled")
                self._enable_llm_analysis = False
                return None
        return self._llm_client

    async def run_batch(self) -> ContinuousReport:
        """Run one batch of experiments."""
        logger.info("Starting batch %s", self._batch_count)

        self._orchestrator.reset_batch()
        findings = []
        experiments_by_type: dict[str, int] = {}

        while not self._orchestrator.should_stop():
            # Select next experiment
            exp_name, exp_fn = self._orchestrator.select_next_experiment()

            if exp_fn is None:
                break

            # Run with fault recovery
            result = await self._recovery.run_with_recovery(
                lambda: exp_fn(self._batch_count)  # noqa: B023
            )

            if result.success and result.result is not None:
                # Record result
                self._orchestrator.record_result(exp_name, result.result)
                experiments_by_type[exp_name] = experiments_by_type.get(exp_name, 0) + 1

                # Extract findings
                if hasattr(result.result, "findings"):
                    for finding in result.result.findings:
                        findings.append(finding)
                        self._kg.add_finding(
                            content=finding,
                            source=exp_name,
                            metadata={"batch_id": self._batch_count},
                        )
                        self._vks.add_finding(
                            content=finding,
                            metadata={"experiment": exp_name, "batch_id": str(self._batch_count)},
                        )

        # Generate insights
        insights = self._discovery.get_insights()

        # Generate hypotheses
        hypotheses = self._discovery.generate_hypotheses()
        for hyp in hypotheses:
            self._kg.add_hypothesis(
                content=hyp.hypothesis,
                source=hyp.suggested_experiment,
            )

        # LLM-powered batch analysis
        llm_analysis: dict[str, Any] | None = None
        llm_client = await self._ensure_llm_client()
        if llm_client and findings:
            try:
                logger.info("Running LLM analysis...")
                batch_analysis = await llm_client.analyze_batch(
                    batch_id=self._batch_count,
                    experiment_results=[
                        {
                            "experiment_type": name,
                            "findings": list(findings),
                        }
                        for name in experiments_by_type
                    ],
                    knowledge_graph_summary=self._kg.get_stats(),
                )
                llm_analysis = {
                    "key_insights": batch_analysis.key_insights,
                    "patterns_detected": batch_analysis.patterns_detected,
                    "anomalies_flagged": batch_analysis.anomalies_flagged,
                    "recommendations": batch_analysis.recommendations,
                    "overall_assessment": batch_analysis.overall_assessment,
                }
                logger.info("LLM analysis complete")
            except Exception as e:
                logger.warning("LLM analysis failed: %s", e)
                llm_analysis = {"error": str(e)}
            finally:
                # Ensure LLM client session is closed
                await llm_client.close()

        # Post-process findings: deduplicate semantically + mark truncations
        processed_findings = self._post_process_findings(findings)

        report = ContinuousReport(
            timestamp=datetime.now().isoformat(),
            batch_id=self._batch_count,
            experiments_run=len(self._orchestrator._batch_results),
            findings_count=len(findings),
            experiments_by_type=experiments_by_type,
            top_findings=processed_findings[:20],
            insights=insights,
            knowledge_graph_stats=self._kg.get_stats(),
            orchestrator_stats=self._orchestrator.get_stats(),
            recovery_stats=self._recovery.get_stats(),
            llm_analysis=llm_analysis,
        )

        self._batch_count += 1
        return report

    def save_report(self, report: ContinuousReport) -> Path:
        """Save report to output directory."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # JSON report
        json_path = self._output_dir / f"batch_{report.batch_id:04d}_{report.timestamp[:10]}.json"
        with open(json_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)

        # Markdown report
        md_path = self._output_dir / f"batch_{report.batch_id:04d}_{report.timestamp[:10]}.md"
        with open(md_path, "w") as f:
            f.write(self._format_markdown(report))

        return md_path

    def _format_markdown(self, report: ContinuousReport) -> str:
        """Format report as markdown in Chinese."""
        _TYPE_NAMES = {
            "random_walk": "随机路径分析",
            "gray_code_fault_tolerance": "格雷码容错",
            "self_observation": "自观测",
            "adaptive_threshold": "自适应阈值",
            "emergence_detection": "涌现检测",
            "policy_lifecycle": "策略生命周期",
            "rollback_safety": "回滚安全",
            "ab_test_winner": "A/B测试",
            "degradation_prevention": "退化预防",
            "meta_learning_convergence": "元学习收敛",
            "weight_stability": "权重稳定性",
            "recursive_safety": "递归安全",
            "reward_shaping": "奖励塑形",
        }
        lines = [
            f"# MAREF 持续研究 - 批次 {report.batch_id}",
            "",
            f"**时间戳**: {report.timestamp}",
            f"**实验运行数**: {report.experiments_run}",
            f"**发现数**: {report.findings_count}",
            "",
            "## 实验分布",
            "",
            "| 类型 | 数量 |",
            "|------|------|",
        ]
        for exp_type, count in report.experiments_by_type.items():
            cn_name = _TYPE_NAMES.get(exp_type, exp_type)
            lines.append(f"| {cn_name} | {count} |")

        lines.extend(
            [
                "",
                "## 重要发现",
                "",
            ]
        )
        for finding in report.top_findings:
            lines.append(f"- {finding}")

        lines.extend(
            [
                "",
                "## 洞察",
                "",
            ]
        )
        for insight in report.insights:
            lines.append(f"- {insight}")

        lines.extend(
            [
                "",
                "## 知识图谱",
                "",
                "```json",
                json.dumps(report.knowledge_graph_stats, indent=2),
                "```",
                "",
                "## 系统健康",
                "",
                f"- 连续失败: {report.recovery_stats.get('consecutive_failures', 0)}",
                f"- 总失败: {report.recovery_stats.get('total_failures', 0)}",
                f"- 需要注意: {report.recovery_stats.get('needs_attention', False)}",
            ]
        )

        if report.llm_analysis:
            lines.extend(
                [
                    "",
                    "## LLM 分析 (百炼 Qwen)",
                    "",
                    f"**总体评估**: {report.llm_analysis.get('overall_assessment', 'N/A')}",
                    "",
                    "### 关键洞察",
                    "",
                ]
            )
            for insight in report.llm_analysis.get("key_insights", []):
                lines.append(f"- {insight}")

            lines.extend(
                [
                    "",
                    "### 检测到的模式",
                    "",
                ]
            )
            for pattern in report.llm_analysis.get("patterns_detected", []):
                lines.append(f"- {pattern}")

            lines.extend(
                [
                    "",
                    "### 标记的异常",
                    "",
                ]
            )
            for anomaly in report.llm_analysis.get("anomalies_flagged", []):
                lines.append(f"- {anomaly}")

            lines.extend(
                [
                    "",
                    "### 建议",
                    "",
                ]
            )
            for rec in report.llm_analysis.get("recommendations", []):
                lines.append(f"- {rec}")

        lines.extend(
            [
                "",
                "---",
                "*由 MAREF 持续自主研究引擎与百炼 LLM 生成*",
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def _detect_truncation(text: str) -> bool:
        """Detect if text appears truncated mid-sentence."""
        if not text or len(text) < 10:
            return False
        stripped = text.rstrip()
        if not stripped:
            return False
        last_char = stripped[-1]
        natural_ends = {"。", "！", "？", "…", "”", '"', ")", "】", "]", "}", ">", ".", "!", "?"}
        if last_char in natural_ends:
            return False
        truncation_markers = {",", "，", "、", "：", ":", "；", ";"}
        if last_char in truncation_markers and len(stripped) > 10:
            return True
        return bool(len(stripped) > 20 and 19968 <= ord(last_char) <= 40959)

    @staticmethod
    def _compute_similarity(a: str, b: str) -> float:
        """Compute rough similarity between two strings using 3-gram overlap."""
        if a == b:
            return 1.0
        if len(a) < 6 or len(b) < 6:
            return 0.0

        def _ngrams(s: str, n: int = 3) -> set[str]:
            s = s.replace("\n", " ").replace("  ", " ")
            return {s[i : i + n] for i in range(len(s) - n + 1)}

        ngrams_a = _ngrams(a)
        ngrams_b = _ngrams(b)
        if not ngrams_a or not ngrams_b:
            return 0.0
        intersection = ngrams_a & ngrams_b
        union = ngrams_a | ngrams_b
        return len(intersection) / len(union) if union else 0.0

    def _post_process_findings(self, findings: list[str]) -> list[str]:
        """Deduplicate findings semantically and mark truncations."""
        unique = list(dict.fromkeys(findings))  # exact dedup, preserve order
        seen = set()
        result: list[str] = []

        for finding in unique:
            # Mark truncation
            if self._detect_truncation(finding):
                finding = finding.rstrip() + "…[截断]"

            # Semantic dedup: skip if too similar to already included
            is_duplicate = False
            for existing in result:
                if self._compute_similarity(finding, existing) > 0.75:
                    is_duplicate = True
                    break
            if not is_duplicate:
                result.append(finding)
                seen.add(finding)

        return result

    async def run_continuous(self, max_batches: int | None = None) -> None:
        """
        Run continuous research loop.

        Args:
            max_batches: Maximum number of batches (None for infinite)
        """
        logger.info("Starting continuous research")
        logger.debug("Output: %s", self._output_dir)
        logger.debug("Batch interval: %.1f minutes", self._batch_interval / 60)

        while max_batches is None or self._batch_count < max_batches:
            try:
                report = await self.run_batch()
                self.save_report(report)

                logger.info(
                    "Batch %s complete: %s experiments, %s findings",
                    report.batch_id,
                    report.experiments_run,
                    report.findings_count,
                )

                # Wait before next batch
                if max_batches is None or self._batch_count < max_batches:
                    await asyncio.sleep(self._batch_interval)

            except KeyboardInterrupt:
                logger.info("Stopping continuous research")
                break
            except Exception as e:
                logger.warning("Batch error: %s", e)
                await asyncio.sleep(60)  # Wait 1 minute before retry


async def main() -> None:
    """Main entry point for continuous research."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="MAREF Continuous AutoResearch")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.environ.get("MAREF_OUTPUT_DIR", "research_output")),
        help="Output directory for reports (default: research_output or MAREF_OUTPUT_DIR env)",
    )
    parser.add_argument(
        "--experiments-per-batch",
        type=int,
        default=50,
        help="Experiments per batch",
    )
    parser.add_argument(
        "--batch-interval",
        type=float,
        default=10.0,
        help="Minutes between batches",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Maximum batches (default: infinite)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM analysis (no API calls)",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="LLM model to use (default: qwen-plus)",
    )

    args = parser.parse_args()

    engine = ContinuousAutoResearch(
        output_dir=args.output_dir,
        experiments_per_batch=args.experiments_per_batch,
        batch_interval_minutes=args.batch_interval,
        enable_llm_analysis=not args.no_llm,
        llm_model=args.llm_model,
    )

    await engine.run_continuous(max_batches=args.max_batches)


if __name__ == "__main__":
    asyncio.run(main())

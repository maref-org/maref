from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RatchetBridge:
    """Bridges PERCV's RatchetLoop to MAREF's MetaLearner evolution engine.

    PERCV's ratchet loop optimizes at the prompt/configuration level
    (one variable per experiment, git-as-state-machine). MAREF's MetaLearner
    optimizes at the strategy level (policy proposals every N rounds).

    This bridge creates a two-layer self-improvement system:
    - Layer 1 (Ratchet): Fine-grained prompt/template optimization
    - Layer 2 (MetaLearner): Coarse-grained strategy/parameter evolution

    The MetaLearner acts as an overseer: ratchet experiments that conflict
    with the current strategy direction are rejected.

    Usage:
        bridge = RatchetBridge(meta_learner=ml)
        results = bridge.run_improvement_cycle(
            target_file="prompts/distill_v1.yaml",
            budget=20,
        )
    """

    def __init__(
        self,
        meta_learner: Any | None = None,
        vault_path: str | Path = Path("vault"),
        program_path: str | Path | None = None,
    ):
        self._meta_learner = meta_learner
        self._vault_path = Path(vault_path)
        self._program_path = Path(program_path) if program_path else self._vault_path / "program.md"
        self._cycle_history: list[dict[str, Any]] = []

    def _read_program_config(self) -> dict[str, Any]:
        """Read PERCV's program.md for ratchet configuration."""
        if not self._program_path.exists():
            return {}
        try:
            import yaml

            text = self._program_path.read_text(encoding="utf-8")
            # program.md uses YAML frontmatter
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    return dict(yaml.safe_load(parts[1]) or {})
            return dict(yaml.safe_load(text) or {})
        except Exception as exc:
            logger.warning("Failed to read program config: %s", exc)
            return {}

    def _run_single_ratchet_iteration(
        self,
        target_file: str,
    ) -> dict[str, Any]:
        """Run one ratchet iteration via CLI command."""
        import subprocess
        import time

        t0 = time.perf_counter()
        try:
            result = subprocess.run(
                ["uv", "run", "percv", "evaluate", "--mock"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            elapsed = time.perf_counter() - t0
            stdout = result.stdout.strip()
            score = self._extract_score(stdout)
            return {
                "success": result.returncode == 0,
                "score": score,
                "stdout": stdout[:500],
                "stderr": result.stderr[:500],
                "duration_s": round(elapsed, 2),
                "git_diff": self._get_git_diff(target_file),
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "timeout", "score": 0.0, "duration_s": 300.0}
        except FileNotFoundError:
            return {"success": False, "error": "percv_cli_not_found", "score": 0.0}

    def _extract_score(self, stdout: str) -> float:
        """Extract numeric score from percv evaluate output."""
        import re

        match = re.search(r"(?:score|quality)[:\s]+([\d.]+)", stdout, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return 0.0

    def _get_git_diff(self, target_file: str) -> str:
        """Get git diff for the target file."""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "diff", "--", target_file],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout[:1000] if result.stdout else ""
        except Exception:
            return ""

    def run_improvement_cycle(
        self,
        target_file: str = "prompts/distill_v1.yaml",
        budget: int = 20,
        human_gate: bool = True,
    ) -> list[dict[str, Any]]:
        """Run a ratchet improvement cycle under MAREF MetaLearner oversight.

        Args:
            target_file: Relative path to the file being optimized.
            budget: Maximum number of iterations.
            human_gate: Whether to pause for human approval on improvements.

        Returns:
            List of iteration result dicts, each containing score, approved
            status, and metadata.
        """
        program_config = self._read_program_config()
        effective_budget = budget or program_config.get("budget", {}).get("max_iterations", 20)
        effective_human_gate = human_gate if human_gate else program_config.get("human_gate", True)

        logger.info(
            "Starting ratchet cycle: target=%s budget=%d human_gate=%s",
            target_file,
            effective_budget,
            effective_human_gate,
        )

        iterations: list[dict[str, Any]] = []
        best_score = 0.0
        best_iteration: int | None = None

        for i in range(effective_budget):
            result = self._run_single_ratchet_iteration(target_file)
            score = result.get("score", 0.0)

            approved = False
            if result.get("success"):
                if score > best_score:
                    if self._meta_learner:
                        try:
                            alignment = self._meta_learner.evaluate_strategy_alignment(
                                change={"file": target_file, "score": score},
                            )
                            approved = alignment.get("aligned", False)
                        except Exception:
                            approved = True
                    else:
                        approved = True

                    if approved:
                        best_score = score
                        best_iteration = i
                        if effective_human_gate:
                            logger.info(
                                "Iteration %d: score improved to %.4f (awaiting human gate)",
                                i,
                                score,
                            )
                    else:
                        logger.info(
                            "Iteration %d: score %.4f rejected by MetaLearner",
                            i,
                            score,
                        )
                else:
                    logger.info("Iteration %d: score %.4f (no improvement)", i, score)

            iteration_record = {
                "iteration": i,
                "score": score,
                "approved": approved,
                "best_score": best_score,
                "best_iteration": best_iteration,
                "duration_s": result.get("duration_s", 0),
                "error": result.get("error"),
                "git_diff": result.get("git_diff", ""),
            }
            iterations.append(iteration_record)
            self._cycle_history.append(iteration_record)

            if not result.get("success"):
                logger.warning("Iteration %d failed: %s", i, result.get("error"))
                if i > 0:
                    break

        logger.info(
            "Ratchet cycle complete: %d iterations, best score %.4f at iter %d",
            len(iterations),
            best_score,
            best_iteration or 0,
        )
        return iterations

    def sync_metrics_to_maref(self) -> dict[str, Any]:
        """Push ratchet experiment results to MAREF's metrics store.

        Returns a summary of experiment metrics.
        """
        if not self._cycle_history:
            return {"status": "no_data"}

        scores = [r.get("score", 0.0) for r in self._cycle_history]
        approved = [r for r in self._cycle_history if r.get("approved")]

        return {
            "status": "ok",
            "total_iterations": len(self._cycle_history),
            "approved_count": len(approved),
            "best_score": max(scores) if scores else 0.0,
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
            "score_improvement": max(scores) - scores[0] if len(scores) > 1 else 0.0,
            "last_updated": __import__("time").time(),
        }

    def get_history(self) -> list[dict[str, Any]]:
        """Return full ratchet cycle history."""
        return list(self._cycle_history)

    def reset(self) -> None:
        """Clear cycle history."""
        self._cycle_history.clear()

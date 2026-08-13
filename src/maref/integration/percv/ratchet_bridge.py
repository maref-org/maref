from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RatchetIterationRecord:
    iteration: int
    score: float
    approved: bool
    best_score: float
    best_iteration: int | None
    duration_s: float
    error: str | None = None
    git_diff: str = ""
    target: str = ""
    mas_ts_score: float = 0.0
    mas_ts_level: str = ""
    status: str = ""
    delta: float = 0.0
    previous_best: float = 0.0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "score": self.score,
            "approved": self.approved,
            "best_score": self.best_score,
            "best_iteration": self.best_iteration,
            "duration_s": self.duration_s,
            "error": self.error,
            "target": self.target,
            "mas_ts_score": self.mas_ts_score,
            "mas_ts_level": self.mas_ts_level,
            "status": self.status,
            "delta": self.delta,
            "previous_best": self.previous_best,
            "description": self.description,
        }


class RatchetBridge:
    # Mirror MetaRatchet.CONSTITUTIONAL_IMMUTABLES for RL-005 enforcement
    CONSTITUTIONAL_IMMUTABLES: list[str] = ["branch_prefix"]

    def __init__(
        self,
        meta_learner: Any | None = None,
        vault_path: str | Path = Path("vault"),
        program_path: str | Path | None = None,
        mas_ts_bridge: Any | None = None,
        redlines_path: str | Path | None = None,
        cross_dimensional_analyzer: Any | None = None,
        evaluation_command: str = "",
    ):
        self._meta_learner = meta_learner
        self._vault_path = Path(vault_path)
        self._program_path = Path(program_path) if program_path else self._vault_path / "program.md"
        self._evaluation_command = evaluation_command  # overrides program.md
        self._cycle_history: list[RatchetIterationRecord] = []
        self._mas_ts_bridge = mas_ts_bridge
        self._redlines = self._load_redlines(redlines_path or Path("configs/rsi_redlines.yaml"))
        self._cross_dimensional_analyzer = cross_dimensional_analyzer
        self._cross_dimensional_triggered = False

    def _load_redlines(self, path: str | Path) -> dict[str, Any]:
        try:
            import yaml

            p = Path(path)
            if p.exists():
                data = yaml.safe_load(p.read_text())
                return data or {}
        except Exception as exc:
            logger.warning("Failed to load redlines from %s: %s", path, exc)
        return {}

    def check_redlines(
        self,
        target: str,
        score: float,
        is_meta: bool = False,
        mas_ts_score: float = 0,
        human_gate: bool = True,
        proposed_config_key: str | None = None,
        cross_dimensional_triggered: bool = True,
    ) -> list[str]:
        violations = []
        for rule in self._redlines.get("rsi_immutables", []):
            applies = rule.get("applies_to", [])
            if is_meta and "meta_ratchet" not in applies:
                continue
            if not is_meta and "ratchet" not in applies:
                continue
            rid = rule.get("rule_id", "")
            action = rule.get("auto_action", "")
            if rid == "RSI-RL-001" and not human_gate:
                violations.append(f"{rid}: {action} - human_gate is False")
            if rid == "RSI-RL-004" and mas_ts_score > 0 and mas_ts_score < 60:
                violations.append(f"{rid}: {action} - MAS-TS score {mas_ts_score} below 60")
            if rid == "RSI-RL-002" and is_meta:
                violations.append(f"{rid}: {action} - meta-ratchet requires >= 10 sandbox rounds")
            if (
                rid == "RSI-RL-005"
                and is_meta
                and proposed_config_key
                and proposed_config_key in self.CONSTITUTIONAL_IMMUTABLES
            ):
                violations.append(
                    f"{rid}: {action} - proposed change to immutable '{proposed_config_key}'"
                )
            if rid == "RSI-RL-003" and not cross_dimensional_triggered:
                violations.append(f"{rid}: {action} - cross-dimensional analysis not triggered")
        return violations

    def _enforce_redlines(
        self,
        target: str,
        mas_ts_score: float,
        human_gate: bool,
        cross_dimensional_triggered: bool = True,
    ) -> dict[str, Any]:
        ACTION_PRIORITY = {"HALT": 3, "BLOCK": 2, "DISCARD": 1, "WARN_AND_CONTINUE": 0}
        result: dict[str, Any] = {}
        for rule in self._redlines.get("rsi_immutables", []):
            applies = rule.get("applies_to", [])
            if "ratchet" not in applies:
                continue
            rid = rule.get("rule_id", "")
            action = rule.get("auto_action", "")
            priority = ACTION_PRIORITY.get(action, -1)

            if rid == "RSI-RL-004" and mas_ts_score > 0 and mas_ts_score < 60:
                if priority > ACTION_PRIORITY.get(result.get("action", ""), -1):
                    result["violation"] = rid
                    result["action"] = action
            if rid == "RSI-RL-001" and not human_gate:
                if priority > ACTION_PRIORITY.get(result.get("action", ""), -1):
                    result["violation"] = rid
                    result["action"] = action
            if rid == "RSI-RL-003" and not cross_dimensional_triggered:
                logger.warning(
                    "RSI-RL-003: cross-dimensional analysis not triggered (WARN_AND_CONTINUE)"
                )
        return result

    def _read_program_config(self) -> dict[str, Any]:
        if not self._program_path.exists():
            return {}
        try:
            import yaml

            text = self._program_path.read_text(encoding="utf-8")
            # Handle YAML inside ```yaml ... ``` code blocks (PERCV format)
            yaml_match = self._extract_yaml_block(text)
            if yaml_match:
                data = yaml.safe_load(yaml_match)
                if isinstance(data, dict):
                    return data
            # Handle --- delimited frontmatter
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    return dict(yaml.safe_load(parts[1]) or {})
            # Handle raw YAML
            return dict(yaml.safe_load(text) or {})
        except Exception as exc:
            logger.warning("Failed to read program config: %s", exc)
            return {}

    @staticmethod
    def _extract_yaml_block(text: str) -> str | None:
        """Extract YAML from the first ```yaml ... ``` block."""
        lines = text.splitlines()
        in_block = False
        yaml_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped in ("```yaml", "```yml"):
                in_block = True
                yaml_lines = []
                continue
            if in_block and stripped == "```":
                return "\n".join(yaml_lines)
            if in_block:
                yaml_lines.append(line)
        return "\n".join(yaml_lines) if yaml_lines else None

    def _run_single_ratchet_iteration(
        self,
        target_file: str,
        use_mas_ts: bool = False,
        mas_ts_card: str = "",
    ) -> dict[str, Any]:
        import shlex
        import subprocess
        import time

        t0 = time.perf_counter()
        # Use the explicit evaluation_command (set by caller, includes --mas-ts),
        # falling back to program.md config, then a safe --mock default.
        eval_cmd_str = (
            self._evaluation_command
            or self._read_program_config().get("evaluation_command", "")
            or "uv run percv evaluate --mock"
        )
        eval_cmd = shlex.split(eval_cmd_str)

        try:
            result = subprocess.run(
                eval_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            elapsed = time.perf_counter() - t0
            stdout = result.stdout.strip()
            score = self._extract_score(stdout)
            raw = {
                "success": result.returncode == 0,
                "score": score,
                "stdout": stdout[:500],
                "stderr": result.stderr[:500],
                "duration_s": round(elapsed, 2),
                "git_diff": self._get_git_diff(target_file),
            }
            if self._mas_ts_bridge and use_mas_ts and mas_ts_card:
                try:
                    mas_ts_result = self._mas_ts_bridge.run_fast_screen(mas_ts_card)
                    raw["mas_ts_score"] = mas_ts_result.get("overall_score", 0)
                    raw["mas_ts_level"] = mas_ts_result.get("level", "L0")
                except Exception as exc:
                    logger.warning("MAS-TS integration failed: %s", exc)
            return raw
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "timeout", "score": 0.0, "duration_s": 300.0}
        except FileNotFoundError:
            return {"success": False, "error": "percv_cli_not_found", "score": 0.0}

    def _extract_score(self, stdout: str) -> float:
        import re

        match = re.search(r"(?:score|quality)[:\s]+([\d.]+)", stdout, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return 0.0

    def _get_git_diff(self, target_file: str) -> str:
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
        use_mas_ts: bool = False,
        mas_ts_card: str = "",
    ) -> list[RatchetIterationRecord]:
        program_config = self._read_program_config()
        effective_budget = budget or program_config.get("budget", {}).get("max_iterations", 20)
        # human_gate=False is a valid explicit value from the caller.
        # Only fall back to vault/program.md when caller's value is True (the default).
        # This ensures the root program.md (human_gate: false) takes precedence
        # over the vault's copy when the caller explicitly passes False.
        if human_gate is False:
            effective_human_gate = False
        else:
            effective_human_gate = program_config.get("human_gate", True)

        logger.info(
            "Starting ratchet cycle: target=%s budget=%d human_gate=%s mas_ts=%s",
            target_file,
            effective_budget,
            effective_human_gate,
            use_mas_ts,
        )

        iterations: list[RatchetIterationRecord] = []
        best_score = 0.0
        best_iteration: int | None = None
        previous_best = 0.0
        self._cross_dimensional_triggered = False

        for i in range(effective_budget):
            result = self._run_single_ratchet_iteration(
                target_file,
                use_mas_ts=use_mas_ts,
                mas_ts_card=mas_ts_card,
            )
            score = result.get("score", 0.0)
            delta = score - previous_best if i > 0 else 0.0
            mas_ts_score = result.get("mas_ts_score", 0.0)

            redline = self._enforce_redlines(
                target_file, mas_ts_score, effective_human_gate, self._cross_dimensional_triggered
            )
            redline_halt = redline.get("action") == "HALT"
            redline_discard = redline.get("action") == "DISCARD"

            if redline_halt:
                logger.warning(
                    "Iteration %d: redline %s triggered HALT", i, redline.get("violation")
                )
                break

            approved = False
            status = "discard"
            if result.get("success"):
                if score > best_score and not redline_discard:
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
                        status = "keep"
                        best_score = score
                        best_iteration = i
                        if effective_human_gate:
                            logger.info(
                                "Iteration %d: score improved to %.4f (awaiting human gate)",
                                i,
                                score,
                            )

                        # Trigger cross-dimensional analysis after keep
                        if self._cross_dimensional_analyzer:
                            try:
                                self._cross_dimensional_analyzer.history = self._cycle_history
                                effects = self._cross_dimensional_analyzer.detect_cross_effects(
                                    window=20
                                )
                                self._cross_dimensional_triggered = True
                                if effects:
                                    logger.info(
                                        "Cross-dimensional effects: %d detected", len(effects)
                                    )
                                    # Query weight registry for current dimension scores
                                    current_weights = {}
                                    registry = getattr(self, "_weight_registry", None)
                                    if registry:
                                        current_weights = {
                                            dim: data.get("current_weight", 0.5)
                                            for dim, data in registry.get_all_weights().items()
                                        }
                                    rec = (
                                        self._cross_dimensional_analyzer.recommend_multi_objective(
                                            current_weights
                                            or {
                                                "correctness": 0.5,
                                                "testing": 0.5,
                                                "code_quality": 0.5,
                                                "security": 0.5,
                                                "performance": 0.5,
                                                "governance": 0.5,
                                            }
                                        )
                                    )
                                    if rec:
                                        logger.info(
                                            "Multi-objective recommendation: %s",
                                            rec.recommended_weights,
                                        )
                            except Exception as exc:
                                logger.warning("Cross-dimensional analysis failed: %s", exc)
                    else:
                        logger.info("Iteration %d: score %.4f rejected by MetaLearner", i, score)
                else:
                    reason = "redline_discard" if redline_discard else "no improvement"
                    logger.info("Iteration %d: score %.4f (%s)", i, score, reason)

            record = RatchetIterationRecord(
                iteration=i,
                score=score,
                approved=approved,
                best_score=best_score,
                best_iteration=best_iteration,
                duration_s=result.get("duration_s", 0),
                error=result.get("error") or redline.get("violation"),
                target=target_file,
                status=status,
                delta=delta,
                previous_best=previous_best,
                mas_ts_score=mas_ts_score,
                mas_ts_level=result.get("mas_ts_level", ""),
            )
            iterations.append(record)
            self._cycle_history.append(record)
            previous_best = best_score

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
        if not self._cycle_history:
            return {"status": "no_data"}
        scores = [r.score for r in self._cycle_history]
        approved = [r for r in self._cycle_history if r.approved]
        return {
            "status": "ok",
            "total_iterations": len(self._cycle_history),
            "approved_count": len(approved),
            "best_score": max(scores) if scores else 0.0,
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
            "score_improvement": max(scores) - scores[0] if len(scores) > 1 else 0.0,
            "last_updated": __import__("time").time(),
        }

    def get_history(self) -> list[RatchetIterationRecord]:
        return list(self._cycle_history)

    def get_history_dicts(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._cycle_history]

    def reset(self) -> None:
        self._cycle_history.clear()

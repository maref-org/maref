from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from maref.governance.state_machine import GovernanceStateMachine
from maref.integration.feature_dev.content_producer import ContentProducer
from maref.integration.feature_dev.content_scorer import ContentScorer
from maref.integration.feature_dev.doc_ingestor import FeatureDocument
from maref.integration.feature_dev.llm_client import LlmClient
from maref.integration.feature_dev.task_generator import FeatureTask, TaskGenerator
from maref.integration.percv.orchestrator import PERCVResearchOrchestrator
from maref.integration.test_platform.eval_observer import MASEvalObserver
from maref.integration.test_platform.quality_gate import EvolutionQualityGate
from maref.integration.test_platform.schema import (
    EvalStatus,
    EvaluationReport,
    LayerReport,
    TestMode,
)

logger = logging.getLogger(__name__)

_LAYER_NAMES: dict[int, str] = {
    1: "Static Audit",
    2: "Reasoning Metrics",
    3: "Action Metrics",
    4: "E2E Metrics",
    5: "MAS Dimensions",
}

GO_THRESHOLD = 75.0
NOGO_THRESHOLD = 50.0
QUALITY_WEIGHT = 0.6


@dataclass
class CycleSnapshot:
    cycle_number: int
    topic: str
    layer_scores: dict[str, float]
    overall_score: float
    overall_status: EvalStatus
    verdict: str
    feedback_injected: str
    duration_seconds: float
    artifacts: dict[str, Any] = field(default_factory=dict)
    go_nogo_decision: str = ""
    budget_used: float = 0.0
    history_entries: list[dict[str, Any]] = field(default_factory=list)
    llm_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_number": self.cycle_number,
            "topic": self.topic,
            "layer_scores": self.layer_scores,
            "overall_score": self.overall_score,
            "overall_status": self.overall_status.value,
            "verdict": self.verdict,
            "feedback_injected": self.feedback_injected,
            "duration_seconds": self.duration_seconds,
            "characters": len(self.artifacts.get("characters", [])),
            "scripts": len(self.artifacts.get("scripts", [])),
            "stages_covered": list(self.artifacts.get("stages_covered", [])),
            "reqs_covered": self.artifacts.get("requirements_covered", 0),
            "go_nogo_decision": self.go_nogo_decision,
            "budget_used": self.budget_used,
            "llm_used": self.llm_used,
        }


class FeatureDevelopmentCycle:
    def __init__(
        self,
        doc: FeatureDocument,
        tasks: list[FeatureTask],
        iterations: int = 10,
        budget_cents: float = 50000.0,
    ) -> None:
        self.doc = doc
        self.tasks = tasks
        self.iterations = iterations
        self.budget_cents = budget_cents
        self.snapshots: list[CycleSnapshot] = []
        self._llm = LlmClient()
        self._sm = GovernanceStateMachine()
        self._eval_obs = MASEvalObserver(governance_fsm=self._sm)
        self._qg = EvolutionQualityGate()
        self._orch = PERCVResearchOrchestrator(
            state_machine=self._sm,
            eval_observer=self._eval_obs,
            quality_gate=self._qg,
        )
        self._producer = ContentProducer(doc)
        self._scorer = ContentScorer(doc)
        self._base_topic = ""
        self._budget_spent = 0.0
        self._prev_artifacts: dict[str, Any] | None = None
        self._go_nogo_triggered = False
        self._final_decision = "in_progress"
        self._llm_feedback_history: list[str] = []

    @property
    def is_deploy_ready(self) -> bool:
        if not self.snapshots:
            return False
        latest = self.snapshots[-1]
        return latest.overall_score >= 80.0 and latest.verdict == "approved"

    @property
    def total_elapsed(self) -> float:
        return sum(s.duration_seconds for s in self.snapshots) if self.snapshots else 0.0

    def run(self) -> list[CycleSnapshot]:
        tg = TaskGenerator(self.doc)
        self._base_topic = tg.get_initial_research_topic()
        self._orch.initialize()
        for i in range(self.iterations):
            if self._go_nogo_triggered:
                break
            snap = self._run_single_cycle(i + 1)
            self.snapshots.append(snap)
            llm_tag = " [LLM]" if snap.llm_used else ""
            logger.info(
                "Cycle %d/%d%s: score=%.1f verdict=%s chars=%d scripts=%d",
                i + 1,
                self.iterations,
                llm_tag,
                snap.overall_score,
                snap.verdict,
                len(snap.artifacts.get("characters", [])),
                len(snap.artifacts.get("scripts", [])),
            )
        return self.snapshots

    def _run_single_cycle(self, cycle_number: int) -> CycleSnapshot:
        t0 = time.perf_counter()
        topic = self._build_topic(cycle_number)
        history: list[dict[str, Any]] = []
        llm_used = False

        # --- Step 1: Research (LLM-generated improvement plan if available) ---
        r1 = self._orch.run_research_cycle(topic=topic)
        history.append({"step": "research", "phase": r1.phase.value})
        sys_prompt = (
            "You are MAREF, an AI recursive evolution engine. "
            "Analyze the feature document requirements and previous evaluation feedback. "
            "Produce a concrete improvement plan for the next content production cycle."
        )
        llm_plan = self._llm.generate(
            system=sys_prompt,
            prompt=f"Feature doc: {self.doc.title}. Requirements: {self.doc.metadata.get('extracted_requirements', 0)}."
            f"Previous feedback: {self._llm_feedback_history[-1:] if self._llm_feedback_history else 'none'}."
            f"Cycle {cycle_number}/{self.iterations}. "
            "Output a specific, actionable plan (3-5 bullet points) for improving content quality this cycle.",
        )
        if llm_plan:
            llm_used = True
            history.append({"step": "llm_research", "plan": llm_plan[:200]})

        # --- Step 2: Produce ---
        scores = self._last_scores()
        artifacts = self._producer.produce(
            cycle=cycle_number,
            feedback=scores,
            prev_artifacts=self._prev_artifacts,
            llm_plan=llm_plan,
        )
        self._prev_artifacts = artifacts
        history.append(
            {
                "step": "produce",
                "phase": "completed",
                "characters": len(artifacts["characters"]),
                "scripts": len(artifacts["scripts"]),
                "stages": list(artifacts["stages_covered"]),
            }
        )

        # --- Step 3: Evaluate (structural + LLM qualitative) ---
        structural = self._scorer.score(artifacts)

        if self._llm.available:
            qual_scores = self._llm_evaluate(artifacts)
            llm_used = True
        else:
            qual_scores = structural

        combined: dict[str, float] = {}
        for key in structural:
            s = structural[key]
            q = qual_scores.get(key, s)
            combined[key] = round(s * (1 - QUALITY_WEIGHT) + q * QUALITY_WEIGHT, 1)

        overall_score = round(sum(combined.values()) / max(len(combined), 1), 1)
        status = self._decide_status(overall_score)

        report = EvaluationReport(
            report_id=f"feature-cycle-{cycle_number}",
            agent_id="feature-agent",
            test_mode=TestMode.FULL_RUN,
            overall_status=status,
            overall_score=overall_score,
            layers=[
                LayerReport(layer_number=num, layer_name=name, score=round(score, 1))
                for num, (name, score) in enumerate(sorted(combined.items()), 1)
            ],
        )
        r2 = self._orch.run_evaluate_cycle(agent_id="feature-agent", report=report)
        history.append(
            {
                "step": "evaluate",
                "phase": r2.phase.value,
                "score": overall_score,
                "structural": structural,
                "qualitative": qual_scores,
            }
        )

        # --- Step 4: Evolve ---
        r3 = self._orch.run_evolve_cycle(candidate_id="feature-agent", score=overall_score)
        verdict = r3.result.get("verdict", "unknown") if r3.result else "unknown"
        history.append({"step": "evolve", "phase": r3.phase.value, "verdict": verdict})

        # --- Step 5: Verify ---
        r4 = self._orch.run_verify_cycle(agent_id="feature-agent")
        history.append({"step": "verify", "phase": r4.phase.value})

        # --- Step 6: Feedback (LLM qualitative if available) ---
        if self._llm.available:
            feedback_text = self._llm_feedback(artifacts, combined)
            llm_used = True
        else:
            feedback_text = self._compile_structural_feedback(combined, artifacts)
        if feedback_text:
            self._llm_feedback_history.append(feedback_text)

        go_nogo = self._evaluate_go_nogo(cycle_number, overall_score)
        cycle_cost = self._estimate_cycle_cost(cycle_number)
        self._budget_spent += cycle_cost
        elapsed = time.perf_counter() - t0

        return CycleSnapshot(
            cycle_number=cycle_number,
            topic=topic,
            layer_scores=combined,
            overall_score=overall_score,
            overall_status=status,
            verdict=verdict,
            feedback_injected=feedback_text,
            duration_seconds=elapsed,
            artifacts=artifacts,
            go_nogo_decision=go_nogo,
            budget_used=round(cycle_cost, 2),
            history_entries=history,
            llm_used=llm_used,
        )

    def _llm_evaluate(self, artifacts: dict[str, Any]) -> dict[str, float]:
        sys = "You are a content quality evaluator. Score produced content (0-100) on 5 dimensions."
        chars = artifacts.get("characters", [])
        scripts = artifacts.get("scripts", [])
        char_str = "\n".join(
            f"- {c.get('name','?')} ({c.get('archetype','?')}): backstory={c.get('backstory','')[:80]}"
            for c in chars[:3]
        )
        script_str = "\n".join(
            f"- {s.get('title','?')} ({s.get('total_duration_s',0)}s, {s.get('scene_count',0)} scenes)"
            for s in scripts[:5]
        )
        prompt = (
            f"Content to evaluate:\nCharacters:\n{char_str}\n\nScripts:\n{script_str}\n\n"
            "Score each dimension 0-100:\n"
            "- Static Audit: structural completeness, profile depth\n"
            "- Reasoning Metrics: narrative coherence, character motivation\n"
            "- Action Metrics: content volume, scene variety\n"
            "- E2E Metrics: story arc completeness, production readiness\n"
            "- MAS Dimensions: character diversity, inter-character dynamics\n"
            'Output JSON: {"Static Audit": N, "Reasoning Metrics": N, ...}'
        )
        result = self._llm.generate_json(system=sys, prompt=prompt)
        if result and all(
            k in result
            for k in (
                "Static Audit",
                "Reasoning Metrics",
                "Action Metrics",
                "E2E Metrics",
                "MAS Dimensions",
            )
        ):
            return {k: min(100.0, max(0.0, float(v))) for k, v in result.items()}
        return {}

    def _llm_feedback(self, artifacts: dict[str, Any], scores: dict[str, float]) -> str:
        sys = "You are MAREF's improvement advisor. Generate specific, actionable feedback for content improvement."
        chars = artifacts.get("characters", [])
        scripts = artifacts.get("scripts", [])
        low = sorted(scores.items(), key=lambda x: x[1])[:2]
        prompt = (
            f"Current scores: {dict(low)}.\n"
            f"Characters: {[c.get('name') for c in chars[:3]]}.\n"
            f"Scripts: {len(scripts)} total.\n"
            "Give 2-3 specific improvement suggestions for the next cycle. Be concrete."
        )
        result = self._llm.generate(system=sys, prompt=prompt, max_tokens=500)
        return result or ""

    def _build_topic(self, cycle_number: int) -> str:
        if cycle_number == 1:
            return self._base_topic
        low = sorted(self.snapshots[-1].layer_scores.items(), key=lambda x: x[1])[:2]
        if not low or low[0][1] >= 80.0:
            return f"{self._base_topic} (iter {cycle_number})"
        focus = ", ".join(f"{n}({s:.0f})" for n, s in low)
        return f"{self._base_topic} [focus: {focus}]"

    def _last_scores(self) -> dict[str, float]:
        if not self.snapshots:
            return dict.fromkeys(_LAYER_NAMES.values(), 0.0)
        return dict(self.snapshots[-1].layer_scores)

    def _decide_status(self, score: float) -> EvalStatus:
        if score >= 80.0:
            return EvalStatus.PASS
        if score >= 50.0:
            return EvalStatus.CONDITIONAL
        return EvalStatus.FAIL

    def _evaluate_go_nogo(self, cycle: int, score: float) -> str:
        if cycle < 3:
            return "monitoring"
        if score >= GO_THRESHOLD:
            self._final_decision = "go"
            return f"GO (score={score:.1f})"
        if score < NOGO_THRESHOLD and cycle >= 5:
            self._go_nogo_triggered = True
            self._final_decision = "kill"
            return f"KILL (score={score:.1f} at cycle {cycle})"
        return f"CONTINUE (score={score:.1f})"

    def _compile_structural_feedback(
        self, scores: dict[str, float], artifacts: dict[str, Any]
    ) -> str:
        chars = len(artifacts.get("characters", []))
        scripts = len(artifacts.get("scripts", []))
        parts = []
        for name, score in sorted(scores.items(), key=lambda x: x[1]):
            gap = max(0.0, 80.0 - score)
            if gap <= 5:
                continue
            if name == "Static Audit":
                parts.append(
                    f"Static Audit={score:.0f}: need more characters ({chars}) or scripts ({scripts})"
                )
            elif name == "MAS Dimensions":
                parts.append(
                    f"MAS={score:.0f}: add more characters with distinct archetypes and crossover episodes"
                )
            else:
                parts.append(f"{name}={score:.0f}: improve coverage")
        return "; ".join(parts[:3]) if parts else "All layers at target."

    def _estimate_cycle_cost(self, cycle: int) -> float:
        return 100.0 * (0.85 ** (cycle - 1))

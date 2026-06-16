from __future__ import annotations

from pathlib import Path
from typing import Any

from maref.integration.feature_dev.doc_ingestor import FeatureDocument


class ContentScorer:
    """Scores PRODUCED content artifacts against the source document's requirements.

    Unlike the previous version which analyzed the document itself, this scorer
    evaluates what was actually produced: characters, scripts, exports.
    The score genuinely changes between cycles because the artifacts improve.
    """

    def __init__(self, doc: FeatureDocument) -> None:
        self.doc = doc

    def score(self, artifacts: dict[str, Any]) -> dict[str, float]:
        return {
            "Static Audit": self._score_static_audit(artifacts),
            "Reasoning Metrics": self._score_reasoning(artifacts),
            "Action Metrics": self._score_action(artifacts),
            "E2E Metrics": self._score_e2e(artifacts),
            "MAS Dimensions": self._score_mas(artifacts),
        }

    def overall(self, layer_scores: dict[str, float]) -> float:
        w = {
            "Static Audit": 0.15,
            "Reasoning Metrics": 0.20,
            "Action Metrics": 0.25,
            "E2E Metrics": 0.20,
            "MAS Dimensions": 0.20,
        }
        return round(sum(layer_scores.get(k, 0) * wv for k, wv in w.items()), 1)

    def _score_static_audit(self, a: dict[str, Any]) -> float:
        score = 0.0
        chars = a.get("characters", [])
        scripts = a.get("scripts", [])
        stages = a.get("stages_covered", set())

        if len(chars) >= 1:
            score += 15.0
        if len(chars) >= 2:
            score += 10.0
        if len(chars) >= 3:
            score += 10.0

        if len(scripts) >= 1:
            score += 10.0
        if len(scripts) >= 3:
            score += 10.0
        if len(scripts) >= 5:
            score += 10.0

        if "mvp" in stages:
            score += 10.0
        if "mixed" in stages:
            score += 10.0
        if "internalization" in stages:
            score += 10.0

        reqs_covered = a.get("requirements_covered", 0)
        doc_reqs = self.doc.metadata.get("extracted_requirements", 1) or 1
        score += min(15.0, (reqs_covered / doc_reqs) * 15.0)

        return min(100.0, score)

    def _score_reasoning(self, a: dict[str, Any]) -> float:
        score = 10.0
        chars = a.get("characters", [])
        scripts = a.get("scripts", [])

        for c in chars:
            if c.get("backstory") and len(c["backstory"]) > 30:
                score += 8.0
            if c.get("archetype"):
                score += 5.0
            if c.get("setting"):
                score += 5.0
        score = min(50.0, score)

        hypos = self.doc.hypotheses
        if hypos:
            if any("H1" in h.name for h in hypos):
                score += 10.0
            if any("H2" in h.name for h in hypos):
                score += 10.0
            if any("H3" in h.name for h in hypos):
                score += 10.0

        if len(scripts) >= 2:
            score += 10.0
        if len(scripts) >= 4:
            score += 10.0

        return min(100.0, score)

    def _score_action(self, a: dict[str, Any]) -> float:
        score = 0.0
        chars = a.get("characters", [])
        scripts = a.get("scripts", [])

        profile_exists = sum(1 for c in chars if c.get("profile_path"))
        score += min(25.0, profile_exists * 12.0)

        scripts_exist = sum(1 for s in scripts if s.get("script_path"))
        score += min(25.0, scripts_exist * 8.0)

        total_duration = sum(s.get("total_duration_s", 0) for s in scripts)
        score += min(20.0, total_duration * 0.5)

        stages = a.get("stages_covered", set())
        score += min(15.0, len(stages) * 5.0)

        scenes = sum(s.get("scene_count", 0) for s in scripts)
        score += min(15.0, scenes * 3.0)

        return min(100.0, score)

    def _score_e2e(self, a: dict[str, Any]) -> float:
        score = 0.0
        chars = a.get("characters", [])
        scripts = a.get("scripts", [])

        has_profile_export = any(Path(c.get("profile_path", "")).exists() for c in chars)
        if has_profile_export:
            score += 15.0

        scripts_on_disk = sum(1 for s in scripts if Path(s.get("script_path", "")).exists())
        score += min(20.0, scripts_on_disk * 5.0)

        stages = a.get("stages_covered", set())
        if "mvp" in stages:
            score += 15.0
        if "mixed" in stages:
            score += 15.0
        if "internalization" in stages:
            score += 15.0

        doc_stages = self.doc.metadata.get("detected_stages", [])
        coverage = len(stages) / max(len(doc_stages), 1)
        score += coverage * 20.0

        return min(100.0, score)

    def _score_mas(self, a: dict[str, Any]) -> float:
        score = 0.0
        chars = a.get("characters", [])

        if len(chars) >= 2:
            score += 20.0
        if len(chars) >= 3:
            score += 15.0

        char_archetypes = {c.get("archetype", "") for c in chars}
        score += min(20.0, len(char_archetypes) * 7.0)

        styles = {c.get("style_keywords", "") for c in chars}
        score += min(15.0, len(styles) * 5.0)

        crossover_scripts = [
            s
            for s in a.get("scripts", [])
            if "crossover" in s.get("title", "").lower() or "x" in s.get("char_id", "")
        ]
        if crossover_scripts:
            score += 20.0

        stages = a.get("stages_covered", set())
        if len(stages) >= 2:
            score += 10.0

        return min(100.0, score)

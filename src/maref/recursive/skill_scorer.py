from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class QualityScore:
    overall: float
    dimensions: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


_FRONTMATTER_WEIGHT = 0.25
_STRUCTURE_WEIGHT = 0.25
_CLARITY_WEIGHT = 0.20
_ACTIONABILITY_WEIGHT = 0.30
_QUALITY_THRESHOLD = 0.7


class SkillScorer:
    def score(self, raw_content: str, frontmatter: dict[str, Any] | None = None) -> QualityScore:
        if frontmatter is None:
            _, raw_fm = _split_frontmatter(raw_content)
            if raw_fm:
                frontmatter = yaml.safe_load(raw_fm) or {}
            else:
                frontmatter = {}

        fm_score, fm_reasons = self._score_frontmatter(frontmatter)
        struct_score, struct_reasons = self._score_structure(raw_content)
        clarity_score, clarity_reasons = self._score_clarity(raw_content)
        action_score, action_reasons = self._score_actionability(raw_content)

        overall = (
            fm_score * _FRONTMATTER_WEIGHT
            + struct_score * _STRUCTURE_WEIGHT
            + clarity_score * _CLARITY_WEIGHT
            + action_score * _ACTIONABILITY_WEIGHT
        )

        return QualityScore(
            overall=round(overall, 4),
            dimensions={
                "frontmatter": round(fm_score, 4),
                "structure": round(struct_score, 4),
                "clarity": round(clarity_score, 4),
                "actionability": round(action_score, 4),
            },
            reasons=fm_reasons + struct_reasons + clarity_reasons + action_reasons,
        )

    def is_quality(self, score: QualityScore, threshold: float = _QUALITY_THRESHOLD) -> bool:
        return score.overall >= threshold

    # ── dimension scorers ──────────────────────────────────────

    @staticmethod
    def _score_frontmatter(frontmatter: dict[str, Any]) -> tuple[float, list[str]]:
        reasons: list[str] = []
        score = 0.0

        name = frontmatter.get("name", "")
        desc = frontmatter.get("description", "")
        if name and len(str(name)) > 0:
            score += 0.5
            reasons.append(f"frontmatter: name='{name}'")
        else:
            reasons.append("frontmatter: name missing")

        if desc and len(str(desc).strip()) >= 10:
            score += 0.5
            reasons.append(f"frontmatter: description ok ({len(str(desc))} chars)")
        else:
            reasons.append(f"frontmatter: description too short ({len(str(desc))} chars)")

        return score, reasons

    @staticmethod
    def _score_structure(content: str) -> tuple[float, list[str]]:
        reasons: list[str] = []
        body = _strip_frontmatter(content)
        lines = body.split("\n")
        step_lines = [l for l in lines if l.strip().startswith("## Step") or l.strip().startswith("##Step")]
        step_count = len(step_lines)

        if step_count < 1:
            return 0.0, ["structure: no '## Step' headings found"]

        if step_count > 20:
            return 0.0, [f"structure: too many steps ({step_count} > 20)"]

        # Check each step has detail (bullets or text after heading)
        detail_lines = [l for l in lines if l.strip().startswith("- ") or l.strip().startswith("* ")]
        detail_ratio = len(detail_lines) / max(step_count, 1)

        base = min(1.0, step_count / 6.0) * 0.6  # up to 0.6 for 6+ steps
        detail_bonus = min(1.0, detail_ratio / 2.0) * 0.4  # up to 0.4 for 2+ details per step

        score = min(1.0, base + detail_bonus)
        reasons.append(f"structure: {step_count} steps, {len(detail_lines)} details (ratio={detail_ratio:.1f})")
        return score, reasons

    @staticmethod
    def _score_clarity(content: str) -> tuple[float, list[str]]:
        reasons: list[str] = []
        body = _strip_frontmatter(content)
        sentences = [s.strip() for s in body.replace("\n", " ").split(".") if len(s.strip()) > 5]

        if not sentences:
            return 0.0, ["clarity: no sentences found"]

        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
        vague_words = {"todo", "etc", "something", "stuff", "idk", "maybe", "sometime"}
        vague_count = sum(1 for s in sentences for w in s.lower().split() if w.strip(".,!?") in vague_words)

        clarity_score = 1.0
        vagueness_penalty = min(1.0, vague_count / max(len(sentences), 1))
        clarity_score -= vagueness_penalty * 0.5

        if avg_len > 30:
            clarity_score -= min(0.3, (avg_len - 30) / 100)
            reasons.append(f"clarity: long avg sentence ({avg_len:.0f} words)")
        else:
            clarity_score += 0.1

        clarity_score = max(0.0, min(1.0, clarity_score))
        reasons.append(f"clarity: {len(sentences)} sentences, avg {avg_len:.0f} words, {vague_count} vague words")
        return clarity_score, reasons

    @staticmethod
    def _score_actionability(content: str) -> tuple[float, list[str]]:
        reasons: list[str] = []
        score = 0.0

        has_code_block = "```" in content
        has_file_paths = any(p in content for p in ("/", ".py", ".ts", ".js", ".yaml", ".json", ".md"))
        has_cli = any(cmd in content for cmd in ("curl", "pytest", "docker", "kubectl", "git", "npm", "pip"))

        if has_code_block:
            score += 0.4
            reasons.append("actionability: has code blocks")
        if has_file_paths:
            score += 0.3
            reasons.append("actionability: has file paths")
        if has_cli:
            score += 0.3
            reasons.append("actionability: has CLI commands")

        return min(score, 1.0), reasons


# ── helpers ─────────────────────────────────────────────────


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Split content into (body, frontmatter_yaml) where frontmatter_yaml
    is the raw YAML string between --- delimiters (without the --- lines)."""
    stripped = content.strip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip(), parts[1].strip()
    return stripped, ""


def _strip_frontmatter(content: str) -> str:
    body, _ = _split_frontmatter(content)
    return body

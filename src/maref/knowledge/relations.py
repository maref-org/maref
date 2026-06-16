"""
MAREF Knowledge Graph Relations

Defines structured relation types and dual-channel extraction
(rule-based for speed + LLM for depth) to populate the knowledge
graph with meaningful edges instead of empty related_nodes arrays.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class RelationType(Enum):
    """Explicit relation types for knowledge graph edges."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CAUSES = "causes"
    SUGGESTS = "suggests"
    OBSERVES = "observes"
    PRECEDES = "precedes"
    TESTS = "tests"
    DERIVES = "derives"


@dataclass
class ExtractedRelation:
    """A relation triple extracted from natural language content."""

    subject_text: str
    relation: RelationType
    object_text: str
    confidence: float
    method: str  # "rule" or "llm"


# --- Rule-based extraction patterns ---

_CAUSAL_PATTERNS: list[tuple[str, RelationType]] = [
    (r"(导致|引起|造成|诱发|触发)", RelationType.CAUSES),
    (r"(因为|由于|根源是|原因是)", RelationType.CAUSES),
]

_CONTRADICTION_PATTERNS: list[tuple[str, RelationType]] = [
    (r"(矛盾|冲突|不一致|相反|与.+不符|违反)", RelationType.CONTRADICTS),
    (r"(推翻|否定|证伪)", RelationType.CONTRADICTS),
]

_SUPPORT_PATTERNS: list[tuple[str, RelationType]] = [
    (r"(证实|验证|支持|确认|吻合|符合|一致)", RelationType.SUPPORTS),
    (r"(与.+一致|增强)", RelationType.SUPPORTS),
]

_SUGGEST_PATTERNS: list[tuple[str, RelationType]] = [
    (r"(建议|推荐|应使用|可考虑|优先)", RelationType.SUGGESTS),
    (r"(发现.+应改善|需要.*优化)", RelationType.SUGGESTS),
]

_OBSERVE_PATTERNS: list[tuple[str, RelationType]] = [
    (r"(显示|表明|呈现|出现|检测到|观察到)", RelationType.OBSERVES),
    (r"(值为|等于|达到|下降|上升|FLUCTUATE)", RelationType.OBSERVES),
]


class RuleBasedExtractor:
    """Fast rule-based relation extraction using regex patterns."""

    _patterns: list[tuple[re.Pattern[str], RelationType]] = []

    def __init__(self) -> None:
        if not RuleBasedExtractor._patterns:
            all_rules = (
                _CAUSAL_PATTERNS
                + _CONTRADICTION_PATTERNS
                + _SUPPORT_PATTERNS
                + _SUGGEST_PATTERNS
                + _OBSERVE_PATTERNS
            )
            RuleBasedExtractor._patterns = [
                (re.compile(pattern), rel_type) for pattern, rel_type in all_rules
            ]

    def extract(self, text: str, candidates: list[str]) -> list[ExtractedRelation]:
        """
        Extract relations from text against candidate nodes.

        Args:
            text: The natural language content to analyze.
            candidates: List of candidate node texts to match against.

        Returns:
            List of extracted relation triples.
        """
        relations: list[ExtractedRelation] = []

        for pattern, rel_type in self._patterns:
            if pattern.search(text):
                for candidate in candidates:
                    candidate_lower = candidate.lower()
                    text_lower = text.lower()
                    shared = _shared_keyword_count(text_lower, candidate_lower)
                    if shared >= 2:
                        relations.append(
                            ExtractedRelation(
                                subject_text=text[:80],
                                relation=rel_type,
                                object_text=candidate[:80],
                                confidence=min(0.5 + shared * 0.1, 0.9),
                                method="rule",
                            )
                        )

        return relations[:10]


class LLMExtractor:
    """LLM-based relation extraction for high-value connections.

    Uses a lightweight prompt to extract structured triples.
    This is the 20% high-value path, used for findings with
    confidence > 0.7 or ambiguous rule-based results.
    """

    _prompt_template = """从以下研究发现中提取 (主语, 关系, 宾语) 三元组。

文本: {text}
候选概念: {candidates}

关系类型: supports, contradicts, causes, suggests, observes

返回 JSON 格式:
[{{"subject": "...", "relation": "supports", "object": "..."}}]

仅返回 JSON，不返回其他内容。"""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    async def extract(
        self,
        text: str,
        candidates: list[str],
    ) -> list[ExtractedRelation]:
        """Extract relations using LLM (async)."""
        if not self._client:
            return []

        prompt = self._prompt_template.format(
            text=text[:500],
            candidates=", ".join(candidates[:10]),
        )

        try:
            response = await self._client.chat(prompt, max_tokens=300)
            triples = self._parse_response(response)
            return [
                ExtractedRelation(
                    subject_text=t.get("subject", text[:80]),
                    relation=RelationType(t.get("relation", "observes")),
                    object_text=t.get("object", ""),
                    confidence=0.75,
                    method="llm",
                )
                for t in triples
            ]
        except Exception:
            return []

    @staticmethod
    def _parse_response(response: str) -> list[dict[str, str]]:
        import json

        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1])

        try:
            data = json.loads(response)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            bracket_idx = response.find("[")
            if bracket_idx >= 0:
                try:
                    return json.loads(response[bracket_idx:])
                except json.JSONDecodeError:
                    pass
            return []


def _shared_keyword_count(a: str, b: str) -> int:
    """Count shared meaningful keywords between two strings."""
    words_a = set(_tokenize(a))
    words_b = set(_tokenize(b))
    return len(words_a & words_b)


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer for Chinese/English mixed text."""
    tokens: list[str] = []
    current: list[str] = []

    for ch in text:
        if ch.isspace() or ch in ",.。，、;；:：!！?？()（）[]【】":
            if current:
                tokens.append("".join(current))
                current = []
            continue
        if 0x4E00 <= ord(ch) <= 0x9FFF:
            if current:
                tokens.append("".join(current))
                current = []
            tokens.append(ch)
        else:
            current.append(ch)

    if current:
        tokens.append("".join(current))

    return [t for t in tokens if len(t) >= 2 or (len(t) == 1 and 0x4E00 <= ord(t) <= 0x9FFF)]

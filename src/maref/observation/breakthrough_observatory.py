from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Priority definitions matching the 7-breakthrough matrix
PRIORITY_DEFS: dict[str, dict[str, Any]] = {
    "P0_human_machine_collab": {
        "title": "人机协同层",
        "impact": 9.5,
        "difficulty": 8.5,
        "roadmap": "v0.30-GA",
        "module": "maref.recursive.hitl_v2",
        "target_score": 0.85,
        "description": "解决 3% 人工仲裁瓶颈，实现真正自治",
    },
    "P1_memory_three_temp": {
        "title": "记忆三温框架",
        "impact": 9.0,
        "difficulty": 7.0,
        "roadmap": "v0.30-GA",
        "module": "maref.recursive.memory_three_temperature",
        "target_score": 0.85,
        "description": "突破上下文限制，长期记忆与经验传承",
    },
    "P2_agent_credit_rating": {
        "title": "Agent 信用评级",
        "impact": 8.5,
        "difficulty": 6.0,
        "roadmap": "v1.0",
        "module": "maref.recursive.agent_credit_rating",
        "target_score": 0.70,
        "description": "防御型治理→信用型治理",
    },
    "P3_skill_marketplace": {
        "title": "技能市场层",
        "impact": 9.5,
        "difficulty": 6.5,
        "roadmap": "v0.30-GA",
        "module": "maref.recursive.agent_marketplace",
        "target_score": 0.85,
        "description": "接入 84K+ 社区 skill 生态，RSI 优化经验可复用可交易",
    },
    "P4_trigrams_v2": {
        "title": "八卦治理模型",
        "impact": 7.0,
        "difficulty": 3.5,
        "roadmap": "v2.0",
        "module": "maref.recursive.eight_trigrams_governance",
        "target_score": 0.50,
        "description": "东方哲学+形式化验证，差异化竞争点",
    },
    "P5_carbon_silicon": {
        "title": "碳硅共生",
        "impact": 6.5,
        "difficulty": 7.0,
        "roadmap": "v2.0",
        "module": "maref.recursive.carbon_silicon_symbiosis",
        "target_score": 0.40,
        "description": "Human-AI Symbiosis，超越工具属性",
    },
    "P6_meta_agent_closure": {
        "title": "元 Agent 闭包",
        "impact": 6.0,
        "difficulty": 5.0,
        "roadmap": "v2.0",
        "module": "maref.recursive.meta_agent_closure",
        "target_score": 0.40,
        "description": "递归终止保障，哲学层面突破",
    },
}


@dataclass
class PriorityAssessment:
    priority_id: str
    title: str
    score: float
    target_score: float
    module: str
    module_loaded: bool
    module_status: str
    impact: float
    difficulty: float
    roadmap: str
    description: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def gap(self) -> float:
        return max(0.0, self.target_score - self.score)

    @property
    def progress_pct(self) -> float:
        if self.target_score <= 0:
            return 0.0
        return min(100.0, self.score / self.target_score * 100.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "priority_id": self.priority_id,
            "title": self.title,
            "score": round(self.score, 4),
            "target_score": self.target_score,
            "gap": round(self.gap, 4),
            "progress_pct": round(self.progress_pct, 1),
            "module": self.module,
            "module_loaded": self.module_loaded,
            "module_status": self.module_status,
            "impact": self.impact,
            "difficulty": self.difficulty,
            "roadmap": self.roadmap,
            "description": self.description,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class BreakthroughSnapshot:
    assessments: list[PriorityAssessment]
    aggregate_score: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "priorities": [a.to_dict() for a in self.assessments],
            "aggregate_score": round(self.aggregate_score, 4),
            "priority_count": len(self.assessments),
            "avg_progress_pct": round(
                sum(a.progress_pct for a in self.assessments) / max(len(self.assessments), 1),
                1,
            ),
            "timestamp": self.timestamp,
        }


class BreakthroughObservatory:
    """Probes the 7 breakthrough priorities and scores their progress."""

    def __init__(self) -> None:
        self._history: list[BreakthroughSnapshot] = []
        self._last_snapshot: BreakthroughSnapshot | None = None

    def _assess_priority(self, pid: str, config: dict[str, Any]) -> PriorityAssessment:
        title = config["title"]
        module_path = config["module"]
        target = config["target_score"]

        try:
            mod = __import__(module_path, fromlist=["_"])
            score, details = self._score_module(pid, mod)
            return PriorityAssessment(
                priority_id=pid,
                title=title,
                score=score,
                target_score=target,
                module=module_path,
                module_loaded=True,
                module_status="loaded",
                impact=config["impact"],
                difficulty=config["difficulty"],
                roadmap=config["roadmap"],
                description=config["description"],
                details=details,
            )
        except Exception as exc:
            return PriorityAssessment(
                priority_id=pid,
                title=title,
                score=0.0,
                target_score=target,
                module=module_path,
                module_loaded=False,
                module_status=f"error: {exc}",
                impact=config["impact"],
                difficulty=config["difficulty"],
                roadmap=config["roadmap"],
                description=config["description"],
                details={"error": str(exc)},
            )

    def _score_module(self, pid: str, mod: Any) -> tuple[float, dict[str, Any]]:
        details: dict[str, Any] = {}

        if pid == "P4_trigrams_v2":
            # EightTrigramsGovernance: extract trust score and trigram state
            try:
                gov = mod.EightTrigramsGovernance(agent_id="observatory")
                score = gov.trust_score
                details["current_trigram"] = gov.current_trigram.value
                details["trust_score"] = round(score, 4)
                details["config"] = gov.current_config
                return score, details
            except Exception as e:
                return 0.5, {"error": str(e), "note": "used default 0.5"}

        if pid == "P0_human_machine_collab":
            # HITL v2: check audit window completion rate
            try:
                auditor = mod.AdversarialAuditor()
                windows = getattr(auditor, "audit_windows", [])
                if windows:
                    completed = sum(1 for w in windows if w.completed)
                    score = completed / max(len(windows), 1)
                else:
                    score = 0.3
                details["audit_window_count"] = len(windows)
                return min(score, 1.0), details
            except Exception:
                return 0.4, {"note": "hitl_v2 loaded, status check fallback"}

        if pid == "P1_memory_three_temp":
            # MemoryThreeTemperature: health scores
            try:
                health = mod.MemoryHealthScore(
                    hit_rate=0.0, decay_rate=0.0, fragmentation=0.0
                )
                details["module"] = "MemoryHealthScore available"
                return 0.3, details
            except Exception:
                return 0.2, {"note": "memory module available"}

        if pid == "P2_agent_credit_rating":
            # AgentCreditRating: rating levels
            try:
                ratings = list(mod.CreditRating)
                details["rating_count"] = len(ratings)
                details["ratings"] = [r.value for r in ratings]
                return 0.4, details
            except Exception:
                return 0.3, {"note": "credit rating module available"}

        if pid == "P3_skill_marketplace":
            # AgentMarketplace: listings
            try:
                marketplace = mod.AgentMarketplace()
                listings = getattr(marketplace, "listings", [])
                score = min(len(listings) / 10.0, 1.0)
                details["listing_count"] = len(listings)
                return score, details
            except Exception:
                return 0.2, {"note": "marketplace module available"}

        if pid == "P5_carbon_silicon":
            # CarbonSiliconSymbiosis: workflow stages
            try:
                stages = list(mod.WorkflowStage)
                details["stage_count"] = len(stages)
                details["stages"] = [s.value for s in stages]
                return 0.3, details
            except Exception:
                return 0.2, {"note": "symbiosis module available"}

        if pid == "P6_meta_agent_closure":
            # MetaAgentClosure: invariants and decisions
            try:
                inv_count = len(list(mod.InvariantStatus))
                dec_count = len(list(mod.EvolutionDecisionType))
                details["invariant_count"] = inv_count
                details["decision_types"] = dec_count
                return 0.3, details
            except Exception:
                return 0.2, {"note": "meta_closure module available"}

        return 0.0, {"note": f"no scoring logic for {pid}"}

    def snapshot(self) -> BreakthroughSnapshot:
        assessments = [
            self._assess_priority(pid, cfg) for pid, cfg in PRIORITY_DEFS.items()
        ]
        agg = (
            sum(a.score * a.impact for a in assessments)
            / max(sum(a.impact for a in assessments), 1)
        )
        snap = BreakthroughSnapshot(assessments=assessments, aggregate_score=agg)
        self._history.append(snap)
        self._last_snapshot = snap
        return snap

    def get_history(self, n: int = 10) -> list[BreakthroughSnapshot]:
        return self._history[-n:]

    @property
    def aggregate_score(self) -> float:
        if self._last_snapshot is not None:
            return self._last_snapshot.aggregate_score
        return 0.0

    def get_delta(self) -> dict[str, float]:
        if len(self._history) < 2:
            return {}
        prev = self._history[-2].aggregate_score
        curr = self._history[-1].aggregate_score
        return {"aggregate_delta": round(curr - prev, 4)}

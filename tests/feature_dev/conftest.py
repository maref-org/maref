from __future__ import annotations

from typing import Any

import pytest

from maref.integration.feature_dev.doc_ingestor import (
    ComplianceRule,
    CostModel,
    DeployStage,
    DocumentSection,
    FeatureDocument,
    Hypothesis,
)
from maref.integration.feature_dev.feature_cycle import CycleSnapshot
from maref.integration.test_platform.schema import EvalStatus


@pytest.fixture
def sample_markdown() -> str:
    return """# AI-Native IP Kingdom

## §1.5 Core Hypotheses

| Hypothesis | Method | Pass Threshold | Fail Criterion |
|---|---|---|---|
| **H1** | A/B test | >80% retention | <50% retention |
| **H2** | User study | >70% satisfaction | <40% satisfaction |
| **H3** | Analytics | >60% engagement | <30% engagement |

## §1.6 Decision Matrix (Go)

Daily check: - [x] Automated tests pass
Weekly: - [ ] Performance review

## MVP Phase (0-4 weeks)

- 里程碑: Character design complete
- 里程碑: First script written
- ✅ Must implement character system
- must have export pipeline
- should support theme switching

## Mixed Period (1-3 months)

- 里程碑: Multi-episode arc complete
- 里程碑: Crossover content produced

## Internalization (3-12 months)

| 成本项 | Tool A | Tool B |
|---|---|---|
| **Scene Gen** | ¥500 | ¥300 |
| **Audio** | ¥200 | ¥150 |

1. **Security Compliance**
2. **Data Privacy**
- [x] Daily audit check
- [ ] Weekly review

## Tools Table

| 工具 | Cost | Type |
|---|---|---|
| FFmpeg | ¥100 | render |
| Python | ¥0 | script |
"""


@pytest.fixture
def valid_feature_doc() -> FeatureDocument:
    return FeatureDocument(
        title="Test Feature",
        raw_path="/tmp/test.md",
        stages={
            DeployStage.MVP: [
                DocumentSection(
                    heading="MVP Phase",
                    level=2,
                    content="MVP content",
                    milestones=["Milestone 1"],
                    requirements=["req1", "req2"],
                ),
            ],
            DeployStage.MIXED: [
                DocumentSection(
                    heading="Mixed Period",
                    level=2,
                    content="Mixed content",
                    milestones=["Milestone 2"],
                    requirements=["req3"],
                ),
            ],
        },
        hypotheses=[
            Hypothesis(name="H1", method="A/B test", pass_threshold=">80%", fail_criterion="<50%"),
            Hypothesis(
                name="H2", method="User study", pass_threshold=">70%", fail_criterion="<40%"
            ),
            Hypothesis(name="H3", method="Analytics", pass_threshold=">60%", fail_criterion="<30%"),
        ],
        compliance_rules=[
            ComplianceRule(rule_id="discipline_1", description="Security", category="discipline"),
            ComplianceRule(
                rule_id="checklist_1",
                description="Daily audit",
                category="daily",
                is_automated=True,
            ),
            ComplianceRule(
                rule_id="checklist_2",
                description="Weekly review",
                category="weekly",
                is_automated=True,
            ),
        ],
        cost_models=[
            CostModel(stage="Scene Gen", items={"Tool A": 500.0, "Tool B": 300.0}, total=800.0),
            CostModel(stage="Audio", items={"Tool A": 200.0, "Tool B": 150.0}, total=350.0),
        ],
        metadata={
            "char_count": 500,
            "section_count": 3,
            "detected_stages": ["mvp", "mixed"],
            "extracted_requirements": 3,
            "extracted_milestones": 2,
            "hypotheses_found": 3,
            "compliance_rules_found": 3,
            "cost_models_found": 2,
        },
    )


@pytest.fixture
def sample_artifacts() -> dict[str, Any]:
    return {
        "cycle": 1,
        "characters": [
            {
                "char_id": "char-1",
                "name": "Neon-chan",
                "archetype": "The Trickster",
                "backstory": "Corporate espionage AI gained sentience",
                "setting": "Neo-Tokyo 2187",
                "style_keywords": "cyberpunk",
                "profile_path": "/tmp/char-1/profile.md",
            },
            {
                "char_id": "char-2",
                "name": "Sylvara",
                "archetype": "The Guardian",
                "backstory": "Last ranger of the Emerald Wild",
                "setting": "Emerald Wild",
                "style_keywords": "fantasy",
                "profile_path": "/tmp/char-2/profile.md",
            },
        ],
        "scripts": [
            {
                "char_id": "char-1",
                "episode_number": 1,
                "title": "Episode 1",
                "scene_count": 3,
                "total_duration_s": 37,
                "script_path": "/tmp/ep-1.md",
            },
            {
                "char_id": "char-2",
                "episode_number": 1,
                "title": "Episode 1",
                "scene_count": 3,
                "total_duration_s": 37,
                "script_path": "/tmp/ep-2.md",
            },
        ],
        "exports": [],
        "stages_covered": {"mvp"},
        "requirements_covered": 10,
    }


@pytest.fixture
def sample_snapshot() -> CycleSnapshot:
    return CycleSnapshot(
        cycle_number=1,
        topic="Test topic",
        layer_scores={
            "Static Audit": 70.0,
            "Reasoning Metrics": 65.0,
            "Action Metrics": 80.0,
            "E2E Metrics": 60.0,
            "MAS Dimensions": 55.0,
        },
        overall_score=66.0,
        overall_status=EvalStatus.CONDITIONAL,
        verdict="approved",
        feedback_injected="Add more characters",
        duration_seconds=12.5,
        artifacts={
            "characters": [{"name": "Char1"}, {"name": "Char2"}],
            "scripts": [{"title": "Ep1"}, {"title": "Ep2"}, {"title": "Ep3"}],
            "stages_covered": {"mvp", "mixed"},
            "requirements_covered": 5,
        },
        go_nogo_decision="CONTINUE",
        budget_used=100.0,
        llm_used=True,
    )

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
    return """# Secure API Gateway

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

- 里程碑: Auth module complete
- 里程碑: Rate limiting implemented
- ✅ Must implement JWT verification
- must have audit logging
- should support tenant isolation

## Mixed Period (1-3 months)

- 里程碑: Multi-region deployment complete
- 里程碑: Browser-based admin console

## Internalization (3-12 months)

| 成本项 | Tool A | Tool B |
|---|---|---|
| **Ingress** | ¥500 | ¥300 |
| **Secrets** | ¥200 | ¥150 |

1. **Security Compliance**
2. **Data Privacy**
- [x] Daily audit check
- [ ] Weekly review

## Tools Table

| 工具 | Cost | Type |
|---|---|---|
| OpenTelemetry | ¥100 | observability |
| Python | ¥0 | service |
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
            CostModel(stage="Ingress", items={"Tool A": 500.0, "Tool B": 300.0}, total=800.0),
            CostModel(stage="Secrets", items={"Tool A": 200.0, "Tool B": 150.0}, total=350.0),
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
        "improvement_plan": [
            "Implement JWT verification",
            "Add audit logging",
            "Cover tenant isolation",
        ],
        "stages_covered": {"mvp"},
        "requirements_covered": 3,
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
        feedback_injected="Add more plan items",
        duration_seconds=12.5,
        artifacts={
            "improvement_plan": ["Implement JWT", "Add logging", "Cover isolation"],
            "stages_covered": {"mvp", "mixed"},
            "requirements_covered": 5,
        },
        go_nogo_decision="CONTINUE",
        budget_used=100.0,
        llm_used=True,
    )

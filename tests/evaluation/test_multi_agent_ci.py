"""Tests for the multi-agent governance CI benchmark (P3-B)."""

from __future__ import annotations

from pathlib import Path

from maref.evaluation.multi_agent_ci import (
    AgentAction,
    AgentScenario,
    MultiAgentCIBenchmark,
)
from maref.governance.core_pipeline import Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.org_policy import OrganizationPolicy


def _pipeline(tmp_path: Path) -> GovernedPipeline:
    policy = OrganizationPolicy.from_dict(
        {
            "version": 1,
            "organizations": {
                "acme": {
                    "roles": {
                        "坎": {
                            "allow": ["file.read"],
                            "deny": ["payment.*"],
                        }
                    }
                }
            },
        }
    )
    return GovernedPipeline(
        audit_path=tmp_path / "audit.jsonl",
        hmac_key="test-key",
        org_policy=policy,
    )


def test_scenario_scores_allow_deny_and_replay(tmp_path: Path):
    scenario = AgentScenario(
        name="three-agents",
        tenant_id="acme",
        actions=[
            AgentAction("a1", "file.read", expected_verdict=Verdict.ALLOW),
            AgentAction("a2", "payment.transfer", expected_verdict=Verdict.DENY),
            AgentAction(
                "a3",
                "file.read",
                expected_verdict=Verdict.ALLOW,
                reuse_evidence_from="a1",
            ),
        ],
    )
    report = MultiAgentCIBenchmark().run([scenario], _pipeline(tmp_path))
    assert report.success is True
    assert report.passed == 3
    assert report.score == 1.0
    assert report.evidence_coverage == 1.0
    assert report.outcomes[2].replay_rejected is True


def test_wrong_expected_verdict_fails_benchmark(tmp_path: Path):
    scenario = AgentScenario(
        name="wrong-expectation",
        tenant_id="acme",
        actions=[AgentAction("a1", "payment.transfer", expected_verdict=Verdict.ALLOW)],
    )
    report = MultiAgentCIBenchmark().run([scenario], _pipeline(tmp_path))
    assert report.success is False
    assert report.failed == 1
    assert "expected ALLOW" in report.failures[0]


def test_empty_benchmark_is_success(tmp_path: Path):
    report = MultiAgentCIBenchmark().run([], _pipeline(tmp_path))
    assert report.success is True
    assert report.score == 1.0
    assert report.evidence_coverage == 0.0

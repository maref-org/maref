"""v0.48 W1 — GovernedPipeline unified governance assembly.

``GovernedPipeline`` (v0.47-era) already assembles audit/hitl/permission/cb.
W1 extends it to wire in the v0.47 governance gates so a single assembly
gives the full closed loop:
  - TrustBoundaryManager (S9) injected into the pipeline;
  - TaskPreflight (S11) available for task-level preflight;
  - RuntimeBehaviorProbe (S10) wired to the audit bus;
  - FederatedConsensus with membership (F2) for federated decisions.
"""

from __future__ import annotations

from pathlib import Path

from maref.governance.core_pipeline import GovernanceRequest, Verdict


class TestGovernedPipelineAssembly:
    def test_assembly_injects_trust_boundary(self, tmp_path: Path) -> None:
        from maref.governance.governed_pipeline import GovernedPipeline

        gp = GovernedPipeline(audit_path=str(tmp_path / "audit.jsonl"))
        # A HIGH-risk action with no scope is denied by the injected boundary.
        result = gp.pipeline.govern(
            GovernanceRequest(
                action="file.delete", agent_id="agent-a", trust_score=90, role=""
            )
        )
        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "trust_boundary"

    def test_assembly_exposes_task_preflight(self, tmp_path: Path) -> None:
        from maref.governance.governed_pipeline import GovernedPipeline

        gp = GovernedPipeline(audit_path=str(tmp_path / "audit.jsonl"))
        assert gp.task_preflight is not None

    def test_assembly_wires_behavior_probe(self, tmp_path: Path) -> None:
        from maref.governance.governed_pipeline import GovernedPipeline

        gp = GovernedPipeline(audit_path=str(tmp_path / "audit.jsonl"))
        assert gp.behavior_probe is not None
        assert gp.behavior_probe.started is True

    def test_assembly_wires_federated_consensus(self, tmp_path: Path) -> None:
        from maref.governance.governed_pipeline import GovernedPipeline

        gp = GovernedPipeline(audit_path=str(tmp_path / "audit.jsonl"))
        assert gp.consensus is not None

    def test_default_behavior_backward_compatible(self, tmp_path: Path) -> None:
        """An in-scope low-risk action still passes (existing behaviour)."""
        from maref.governance.governed_pipeline import GovernedPipeline

        gp = GovernedPipeline(audit_path=str(tmp_path / "audit.jsonl"))
        result = gp.pipeline.govern(
            GovernanceRequest(
                action="file.read", agent_id="agent-a", trust_score=80, role=""
            )
        )
        assert result.verdict == Verdict.ALLOW

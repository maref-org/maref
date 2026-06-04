from __future__ import annotations

import tempfile

from maref.recursive.complexity_budget import ArchitectureComplexityBudget
from maref.recursive.continuous_optimizer import ContinuousOptimizer
from maref.recursive.correlation_engine import CorrelationEngine
from maref.recursive.live_migration import LiveMigration
from maref.recursive.self_architect import SelfArchitect
from maref.recursive.self_executor import SelfExecutor
from maref.recursive.signed_agent_cards import (
    AgentCardSigner,
    SignedAgentCard,
    SignedAgentCardStore,
)
from maref.recursive.unified_audit import UnifiedAuditStore


class TestR40FullProcessRegression:
    def test_full_closed_loop_pipeline(self) -> None:
        audit = UnifiedAuditStore()
        tmpdir = tempfile.mkdtemp()

        step1_architect = SelfArchitect(audit_store=audit)
        step1_architect.snapshot_architecture({"maref": {"files": 35, "tests": 1391}})
        prop = step1_architect.propose_redesign()
        assert prop is not None, "Step 1: SelfArchitect generated a proposal"

        step2_executor = SelfExecutor(max_rounds=1, project_root=tmpdir, audit_store=audit)
        pipeline = step2_executor.execute(prop, round_num=40)
        assert pipeline.final_state in (
            "SUCCESS",
            "FAILED_VERIFY_ROLLED_BACK",
            "FAILED_SAFETY_GATE",
        ), f"Step 2: Execution pipeline state = {pipeline.final_state}"
        assert len(step2_executor.history) >= 1, "Step 2: Execution recorded in history"

        step3_corr = CorrelationEngine(audit_store=audit)
        span_id = f"r40_span_{pipeline.pipeline_id}"
        audit_id = f"r40_audit_{pipeline.pipeline_id}"
        exp_id = f"r40_exp_{pipeline.pipeline_id}"

        step3_corr.link_all(span_id, audit_id, exp_id, round_num=40)
        assert step3_corr.link_count == 1, "Step 3: Correlation link created"

        trace = step3_corr.query_full_trace(span_id, "span")
        assert trace.hop_count <= 5, (
            f"Step 3: Full trace in {trace.hop_count} hops (must be ≤ 5)"
        )
        assert trace.complete, (
            f"Step 3: Trace complete={trace.complete}, "
            f"spans={len(trace.span_ids)}, audits={len(trace.audit_ids)}, "
            f"exps={len(trace.experience_ids)}"
        )

        step4_budget = ArchitectureComplexityBudget(audit_store=audit)
        step4_budget.register_edge("self_executor", "safety_gate", "import")
        step4_budget.register_edge("self_executor", "unified_audit", "import")
        step4_budget.register_edge("correlation_engine", "unified_audit", "import")
        report = step4_budget.get_global_report()
        assert report.total_modules >= 2, f"Step 4: Budget tracks {report.total_modules} modules"
        assert not step4_budget.is_module_blocked("self_executor"), "Step 4: Executor not blocked"

        step5_optimizer = ContinuousOptimizer(audit_store=audit)
        step5_optimizer.run_cycle({
            "coverage": 96.25,
            "test_count": 1391.0,
            "self_executor_coverage": 90.0,
        })
        assert step5_optimizer.health_check()["total_cycles"] >= 1, "Step 5: Optimizer ran cycles"

        step7_migration = LiveMigration(project_root=tmpdir, audit_store=audit)
        plan = step7_migration.plan_migration("0.5.0", "0.6.0")
        dry_result = step7_migration.dry_run(plan)
        assert dry_result["estimated_ok"], "Step 6: Migration dry-run estimates OK"
        assert dry_result["compatibility"] != "unknown", (
            f"Step 6: Compatibility = {dry_result['compatibility']}"
        )

        step8_signer = AgentCardSigner()
        step8_signer.register_key("maref_executor", "public_key_r40")
        card = SignedAgentCard(
            card_id="r40_card",
            agent_id="maref_executor",
            agent_name="MAREF v0.6.0 Executor",
            capabilities=["self_execute", "correlate", "migrate", "optimize"],
            trust_score=0.95,
            version="0.6.0",
        )
        step8_signer.sign_card(card, "private_key_r40")
        assert step8_signer.verify_card(card), "Step 7: Signed agent card verified"

        store = SignedAgentCardStore(audit_store=audit)
        store.register(card)
        assert store.valid_count >= 1, "Step 7: Valid cards in store"

        final_audit_count = audit.count()
        assert final_audit_count >= 8, (
            f"R40 Complete: Total audit records = {final_audit_count} (expected ≥ 8)"
        )

    def test_r40_trace_completeness(self) -> None:
        audit = UnifiedAuditStore()
        corr = CorrelationEngine(audit_store=audit)

        for i in range(5):
            corr.link_all(f"span_{i}", f"audit_{i}", f"exp_{i}", round_num=40 + i)

        assert corr.link_count == 5

        report = corr.get_completeness_report()
        assert report["total_links"] == 5
        assert report["fully_linked"] == 5
        assert report["orphan_spans"] == 0
        assert report["orphan_audits"] == 0
        assert report["orphan_experiences"] == 0

    def test_r40_complexity_budget_pipeline(self) -> None:
        audit = UnifiedAuditStore()
        budget = ArchitectureComplexityBudget(audit_store=audit)

        modules = [
            "self_executor", "correlation_engine", "continuous_optimizer",
            "signed_agent_cards", "live_migration", "self_architect",
            "safety_gate", "unified_audit", "self_diagnostician",
            "self_healer",
        ]

        for i, mod in enumerate(modules):
            for j in range(min(i + 1, 4)):
                budget.register_edge(mod, f"dep_{j}", "import")

        report = budget.get_global_report()
        assert report.total_modules >= 8, f"All {report.total_modules} modules tracked"
        assert report.global_status in ("HEALTHY", "WARNING"), f"Global: {report.global_status}"

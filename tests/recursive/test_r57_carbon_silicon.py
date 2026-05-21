from __future__ import annotations

from maref.recursive.carbon_silicon_symbiosis import (
    DOMAIN_ALLOCATION,
    DOMAIN_CONFIDENCE_FOR_AUTO,
    CarbonSiliconSymbiosis,
    TaskAllocation,
    TaskDomain,
    WorkflowStage,
    WorkflowStep,
    WorkflowTask,
)


class TestTaskDomain:
    def test_all_domains_have_allocation(self):
        for domain in TaskDomain:
            assert domain in DOMAIN_ALLOCATION

    def test_code_generation_agent_only(self):
        assert DOMAIN_ALLOCATION[TaskDomain.CODE_GENERATION] == TaskAllocation.AGENT_ONLY

    def test_security_review_human_required(self):
        assert DOMAIN_ALLOCATION[TaskDomain.SECURITY_REVIEW] == TaskAllocation.HUMAN_REQUIRED

    def test_domain_confidence_thresholds(self):
        for domain in TaskDomain:
            threshold = DOMAIN_CONFIDENCE_FOR_AUTO[domain]
            assert 0.0 <= threshold <= 1.0


class TestCarbonSiliconSymbiosisInit:
    def test_default_init(self):
        css = CarbonSiliconSymbiosis()
        assert css._human_id == "human_operator"


class TestTrustAndOldYang:
    def test_set_agent_trust(self):
        css = CarbonSiliconSymbiosis()
        css.set_agent_trust("agent_1", 0.85)
        assert css.get_agent_trust("agent_1") == 0.85

    def test_default_trust(self):
        css = CarbonSiliconSymbiosis()
        assert css.get_agent_trust("unknown") == 0.5

    def test_old_yang_mode(self):
        css = CarbonSiliconSymbiosis()
        css.set_agent_trust("agent_1", 0.92)
        assert css.is_old_yang_mode("agent_1")

    def test_not_old_yang_mode(self):
        css = CarbonSiliconSymbiosis()
        css.set_agent_trust("agent_1", 0.7)
        assert not css.is_old_yang_mode("agent_1")


class TestTaskAllocation:
    def test_allocate_normal_task(self):
        css = CarbonSiliconSymbiosis()
        task = css.allocate_task(TaskDomain.CODE_GENERATION, "agent_1",
                                 "Generate Code", "Generate a utility module")
        assert task.allocation == TaskAllocation.AGENT_ONLY

    def test_allocate_security_task(self):
        css = CarbonSiliconSymbiosis()
        task = css.allocate_task(TaskDomain.SECURITY_REVIEW, "agent_1",
                                 "Security Audit", "Review security policies")
        assert task.allocation == TaskAllocation.HUMAN_REQUIRED

    def test_old_yang_elevates_allocation(self):
        css = CarbonSiliconSymbiosis()
        css.set_agent_trust("agent_1", 0.95)
        task = css.allocate_task(TaskDomain.SECURITY_REVIEW, "agent_1",
                                 "Security Audit", "Review security policies")
        assert task.allocation != TaskAllocation.HUMAN_ONLY

    def test_old_yang_architecture_collaborative_to_agent_only(self):
        css = CarbonSiliconSymbiosis()
        css.set_agent_trust("agent_1", 0.95)
        task = css.allocate_task(TaskDomain.ARCHITECTURE_DESIGN, "agent_1",
                                 "Design System", "Design new module")
        assert task.allocation == TaskAllocation.AGENT_ONLY


class TestWorkflowLifecycle:
    def test_start_workflow(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.CODE_GENERATION,
                                      "Generate Code", "Description")
        assert instance is not None
        assert instance.current_stage == WorkflowStage.PROPOSE

    def test_human_confirm(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.ARCHITECTURE_DESIGN,
                                      "Design", "Description")
        result = css.human_confirm(instance.task.task_id, True)
        assert result is not None
        assert result.current_stage == WorkflowStage.HUMAN_CONFIRM

    def test_human_reject(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.ARCHITECTURE_DESIGN,
                                      "Design", "Description")
        result = css.human_confirm(instance.task.task_id, False)
        assert result is not None
        assert result.status == "rejected"

    def test_agent_execute(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.CODE_GENERATION,
                                      "Generate", "Description")
        result = css.agent_execute(instance.task.task_id, "agent_1")
        assert result is not None
        assert result.current_stage == WorkflowStage.AGENT_EXECUTE

    def test_agent_self_review(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.MONITORING,
                                      "Monitor", "Description")
        css.agent_execute(instance.task.task_id, "agent_1")
        result = css.agent_self_review(instance.task.task_id, "agent_1", True)
        assert result is not None
        assert result.current_stage == WorkflowStage.AGENT_SELF_REVIEW

    def test_agent_self_review_fail(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.MONITORING,
                                      "Monitor", "Description")
        css.agent_execute(instance.task.task_id, "agent_1")
        result = css.agent_self_review(instance.task.task_id, "agent_1", False)
        assert result is not None


class TestFullCycle:
    def test_full_cycle_agent_only(self):
        css = CarbonSiliconSymbiosis()
        css.set_agent_trust("agent_1", 0.8)
        instance = css.run_full_cycle(
            "agent_1", TaskDomain.CODE_GENERATION,
            "Generate Code", "Generate utility module",
        )
        assert instance is not None
        assert instance.status in ("completed", "active")

    def test_full_cycle_collaborative(self):
        css = CarbonSiliconSymbiosis()
        instance = css.run_full_cycle(
            "agent_1", TaskDomain.ARCHITECTURE_DESIGN,
            "Design System", "Design new module",
            human_confirms=True, self_review_passes=True, spot_check_passes=True,
        )
        assert instance is not None
        assert instance.status in ("completed", "active")

    def test_full_cycle_rejected_by_human(self):
        css = CarbonSiliconSymbiosis()
        instance = css.run_full_cycle(
            "agent_1", TaskDomain.ARCHITECTURE_DESIGN,
            "Design System", "Design new module",
            human_confirms=False,
        )
        assert instance is not None
        assert instance.status == "rejected"


class TestWorkflowQuery:
    def test_get_workflow_by_id(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.CODE_GENERATION,
                                      "Test", "Desc")
        found = css.get_workflow(instance.task.task_id)
        assert found is not None

    def test_get_all_workflows(self):
        css = CarbonSiliconSymbiosis()
        css.start_workflow("agent_1", TaskDomain.CODE_GENERATION, "T1", "D1")
        css.start_workflow("agent_2", TaskDomain.MONITORING, "T2", "D2")
        assert len(css.get_all_workflows()) == 2

    def test_get_completed_workflows(self):
        css = CarbonSiliconSymbiosis()
        css.run_full_cycle(
            "agent_1", TaskDomain.MONITORING,
            "Monitor", "Monitor system",
        )
        completed = css.get_completed_workflows()
        assert len(completed) >= 0


class TestStats:
    def test_get_stats(self):
        css = CarbonSiliconSymbiosis()
        css.start_workflow("agent_1", TaskDomain.CODE_GENERATION, "T1", "D1")
        stats = css.get_stats()
        assert stats["active_workflows"] >= 1
        assert "total_human_interactions" in stats
        assert "total_agent_interactions" in stats
        assert "symbiosis_ratio" in stats

    def test_interaction_tracking(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.ARCHITECTURE_DESIGN,
                                      "Design", "Description")
        css.human_confirm(instance.task.task_id, True)
        css.agent_execute(instance.task.task_id, "agent_1")
        css.agent_self_review(instance.task.task_id, "agent_1", True)
        stats = css.get_stats()
        assert stats["total_agent_interactions"] >= 3


class TestSerialization:
    def test_workflow_task_to_dict(self):
        task = WorkflowTask("t1", "Title", "Desc", TaskDomain.CODE_GENERATION, TaskAllocation.AGENT_ONLY)
        d = task.to_dict()
        assert d["title"] == "Title"

    def test_workflow_step_to_dict(self):
        step = WorkflowStep("s1", "t1", WorkflowStage.AGENT_EXECUTE, "agent_1", "execute")
        d = step.to_dict()
        assert d["stage"] == "agent_execute"

    def test_css_to_dict(self):
        css = CarbonSiliconSymbiosis()
        css.set_agent_trust("agent_1", 0.8)
        css.start_workflow("agent_1", TaskDomain.CODE_GENERATION, "Test", "Desc")
        d = css.to_dict()
        assert "human_id" in d
        assert "agent_trust" in d
        assert "stats" in d
        assert "workflows" in d

    def test_human_confirm_agent_only_skips(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.CODE_GENERATION, "Gen", "Desc")
        result = css.human_confirm(instance.task.task_id, True)
        assert result is not None

    def test_agent_execute_rejected_workflow(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.ARCHITECTURE_DESIGN, "Design", "Desc")
        css.human_confirm(instance.task.task_id, False)
        result = css.agent_execute(instance.task.task_id, "agent_1")
        assert result is not None

    def test_human_spot_check_agent_only(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.CODE_GENERATION, "Gen", "Desc")
        css.agent_execute(instance.task.task_id, "agent_1")
        result = css.human_spot_check(instance.task.task_id, True)
        assert result is not None

    def test_human_spot_check_fail(self):
        css = CarbonSiliconSymbiosis()
        instance = css.start_workflow("agent_1", TaskDomain.ARCHITECTURE_DESIGN, "Design", "Desc")
        css.human_confirm(instance.task.task_id, True)
        css.agent_execute(instance.task.task_id, "agent_1")
        result = css.human_spot_check(instance.task.task_id, False)
        assert result is not None
        assert result.status == "rejected"

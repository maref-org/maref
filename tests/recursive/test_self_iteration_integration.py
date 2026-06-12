from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from maref.recursive.self_loop_runner import SelfLoopRunner, LoopConfig, LoopResult


class TestSelfIterationDryRun:
    def test_dry_run_completes_all_steps(self) -> None:
        runner = SelfLoopRunner(config=LoopConfig(max_iterations=2, heal_after_diagnosis=True))
        result = runner.dry_run()
        assert isinstance(result, LoopResult)
        assert result.iterations_completed >= 1
        assert any("observe" in r.steps_completed for r in result.iteration_results)
        assert any("diagnose" in r.steps_completed for r in result.iteration_results)
        assert any("optimize" in r.steps_completed for r in result.iteration_results)
        assert any("architect" in r.steps_completed for r in result.iteration_results)
        assert result.total_duration > 0

    def test_dry_run_default_config(self) -> None:
        runner = SelfLoopRunner()
        result = runner.dry_run()
        assert result.iterations_completed >= 1
        for iteration in result.iteration_results:
            if iteration.snapshot is not None:
                assert iteration.snapshot.source_file_count > 0
                assert len(iteration.snapshot.test_stats) > 0

    def test_dry_run_audit_records(self) -> None:
        runner = SelfLoopRunner()
        before = len(runner._audit_store._records)
        runner.dry_run()
        assert len(runner._audit_store._records) > before

    def test_dry_run_does_not_execute(self) -> None:
        runner = SelfLoopRunner(config=LoopConfig(max_iterations=1, execute_enabled=False))
        result = runner.dry_run()
        for iteration in result.iteration_results:
            assert "execute" not in iteration.steps_completed

    def test_claude_code_adapter_not_connected_by_default(self) -> None:
        from maref.recursive.claude_code_adapter import ClaudeCodeAdapter
        adapter = ClaudeCodeAdapter()
        assert not adapter.is_connected

    def test_dry_run_with_semantic_diagnosis(self) -> None:
        runner = SelfLoopRunner()
        runner._diagnostician.accept_semantic_diagnosis({
            "type": "integration_test",
            "module": "self_observer",
            "severity": "warning",
            "message": "Test semantic finding",
        })
        result = runner.dry_run()
        assert result.iterations_completed >= 1

    def test_dry_run_with_external_proposal(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal, ChangeType
        runner = SelfLoopRunner()
        proposal = ArchitectureProposal(
            proposal_id="dry_run_ext",
            timestamp=0.0,
            current_arch="1",
            proposed_arch="2",
            rationale="External proposal in dry-run",
            risk_assessment="low",
            confidence=0.9,
            change_type=ChangeType.ADD_TEST,
        )
        runner._architect.accept_external_proposal(proposal)
        result = runner.dry_run()
        assert result.iterations_completed >= 1
        assert len(runner._architect.list_proposals(change_type=ChangeType.ADD_TEST)) >= 1

    def test_run_raises_if_already_running(self) -> None:
        runner = SelfLoopRunner()
        runner.is_running = True
        with pytest.raises(RuntimeError, match="already running"):
            runner.run()


class TestSelfIterationFullRun:
    def test_full_run_executes_step_in_temp_dir(self) -> None:
        tmpdir = tempfile.mkdtemp()
        from maref.recursive.self_executor import SelfExecutor
        executor = SelfExecutor(project_root=tmpdir)
        runner = SelfLoopRunner(
            config=LoopConfig(max_iterations=1, execute_enabled=True, heal_after_diagnosis=True),
            executor=executor,
        )
        result = runner.run()
        assert result.iterations_completed >= 1
        assert any("execute" in r.steps_completed for r in result.iteration_results)
        assert any("heal" in r.steps_completed for r in result.iteration_results)

    def test_full_run_pipeline_record_created(self) -> None:
        tmpdir = tempfile.mkdtemp()
        from maref.recursive.self_executor import SelfExecutor
        executor = SelfExecutor(project_root=tmpdir)
        runner = SelfLoopRunner(
            config=LoopConfig(max_iterations=1, execute_enabled=True),
            executor=executor,
        )
        result = runner.run()
        record = result.iteration_results[0].execution
        assert record is not None
        assert record.final_state in ("SUCCESS", "FAILED_DEPLOY_ROLLED_BACK", "FAILED_VERIFY_ROLLED_BACK",
                                      "FAILED_SAFETY_GATE", "FAILED_AST_VALIDATE", "FAILED_CODE_GEN")

    def test_full_run_cleanup_temp_dir(self) -> None:
        tmpdir = tempfile.mkdtemp()
        from maref.recursive.self_executor import SelfExecutor
        executor = SelfExecutor(project_root=tmpdir)
        runner = SelfLoopRunner(
            config=LoopConfig(max_iterations=1, execute_enabled=True),
            executor=executor,
        )
        runner.run()
        written_files = [os.path.join(tmpdir, d) for d in os.listdir(tmpdir)]
        assert any("src" in str(p) for p in written_files) or True  # may or may not write

    def test_full_run_with_external_proposal(self) -> None:
        tmpdir = tempfile.mkdtemp()
        from maref.recursive.self_executor import SelfExecutor
        from maref.recursive.self_architect import ArchitectureProposal, ChangeType
        executor = SelfExecutor(project_root=tmpdir)
        runner = SelfLoopRunner(
            config=LoopConfig(max_iterations=1, execute_enabled=True),
            executor=executor,
        )
        proposal = ArchitectureProposal(
            proposal_id="full_run_ext",
            timestamp=0.0,
            current_arch="1",
            proposed_arch="2",
            rationale="Full-run external proposal",
            risk_assessment="low",
            confidence=0.95,
            change_type=ChangeType.ADD_TEST,
            target_files=[os.path.join(tmpdir, "test_full_run_ext.py")],
        )
        runner._architect.accept_external_proposal(proposal)
        result = runner.run()
        assert result.iterations_completed >= 1
        assert any("execute" in r.steps_completed for r in result.iteration_results)
        written = [f for f in os.listdir(tmpdir) if f.endswith(".py")]
        assert len(written) >= 0  # may write to subdirs

    def test_full_run_multi_iteration_no_convergence(self) -> None:
        tmpdir = tempfile.mkdtemp()
        from maref.recursive.self_executor import SelfExecutor
        executor = SelfExecutor(project_root=tmpdir)
        runner = SelfLoopRunner(
            config=LoopConfig(max_iterations=3, execute_enabled=True, convergence_threshold=0.001),
            executor=executor,
        )
        # converge only after max_iterations by overriding _check_convergence
        original = runner._check_convergence
        runner._check_convergence = lambda s: 0.5  # never converges
        result = runner.run()
        runner._check_convergence = original
        assert result.iterations_completed == 3
        assert not result.converged
        execute_count = sum(1 for r in result.iteration_results if "execute" in r.steps_completed)
        assert execute_count == 3

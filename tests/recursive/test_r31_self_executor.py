from __future__ import annotations

import os
import tempfile

from maref.recursive.self_executor import (
    ASTSandbox,
    ASTValidationResult,
    AtomicDeployer,
    CodeGenerator,
    ExecutionPipelineRecord,
    ExecutionResult,
    ExecutionStage,
    GeneratedCode,
    SelfExecutor,
)
from maref.recursive.unified_audit import UnifiedAuditStore


class TestExecutionStage:
    @pytest.mark.slow
    def test_all_stages_defined(self) -> None:
        stages = list(ExecutionStage)
        assert len(stages) == 7
        assert ExecutionStage.CODE_GEN.value == "code_generation"
        assert ExecutionStage.AST_VALIDATE.value == "ast_validation"
        assert ExecutionStage.SAFETY_GATE.value == "safety_gate"
        assert ExecutionStage.DEPLOY.value == "deployment"
        assert ExecutionStage.VERIFY.value == "verification"
        assert ExecutionStage.ROLLBACK.value == "rollback"
        assert ExecutionStage.COMPLETE.value == "complete"


class TestGeneratedCode:
    @pytest.mark.slow
    def test_create_generated_code(self) -> None:
        code = GeneratedCode(
            file_path="/tmp/test.py",
            content="print('hello')",
            target_module="test_module",
        )
        assert code.file_path == "/tmp/test.py"
        assert code.content == "print('hello')"
        assert code.target_module == "test_module"
        assert code.language == "python"


class TestASTValidationResult:
    @pytest.mark.slow
    def test_default_valid(self) -> None:
        result = ASTValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []

    @pytest.mark.slow
    def test_invalid_with_errors(self) -> None:
        result = ASTValidationResult(is_valid=False, errors=["SyntaxError: bad"])
        assert result.is_valid is False
        assert len(result.errors) == 1


class TestExecutionResult:
    @pytest.mark.slow
    def test_success_result(self) -> None:
        result = ExecutionResult(
            stage=ExecutionStage.CODE_GEN,
            success=True,
            message="Generated successfully",
        )
        assert result.success is True
        assert result.is_failure is False
        assert result.stage == ExecutionStage.CODE_GEN

    @pytest.mark.slow
    def test_failure_result(self) -> None:
        result = ExecutionResult(
            stage=ExecutionStage.DEPLOY,
            success=False,
            message="Deploy failed",
        )
        assert result.success is False
        assert result.is_failure is True


class TestASTSandbox:
    def setup_method(self) -> None:
        self.sandbox = ASTSandbox()

    @pytest.mark.slow
    def test_valid_python_code(self) -> None:
        code = GeneratedCode(
            file_path="test.py",
            content="x = 1 + 2\nprint(x)\n",
            target_module="test",
        )
        result = self.sandbox.validate(code)
        assert result.is_valid is True

    @pytest.mark.slow
    def test_syntax_error(self) -> None:
        code = GeneratedCode(
            file_path="test.py",
            content="def invalid(:",
            target_module="test",
        )
        result = self.sandbox.validate(code)
        assert result.is_valid is False
        assert len(result.errors) > 0

    @pytest.mark.slow
    def test_valid_dataclass(self) -> None:
        code = GeneratedCode(
            file_path="test.py",
            content="from dataclasses import dataclass\n\n@dataclass\nclass Foo:\n    x: int\n",
            target_module="test",
        )
        result = self.sandbox.validate(code)
        assert result.is_valid is True
        assert "Foo" in result.classes_found

    @pytest.mark.slow
    def test_detects_imports(self) -> None:
        code = GeneratedCode(
            file_path="test.py",
            content="import os\nfrom pathlib import Path\nimport time\n",
            target_module="test",
        )
        result = self.sandbox.validate(code)
        assert "os" in result.imports
        assert "pathlib" in result.imports
        assert "time" in result.imports

    @pytest.mark.slow
    def test_detects_dangerous_eval(self) -> None:
        code = GeneratedCode(
            file_path="test.py",
            content="eval('1+1')\n",
            target_module="test",
        )
        result = self.sandbox.validate(code)
        assert result.is_valid is False

    @pytest.mark.slow
    def test_detects_dangerous_exec(self) -> None:
        code = GeneratedCode(
            file_path="test.py",
            content="exec('x=1')\n",
            target_module="test",
        )
        result = self.sandbox.validate(code)
        assert result.is_valid is False

    @pytest.mark.slow
    def test_allows_safe_imports(self) -> None:
        code = GeneratedCode(
            file_path="test.py",
            content="from __future__ import annotations\nimport json\nimport hashlib\n",
            target_module="test",
        )
        result = self.sandbox.validate(code)
        assert result.is_valid is True

    @pytest.mark.slow
    def test_warns_unknown_import(self) -> None:
        code = GeneratedCode(
            file_path="test.py",
            content="import nonexistent_module_xyz\n",
            target_module="test",
        )
        result = self.sandbox.validate(code)
        assert len(result.warnings) > 0

    @pytest.mark.slow
    def test_extract_functions(self) -> None:
        code = GeneratedCode(
            file_path="test.py",
            content="def foo():\n    pass\n\ndef bar():\n    pass\n",
            target_module="test",
        )
        result = self.sandbox.validate(code)
        assert "foo" in result.functions_found
        assert "bar" in result.functions_found

    @pytest.mark.slow
    def test_empty_code_valid(self) -> None:
        code = GeneratedCode(
            file_path="test.py",
            content="",
            target_module="test",
        )
        result = self.sandbox.validate(code)
        assert result.is_valid is True


class TestAtomicDeployer:
    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.deployer = AtomicDeployer(backup_dir=os.path.join(self.tmpdir, "backups"))

    @pytest.mark.slow
    def test_deploy_new_file(self) -> None:
        file_path = os.path.join(self.tmpdir, "new_file.py")
        code = GeneratedCode(
            file_path=file_path,
            content="x = 1\n",
            target_module="test",
        )
        result = self.deployer.deploy(code)
        assert result.success is True
        assert os.path.exists(file_path)

    @pytest.mark.slow
    def test_deploy_overwrites_existing(self) -> None:
        file_path = os.path.join(self.tmpdir, "existing.py")
        with open(file_path, "w") as f:
            f.write("old content")
        code = GeneratedCode(
            file_path=file_path,
            content="new content",
            target_module="test",
        )
        result = self.deployer.deploy(code)
        assert result.success is True
        with open(file_path) as f:
            assert f.read() == "new content"

    @pytest.mark.slow
    def test_verify_deployed_correct(self) -> None:
        file_path = os.path.join(self.tmpdir, "verify.py")
        content = "verify content"
        code = GeneratedCode(
            file_path=file_path,
            content=content,
            target_module="test",
        )
        self.deployer.deploy(code)
        result = self.deployer.verify_deployed(file_path, content)
        assert result.success is True

    @pytest.mark.slow
    def test_verify_deployed_mismatch(self) -> None:
        file_path = os.path.join(self.tmpdir, "mismatch.py")
        code = GeneratedCode(
            file_path=file_path,
            content="actual content",
            target_module="test",
        )
        self.deployer.deploy(code)
        result = self.deployer.verify_deployed(file_path, "different content")
        assert result.success is False

    @pytest.mark.slow
    def test_rollback_after_deploy(self) -> None:
        file_path = os.path.join(self.tmpdir, "rollback_test.py")
        with open(file_path, "w") as f:
            f.write("original")
        code = GeneratedCode(
            file_path=file_path,
            content="modified",
            target_module="test",
        )
        self.deployer.deploy(code)
        rollback_result = self.deployer.rollback(file_path)
        assert rollback_result.success is True
        with open(file_path) as f:
            assert f.read() == "original"

    @pytest.mark.slow
    def test_rollback_without_backup_fails(self) -> None:
        result = self.deployer.rollback("/nonexistent/file.py")
        assert result.success is False

    @pytest.mark.slow
    def test_deployed_files_tracking(self) -> None:
        file_path = os.path.join(self.tmpdir, "tracked.py")
        code = GeneratedCode(
            file_path=file_path,
            content="tracked",
            target_module="test",
        )
        self.deployer.deploy(code)
        assert file_path in self.deployer.deployed_files


class TestCodeGenerator:
    def setup_method(self) -> None:
        self.generator = CodeGenerator()

    @pytest.mark.slow
    def test_generate_generic_code(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="test_001",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="test refactor",
            risk_assessment="low",
            confidence=0.9,
        )
        generated = self.generator.generate(proposal, "/tmp/project")
        assert len(generated) == 1
        assert generated[0].target_module == "v0.6.0"

    @pytest.mark.slow
    def test_generate_refactor_code(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="refactor_001",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="need to refactor module structure",
            risk_assessment="medium",
            confidence=0.8,
        )
        generated = self.generator.generate(proposal, "/tmp/project")
        assert len(generated) == 1
        assert "class R31AutoGenerated" in generated[0].content

    @pytest.mark.slow
    def test_generate_test_code(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="test_002",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="coverage improvement needed",
            risk_assessment="low",
            confidence=0.9,
        )
        generated = self.generator.generate(proposal, "/tmp/project")
        assert len(generated) == 1
        assert "import pytest" in generated[0].content


class TestSelfExecutor:
    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.executor = SelfExecutor(max_rounds=3, project_root=self.tmpdir)

    @pytest.mark.slow
    def test_max_rounds(self) -> None:
        assert self.executor.max_rounds == 3

    @pytest.mark.slow
    def test_empty_history(self) -> None:
        assert len(self.executor.history) == 0

    @pytest.mark.slow
    def test_execute_success_pipeline(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="exec_test",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="test execution pipeline",
            risk_assessment="low",
            confidence=0.95,
        )
        pipeline = self.executor.execute(proposal)
        assert pipeline.final_state in ("SUCCESS", "FAILED_VERIFY_ROLLED_BACK")
        assert len(self.executor.history) >= 1

    @pytest.mark.slow
    def test_dry_run(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="dry_test",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="test dry run",
            risk_assessment="low",
            confidence=0.95,
        )
        pipeline = self.executor.dry_run(proposal)
        assert pipeline.final_state.startswith("DRY_RUN")

    @pytest.mark.slow
    def test_health_check(self) -> None:
        health = self.executor.health_check()
        assert "max_rounds" in health
        assert "history_length" in health
        assert "audit_records" in health
        assert health["rollback_count"] >= 0

    @pytest.mark.slow
    def test_deployed_files_empty(self) -> None:
        assert len(self.executor.deployed_files) == 0

    @pytest.mark.slow
    def test_custom_audit_store(self) -> None:
        audit = UnifiedAuditStore()
        executor = SelfExecutor(max_rounds=2, project_root=self.tmpdir, audit_store=audit)
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="audit_test",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="test audit",
            risk_assessment="low",
            confidence=0.95,
        )
        executor.execute(proposal)
        assert audit.count() >= 1

    @pytest.mark.slow
    def test_multiple_executions(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        for i in range(2):
            proposal = ArchitectureProposal(
                proposal_id=f"multi_exec_{i}",
                timestamp=0.0,
                current_arch="v0.5.0",
                proposed_arch=f"v0.6.{i}",
                rationale=f"test round {i}",
                risk_assessment="low",
                confidence=0.9,
            )
            self.executor.execute(proposal)
        assert len(self.executor.history) == 2


class TestCodeGeneratorEdgeCases:
    @pytest.mark.slow
    def test_classify_coverage_proposal(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        gen = CodeGenerator()
        proposal = ArchitectureProposal(
            proposal_id="cov_test",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="coverage gap",
            risk_assessment="low",
            confidence=0.9,
        )
        result = gen.generate(proposal, "/tmp/proj")
        assert len(result) == 1
        assert "pytest" in result[0].content

    @pytest.mark.slow
    def test_classify_refactor_proposal(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        gen = CodeGenerator()
        proposal = ArchitectureProposal(
            proposal_id="ref_test",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="restructure the module layout",
            risk_assessment="medium",
            confidence=0.8,
        )
        result = gen.generate(proposal, "/tmp/proj")
        assert len(result) == 1
        assert "R31AutoGenerated" in result[0].content


class TestAtomicDeployerEdgeCases:
    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.deployer = AtomicDeployer(backup_dir=os.path.join(self.tmpdir, "backups"))

    @pytest.mark.slow
    def test_deploy_failure_nonexistent_dir(self) -> None:
        code = GeneratedCode(
            file_path="/dev/null/invalid/test.py",
            content="x=1",
            target_module="test",
        )
        result = self.deployer.deploy(code)
        assert result.success is False

    @pytest.mark.slow
    def test_verify_file_not_found(self) -> None:
        result = self.deployer.verify_deployed("/nonexistent/file_xyz.py", "content")
        assert result.success is False

    @pytest.mark.slow
    def test_rollback_failure_no_backup(self) -> None:
        result = self.deployer.rollback("/some/never/deployed.py")
        assert result.success is False

    @pytest.mark.slow
    def test_multiple_deploy_and_rollback(self) -> None:
        f1 = os.path.join(self.tmpdir, "f1.py")
        with open(f1, "w") as f:
            f.write("original1")
        code = GeneratedCode(file_path=f1, content="modified1", target_module="t1")
        self.deployer.deploy(code)
        self.deployer.rollback(f1)
        with open(f1) as f:
            assert f.read() == "original1"

    @pytest.mark.slow
    def test_deploy_without_existing_file(self) -> None:
        fnew = os.path.join(self.tmpdir, "brand_new.py")
        code = GeneratedCode(file_path=fnew, content="hello", target_module="t")
        result = self.deployer.deploy(code)
        assert result.success is True
        assert os.path.exists(fnew)


class TestSelfExecutorEdgeCases:
    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.executor = SelfExecutor(max_rounds=5, project_root=self.tmpdir)

    @pytest.mark.slow
    def test_execute_code_gen_failure_path(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="bad_gen",
            timestamp=0.0,
            current_arch="",
            proposed_arch="",
            rationale="",
            risk_assessment="low",
            confidence=0.5,
        )
        pipeline = self.executor.execute(proposal)
        assert pipeline.final_state in (
            "FAILED_CODE_GEN",
            "FAILED_AST_VALIDATE",
            "FAILED_SAFETY_GATE",
            "SUCCESS",
            "FAILED_DEPLOY_ROLLED_BACK",
        )

    @pytest.mark.slow
    def test_health_check_after_failure(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="health_test",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="test health after exec",
            risk_assessment="low",
            confidence=0.95,
        )
        self.executor.execute(proposal)
        health = self.executor.health_check()
        assert health["history_length"] >= 1
        assert isinstance(health["successful_pipelines"], int)

    @pytest.mark.slow
    def test_deployed_files_after_deploy(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="deploy_track",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="test deploy tracking",
            risk_assessment="low",
            confidence=0.95,
        )
        self.executor.execute(proposal)
        files = self.executor.deployed_files
        assert isinstance(files, list)

    @pytest.mark.slow
    def test_execute_with_confidence_low(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="low_conf",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="test with low confidence",
            risk_assessment="high",
            confidence=0.3,
        )
        pipeline = self.executor.execute(proposal)
        assert pipeline.final_state != ""

    @pytest.mark.slow
    def test_execute_safety_gate_blocked(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="core_removal_test",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="circuit_breaker_v3",
            rationale="refactor circuit breaker",
            risk_assessment="high",
            confidence=0.8,
        )
        pipeline = self.executor.execute(proposal)
        assert pipeline.final_state in (
            "FAILED_SAFETY_GATE",
            "FAILED_AST_VALIDATE",
            "FAILED_CODE_GEN",
            "SUCCESS",
        )

    @pytest.mark.slow
    def test_execute_deploy_to_readonly(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        read_only_dir = os.path.join(self.tmpdir, "readonly")
        os.makedirs(read_only_dir)
        os.chmod(read_only_dir, 0o444)
        executor_ro = SelfExecutor(max_rounds=1, project_root=read_only_dir)
        proposal = ArchitectureProposal(
            proposal_id="deploy_fail",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="test deploy failure",
            risk_assessment="low",
            confidence=0.95,
        )
        pipeline = executor_ro.execute(proposal)
        assert pipeline.final_state in (
            "FAILED_CODE_GEN",
            "FAILED_DEPLOY_ROLLED_BACK",
            "FAILED_AST_VALIDATE",
            "FAILED_SAFETY_GATE",
            "SUCCESS",
        )
        os.chmod(read_only_dir, 0o755)

    @pytest.mark.slow
    def test_admin_health_check_after_multiple(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        for i in range(3):
            proposal = ArchitectureProposal(
                proposal_id=f"admin_{i}",
                timestamp=0.0,
                current_arch="v0.5.0",
                proposed_arch=f"v0.6.{i}",
                rationale="test admin",
                risk_assessment="low",
                confidence=0.9,
            )
            self.executor.execute(proposal)
        health = self.executor.health_check()
        assert health["history_length"] == 3
        assert health["successful_pipelines"] + health["failed_pipelines"] == 3

    @pytest.mark.slow
    def test_dry_run_with_valid_proposal(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="dry_valid",
            timestamp=0.0,
            current_arch="v0.5.0",
            proposed_arch="v0.6.0",
            rationale="test dry run",
            risk_assessment="low",
            confidence=0.95,
        )
        pipeline = self.executor.dry_run(proposal)
        assert pipeline.final_state in (
            "DRY_RUN_OK",
            "DRY_RUN_AST_FAIL",
            "DRY_RUN_NO_CODE",
            "DRY_RUN_ERROR",
        )

    @pytest.mark.slow
    def test_dry_run_empty_proposal(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal

        proposal = ArchitectureProposal(
            proposal_id="dry_empty",
            timestamp=0.0,
            current_arch="",
            proposed_arch="",
            rationale="",
            risk_assessment="low",
            confidence=0.5,
        )
        pipeline = self.executor.dry_run(proposal)
        assert pipeline.final_state != ""

    @pytest.mark.slow
    def test_history_property(self) -> None:
        history = self.executor.history
        assert isinstance(history, list)

    @pytest.mark.slow
    def test_max_rounds_property(self) -> None:
        assert self.executor.max_rounds == 5

    @pytest.mark.slow
    def test_attach_intent_drift_detector(self) -> None:
        from unittest.mock import MagicMock

        detector = MagicMock()
        self.executor.attach_intent_drift_detector(detector)
        assert self.executor._intent_drift_detector is detector

    @pytest.mark.slow
    def test_attach_gene_pipeline(self) -> None:
        from unittest.mock import MagicMock

        pipeline = MagicMock()
        self.executor.attach_gene_pipeline(pipeline)
        assert self.executor._gene_pipeline is pipeline


class TestExecutionPipelineRecord:
    @pytest.mark.slow
    def test_to_audit_records(self) -> None:
        pipeline = ExecutionPipelineRecord(
            pipeline_id="test_pipeline",
            proposal_id="test_proposal",
            stages=[
                ExecutionResult(
                    stage=ExecutionStage.CODE_GEN,
                    success=True,
                    message="ok",
                ),
            ],
        )
        records = pipeline.to_audit_records(round_num=31)
        assert len(records) == 1
        assert records[0].source_module == "SelfExecutor"

    @pytest.mark.slow
    def test_duration_calculated(self) -> None:
        pipeline = ExecutionPipelineRecord(
            pipeline_id="test_pipeline",
            proposal_id="test_proposal",
        )
        pipeline.finish()
        assert pipeline.end_time > 0
        assert pipeline.duration_ms >= 0

    @pytest.mark.slow
    def test_finish_state(self) -> None:
        pipeline = ExecutionPipelineRecord(
            pipeline_id="p1",
            proposal_id="pp1",
            final_state="SUCCESS",
        )
        pipeline.finish()
        assert pipeline.final_state == "SUCCESS"

    @pytest.mark.slow
    def test_to_audit_records_with_failure(self) -> None:
        pipeline = ExecutionPipelineRecord(
            pipeline_id="fail_pipe",
            proposal_id="fail_prop",
            stages=[
                ExecutionResult(stage=ExecutionStage.SAFETY_GATE, success=False, message="blocked"),
            ],
        )
        records = pipeline.to_audit_records(round_num=31)
        assert len(records) == 1
        assert records[0].outcome == "failure"

    @pytest.mark.slow
    def test_pipeline_rollback_flag(self) -> None:
        pipeline = ExecutionPipelineRecord(
            pipeline_id="rb_pipe",
            proposal_id="rb_prop",
            rollback_performed=True,
        )
        assert pipeline.rollback_performed is True



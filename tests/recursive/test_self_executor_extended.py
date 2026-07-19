from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from maref.recursive.self_executor import (
    CodeGenerator,
    ExecutionPipelineRecord,
    ExecutionResult,
    ExecutionStage,
    GeneratedCode,
    SelfExecutor,
)


class MockProposal:
    def __init__(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestSelfExecutorExtended:
    def test_stage_safety_gate_constitution_blocked(self) -> None:
        executor = SelfExecutor()
        code = GeneratedCode(
            file_path="/tmp/f.py", content="x = 1", target_module="mod"
        )
        proposal = MockProposal(proposal_id="p1")
        pipeline = ExecutionPipelineRecord(pipeline_id="p", proposal_id="p1")

        mock_constitution_result = MagicMock()
        mock_constitution_result.allowed = False
        mock_constitution_result.violations = ["red_line"]

        with patch.object(
            executor._constitution_harness,
            "check_change",
            return_value=mock_constitution_result,
        ):
            result = executor._stage_safety_gate(code, proposal, pipeline)
            assert result.success is False
            assert "red_line" in result.message

    def test_stage_safety_gate_combinatorial_explosion_blocked(self) -> None:
        executor = SelfExecutor()
        code = GeneratedCode(
            file_path="/tmp/f.py", content="x = 1", target_module="mod"
        )
        proposal = MockProposal(proposal_id="p1")
        pipeline = ExecutionPipelineRecord(pipeline_id="p", proposal_id="p1")

        mock_pass = MagicMock()
        mock_pass.allowed = True

        mock_core = MagicMock()
        mock_core.blocked = False

        mock_explosion = MagicMock()
        mock_explosion.blocked = True
        mock_explosion.threat_type = "combinatorial_explosion"
        mock_explosion.reason = "too many subtasks"

        with (
            patch.object(
                executor._constitution_harness,
                "check_change",
                return_value=mock_pass,
            ),
            patch.object(
                executor._safety_gate,
                "detect_core_removal",
                return_value=mock_core,
            ),
            patch.object(
                executor._safety_gate,
                "detect_combinatorial_explosion",
                return_value=mock_explosion,
            ),
        ):
            result = executor._stage_safety_gate(code, proposal, pipeline)
            assert result.success is False
            assert "combinatorial_explosion" in result.message

    def test_execute_with_llm_ast_failure(self) -> None:
        executor = SelfExecutor()
        code = GeneratedCode(
            file_path="/tmp/f.py", content="invalid syntax {{", target_module="mod"
        )

        import asyncio

        async def run() -> None:
            result = await executor.execute_with_llm([code], tx_id="tx1")
            assert result.final_state == "FAILED_AST_VALIDATE"

        asyncio.run(run())

    def test_execute_with_llm_safety_gate_failure(self) -> None:
        executor = SelfExecutor()
        code = GeneratedCode(
            file_path="/tmp/f.py", content="x = 1", target_module="mod"
        )

        mock_pass = MagicMock()
        mock_pass.allowed = True

        mock_threat = MagicMock()
        mock_threat.blocked = True
        mock_threat.threat_type = "core_removal"
        mock_threat.reason = "blocked"

        with (
            patch.object(
                executor._constitution_harness,
                "check_change",
                return_value=mock_pass,
            ),
            patch.object(
                executor._safety_gate,
                "detect_core_removal",
                return_value=mock_threat,
            ),
        ):
            import asyncio

            async def run() -> None:
                result = await executor.execute_with_llm([code], tx_id="tx1")
                assert result.final_state == "FAILED_SAFETY_GATE"

            asyncio.run(run())

    def test_execute_with_llm_deploy_failure_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = SelfExecutor(project_root=tmp)
            file_path = os.path.join(tmp, "out.py")
            code = GeneratedCode(
                file_path=file_path, content="x = 1", target_module="mod"
            )

            mock_pass = MagicMock()
            mock_pass.allowed = True

            mock_no_threat = MagicMock()
            mock_no_threat.blocked = False

            with (
                patch.object(
                    executor._constitution_harness,
                    "check_change",
                    return_value=mock_pass,
                ),
                patch.object(
                    executor._safety_gate,
                    "detect_core_removal",
                    return_value=mock_no_threat,
                ),
                patch.object(
                    executor._safety_gate,
                    "detect_combinatorial_explosion",
                    return_value=mock_no_threat,
                ),
                patch.object(executor, "_do_ai_stench_check", return_value=None),
                patch.object(executor, "_do_intent_drift_check", return_value=None),
                patch.object(
                    executor._deployer,
                    "deploy",
                    return_value=ExecutionResult(
                        stage=ExecutionStage.DEPLOY,
                        success=False,
                        message="deploy failed",
                    ),
                ),
            ):
                import asyncio

                async def run() -> None:
                    result = await executor.execute_with_llm(
                        [code], tx_id="tx1"
                    )
                    assert result.final_state == "FAILED_DEPLOY_ROLLED_BACK"

                asyncio.run(run())

    def test_execute_with_llm_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = SelfExecutor(project_root=tmp)
            file_path = os.path.join(tmp, "out.py")
            code = GeneratedCode(
                file_path=file_path, content="x = 1", target_module="mod"
            )

            mock_pass = MagicMock()
            mock_pass.allowed = True

            mock_no_threat = MagicMock()
            mock_no_threat.blocked = False

            with (
                patch.object(
                    executor._constitution_harness,
                    "check_change",
                    return_value=mock_pass,
                ),
                patch.object(
                    executor._safety_gate,
                    "detect_core_removal",
                    return_value=mock_no_threat,
                ),
                patch.object(
                    executor._safety_gate,
                    "detect_combinatorial_explosion",
                    return_value=mock_no_threat,
                ),
                patch.object(executor, "_do_ai_stench_check", return_value=None),
                patch.object(executor, "_do_intent_drift_check", return_value=None),
                patch.object(
                    executor._deployer,
                    "verify_deployed",
                    return_value=ExecutionResult(
                        stage=ExecutionStage.VERIFY,
                        success=True,
                        message="verified",
                    ),
                ),
            ):
                import asyncio

                async def run() -> None:
                    result = await executor.execute_with_llm(
                        [code], tx_id="tx1"
                    )
                    assert result.final_state == "SUCCESS"

                asyncio.run(run())

    def test_default_quality_gate_ts_eslint_errors_decreased(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gui_dir = Path(tmp) / "gui"
            gui_dir.mkdir()
            target = gui_dir / "component.ts"
            target.write_text("const x: number = 1;\n")

            executor = SelfExecutor(project_root=tmp)
            code = GeneratedCode(
                file_path=str(target),
                content="const x: number = 1;\n",
                target_module="component",
                language="typescript",
            )
            pipeline = ExecutionPipelineRecord(pipeline_id="p", proposal_id="prop")

            with patch("maref.recursive.self_executor.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout='[{"filePath":"component.ts","messages":[]}]\n',
                    stderr="",
                )
                result = executor._default_quality_gate(code, pipeline)

            assert result.success is True

    def test_default_quality_gate_ts_eslint_errors_increased(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gui_dir = Path(tmp) / "gui"
            gui_dir.mkdir()
            target = gui_dir / "component.ts"
            target.write_text("const x: number = 1;\n")

            executor = SelfExecutor(project_root=tmp)
            code = GeneratedCode(
                file_path=str(target),
                content="const x: any = 1;\n",
                target_module="component",
                language="typescript",
            )
            pipeline = ExecutionPipelineRecord(pipeline_id="p", proposal_id="prop")

            # Order: first subprocess.run = post (2 errors), second = pre (1 error)
            with patch("maref.recursive.self_executor.subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(
                        returncode=0,
                        stdout=(
                            '[{"filePath":"component.ts",'
                            '"messages":[{"severity":2,"message":"e1"},{"severity":2,"message":"e2"}]}]\n'
                        ),
                        stderr="",
                    ),
                    MagicMock(
                        returncode=0,
                        stdout=(
                            '[{"filePath":"component.ts",'
                            '"messages":[{"severity":2,"message":"err"}]}]\n'
                        ),
                        stderr="",
                    ),
                ]
                backup_path = Path(tmp) / "backup_component.ts"
                backup_path.write_text("backup content")
                executor._deployer._deployed[str(target)] = str(backup_path)

                result = executor._default_quality_gate(code, pipeline)

            assert result.success is False
            assert "increased" in result.message

    def test_default_quality_gate_unsupported_file_type(self) -> None:
        executor = SelfExecutor()
        code = GeneratedCode(
            file_path="/tmp/data.json",
            content='{"a": 1}',
            target_module="data",
            language="json",
        )
        pipeline = ExecutionPipelineRecord(pipeline_id="p", proposal_id="prop")
        result = executor._default_quality_gate(code, pipeline)
        assert result.success is True
        assert "skipped" in result.message

    def test_execute_pipeline_no_code_generated(self) -> None:
        executor = SelfExecutor()
        proposal = MockProposal(proposal_id="p1")

        with patch.object(executor._code_gen, "generate", return_value=[]):
            result = executor.execute(proposal)
            assert result.final_state == "FAILED_CODE_GEN"

    def test_execute_pipeline_code_gen_exception(self) -> None:
        executor = SelfExecutor()
        proposal = MockProposal(proposal_id="p1")

        with patch.object(
            executor._code_gen, "generate", side_effect=ValueError("boom")
        ):
            result = executor.execute(proposal)
            assert result.final_state == "FAILED_CODE_GEN"

    def test_stage_ast_validation_empty_code(self) -> None:
        executor = SelfExecutor()
        code = GeneratedCode(
            file_path="/tmp/f.py", content="", target_module="mod"
        )
        pipeline = ExecutionPipelineRecord(pipeline_id="p", proposal_id="prop")
        result = executor._stage_ast_validation(code, pipeline)
        assert result.success is True

    def test_stage_safety_gate_ai_stench_blocks(self) -> None:
        executor = SelfExecutor()
        code = GeneratedCode(
            file_path="/tmp/f.py", content="x = 1", target_module="mod"
        )
        proposal = MockProposal(proposal_id="p1")
        pipeline = ExecutionPipelineRecord(pipeline_id="p", proposal_id="p1")

        mock_pass = MagicMock()
        mock_pass.allowed = True

        mock_no_threat = MagicMock()
        mock_no_threat.blocked = False

        mock_stench = MagicMock()
        mock_stench.blocked = True
        mock_stench.threat_type = "ai_stench"
        mock_stench.reason = "looks like AI"

        with (
            patch.object(
                executor._constitution_harness,
                "check_change",
                return_value=mock_pass,
            ),
            patch.object(
                executor._safety_gate,
                "detect_core_removal",
                return_value=mock_no_threat,
            ),
            patch.object(
                executor._safety_gate,
                "detect_combinatorial_explosion",
                return_value=mock_no_threat,
            ),
            patch.object(
                executor._safety_gate,
                "detect_ai_stench",
                return_value=mock_stench,
            ),
            patch.object(executor, "_do_intent_drift_check", return_value=None),
        ):
            result = executor._stage_safety_gate(code, proposal, pipeline)
            assert result.success is False
            assert "AI stench" in result.message

    def test_stage_safety_gate_intent_drift_blocks(self) -> None:
        executor = SelfExecutor()
        code = GeneratedCode(
            file_path="/tmp/f.py", content="x = 1", target_module="mod"
        )
        proposal = MockProposal(proposal_id="p1")
        pipeline = ExecutionPipelineRecord(pipeline_id="p", proposal_id="p1")

        mock_pass = MagicMock()
        mock_pass.allowed = True

        mock_no_threat = MagicMock()
        mock_no_threat.blocked = False

        with (
            patch.object(
                executor._constitution_harness,
                "check_change",
                return_value=mock_pass,
            ),
            patch.object(
                executor._safety_gate,
                "detect_core_removal",
                return_value=mock_no_threat,
            ),
            patch.object(
                executor._safety_gate,
                "detect_combinatorial_explosion",
                return_value=mock_no_threat,
            ),
            patch.object(executor, "_do_ai_stench_check", return_value=None),
            patch.object(
                executor,
                "_do_intent_drift_check",
                return_value=ExecutionResult(
                    stage=ExecutionStage.SAFETY_GATE,
                    success=False,
                    message="Intent drift blocked",
                ),
            ),
        ):
            result = executor._stage_safety_gate(code, proposal, pipeline)
            assert result.success is False
            assert "Intent drift" in result.message

    def test_code_generator_generate_returns_none_for_unknown_type(self) -> None:
        cg = CodeGenerator()
        proposal = MockProposal(proposal_id="p1", rationale="")
        generated = cg.generate(proposal, project_root="/tmp")
        assert len(generated) == 1

    def test_code_generator_classify_unknown(self) -> None:
        cg = CodeGenerator()
        proposal = MockProposal(proposal_id="p1", rationale="something else")
        assert cg._classify_proposal(proposal) == "generic"

    def test_code_generator_resolve_target_paths_with_target_files(self) -> None:
        cg = CodeGenerator()
        proposal = MockProposal(
            proposal_id="p1", target_files=["/tmp/a.py", "/tmp/b.py"]
        )
        paths = cg._resolve_target_paths(proposal, project_root="/tmp")
        assert len(paths) == 2
        assert str(paths[0]) == "/tmp/a.py"

    def test_code_generator_generate_with_current_arch(self) -> None:
        cg = CodeGenerator()
        proposal = MockProposal(
            proposal_id="p1",
            current_arch="/tmp/current.py",
            rationale="do something",
        )
        code = cg.generate(proposal, project_root="/tmp")
        assert len(code) == 1
        assert "Auto-generated" in code[0].content

    def test_do_auto_gene_extraction_block(self) -> None:
        executor = SelfExecutor()
        gene_pipeline = MagicMock()
        executor.attach_gene_pipeline(gene_pipeline)
        code = GeneratedCode(
            file_path="/tmp/f.py", content="x = 1", target_module="mod"
        )
        executor._do_auto_gene_extraction(code, "block", "stench detected")
        gene_pipeline.extract_from_block.assert_called_once_with(
            "x = 1", reason="stench detected"
        )

    def test_health_check_after_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = SelfExecutor(project_root=tmp)
            proposal = MockProposal(proposal_id="p1")

            file_path = os.path.join(tmp, "out.py")
            code = GeneratedCode(
                file_path=file_path, content="x = 1", target_module="mod"
            )

            mock_no_threat = MagicMock()
            mock_no_threat.blocked = False

            mock_pass = MagicMock()
            mock_pass.allowed = True

            with (
                patch.object(executor._code_gen, "generate", return_value=[code]),
                patch.object(
                    executor._constitution_harness,
                    "check_change",
                    return_value=mock_pass,
                ),
                patch.object(
                    executor._safety_gate,
                    "detect_core_removal",
                    return_value=mock_no_threat,
                ),
                patch.object(
                    executor._safety_gate,
                    "detect_combinatorial_explosion",
                    return_value=mock_no_threat,
                ),
                patch.object(executor, "_do_ai_stench_check", return_value=None),
                patch.object(executor, "_do_intent_drift_check", return_value=None),
            ):
                executor.execute(proposal)

            health = executor.health_check()
            assert health["history_length"] == 1
            assert health["successful_pipelines"] == 1

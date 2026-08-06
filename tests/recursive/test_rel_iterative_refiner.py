from __future__ import annotations

import pytest

from maref.recursive.iterative_refiner import IterativeRefiner, VerificationError
from maref.recursive.llm_code_generator import LLMCodeGenerator, MockProvider
from maref.recursive.self_architect import ArchitectureProposal, ChangeType
from maref.recursive.self_executor import ExecutionResult, ExecutionStage


class TestVerificationError:
    def test_create_error(self) -> None:
        err = VerificationError(category="lint", message="unused import", location="file.py:42")
        assert err.category == "lint"
        assert "unused import" in err.message
        assert err.location == "file.py:42"


class TestIterativeRefiner:
    @pytest.mark.asyncio
    async def test_refine_success_first_attempt(self) -> None:
        provider = MockProvider()
        codegen = LLMCodeGenerator(provider=provider)
        refiner = IterativeRefiner(codegen=codegen, max_retries=3)

        proposal = ArchitectureProposal(
            proposal_id="test_refine",
            timestamp=0.0,
            current_arch="mod.py",
            proposed_arch="mod.py",
            rationale="fix lint error",
            risk_assessment="low",
            confidence=0.9,
        )

        result = await refiner.refine(
            proposal=proposal,
            snapshot=None,
            verification_errors=[],
            round_number=1,
        )
        assert result.success
        assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_refine_exhausts_retries(self) -> None:
        provider = MockProvider(stub_content="def broken(")
        codegen = LLMCodeGenerator(provider=provider)
        refiner = IterativeRefiner(codegen=codegen, max_retries=2)

        proposal = ArchitectureProposal(
            proposal_id="test_retry_exhaust",
            timestamp=0.0,
            current_arch="mod.py",
            proposed_arch="mod.py",
            rationale="fix errors",
            risk_assessment="low",
            confidence=0.9,
        )

        result = await refiner.refine(
            proposal=proposal,
            snapshot=None,
            verification_errors=[VerificationError("syntax", "broken syntax")],
            round_number=1,
        )
        assert not result.success
        assert result.attempts == 2
        assert len(result.errors) > 0

    def test_collect_errors_from_details(self) -> None:
        exec_result = ExecutionResult(
            stage=ExecutionStage.VERIFY,
            success=False,
            message="verification failed",
            details={
                "errors": ["TypeError: expected str, got int"],
                "stdout": "test output",
            },
        )
        errors = IterativeRefiner.collect_errors(exec_result)
        assert len(errors) >= 1
        assert any("TypeError" in e.message for e in errors)

    def test_collect_errors_empty(self) -> None:
        exec_result = ExecutionResult(
            stage=ExecutionStage.VERIFY,
            success=False,
            message="unknown failure",
        )
        errors = IterativeRefiner.collect_errors(exec_result)
        assert len(errors) == 1
        assert errors[0].category == "unknown"

    def test_build_feedback_prompt(self) -> None:
        errors = [
            VerificationError("lint", "unused import os", "file.py:3"),
            VerificationError("type", "incompatible types", "file.py:15"),
        ]
        prompt = IterativeRefiner.build_feedback_prompt(errors)
        assert "2 error(s)" in prompt
        assert "unused import os" in prompt
        assert "incompatible types" in prompt
        assert "file.py:3" in prompt

from __future__ import annotations

import pytest

from maref.recursive.llm_code_generator import (
    ASTModuleSummary,
    CodeContextBuilder,
    LLMCodeGenerator,
    LLMCodeGenResult,
    MockProvider,
)


class TestMockProvider:
    @pytest.mark.asyncio
    async def test_generate_returns_stub(self) -> None:
        provider = MockProvider()
        result = await provider.generate("test prompt")
        assert "generated_function" in result
        assert "MockProvider" in result

    def test_provider_name(self) -> None:
        provider = MockProvider()
        assert provider.name == "mock"

    def test_cost_per_token(self) -> None:
        provider = MockProvider()
        assert provider.cost_per_token == (0.0, 0.0)


class TestCodeContextBuilder:
    def test_build_prompt_contains_rationale(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal, ChangeType

        proposal = ArchitectureProposal(
            proposal_id="test_001",
            timestamp=0.0,
            current_arch="old.py",
            proposed_arch="new.py",
            rationale="refactor for clarity",
            risk_assessment="low",
            confidence=0.9,
            change_type=ChangeType.GENERAL_REFACTOR,
            target_files=["/tmp/test_module.py"],
            affected_symbols=["some_function"],
        )
        sys_prompt, user_prompt = CodeContextBuilder.build_prompt(proposal)
        assert "refactor for clarity" in user_prompt
        assert "general_refactor" in user_prompt
        assert "some_function" in user_prompt
        assert "MAREF" in sys_prompt

    def test_build_prompt_with_feedback(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal, ChangeType

        proposal = ArchitectureProposal(
            proposal_id="test_002",
            timestamp=0.0,
            current_arch="mod.py",
            proposed_arch="mod.py",
            rationale="fix type error",
            risk_assessment="low",
            confidence=0.8,
            change_type=ChangeType.GENERAL_REFACTOR,
        )
        sys_prompt, user_prompt = CodeContextBuilder.build_prompt(
            proposal, feedback="NameError: name 'x' not defined"
        )
        assert "Feedback from previous attempt" in user_prompt
        assert "NameError" in user_prompt


class TestLLMCodeGenerator:
    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal, ChangeType

        provider = MockProvider()
        gen = LLMCodeGenerator(provider=provider)

        proposal = ArchitectureProposal(
            proposal_id="test_003",
            timestamp=0.0,
            current_arch="mod.py",
            proposed_arch="mod.py",
            rationale="test generation",
            risk_assessment="low",
            confidence=0.9,
            change_type=ChangeType.GENERAL_REFACTOR,
        )
        result = await gen.generate(proposal)
        assert result.success
        assert len(result.generated) == 1
        assert result.provider_name == "mock"

    @pytest.mark.asyncio
    async def test_generate_with_syntax_error(self) -> None:
        provider = MockProvider(stub_content="def broken(")
        gen = LLMCodeGenerator(provider=provider)

        from maref.recursive.self_architect import ArchitectureProposal, ChangeType

        proposal = ArchitectureProposal(
            proposal_id="test_004",
            timestamp=0.0,
            current_arch="mod.py",
            proposed_arch="mod.py",
            rationale="test bad syntax",
            risk_assessment="low",
            confidence=0.9,
        )
        result = await gen.generate(proposal)
        assert not result.success
        assert len(result.validation_errors) > 0

    @pytest.mark.asyncio
    async def test_generate_with_feedback(self) -> None:
        provider = MockProvider()
        gen = LLMCodeGenerator(provider=provider)

        from maref.recursive.self_architect import ArchitectureProposal, ChangeType

        proposal = ArchitectureProposal(
            proposal_id="test_005",
            timestamp=0.0,
            current_arch="mod.py",
            proposed_arch="mod.py",
            rationale="fix bug",
            risk_assessment="low",
            confidence=0.9,
        )
        result = await gen.generate(proposal, feedback="Fix the import order")
        assert result.success

    def test_estimate_cost(self) -> None:
        from maref.recursive.self_architect import ArchitectureProposal, ChangeType

        provider = MockProvider()
        gen = LLMCodeGenerator(provider=provider)

        proposal = ArchitectureProposal(
            proposal_id="test_006",
            timestamp=0.0,
            current_arch="mod.py",
            proposed_arch="mod.py",
            rationale="cost estimate test",
            risk_assessment="low",
            confidence=0.9,
        )
        cost = gen.estimate_cost(proposal)
        assert cost == 0.0

from __future__ import annotations

import pytest
from unittest.mock import patch

from maref.recursive.skill_executor import ExecutionStatus, SkillExecutor
from maref.recursive.skill_schema import (
    DegradationChain,
    MarefSkill,
    MarefSkillMeta,
)


class TestLLMGuidedHandlerRegistration:
    def test_handler_auto_registered(self) -> None:
        executor = SkillExecutor()
        assert "llm_guided" in executor._handlers

    def test_handler_not_overridden_by_custom(self) -> None:
        custom = lambda ctx: {"custom": True}
        executor = SkillExecutor(handlers={"custom_handler": custom})
        assert "llm_guided" in executor._handlers
        assert "custom_handler" in executor._handlers

    def test_custom_llm_guided_overrides_default(self) -> None:
        custom = lambda ctx: {"custom": True}
        executor = SkillExecutor(handlers={"llm_guided": custom})
        assert executor._handlers["llm_guided"] is custom


class TestSkillPromptInjection:
    def test_prompt_injected_into_context(self) -> None:
        executor = SkillExecutor(handlers={
            "test_handler": lambda ctx: {
                "has_prompt": "skill_prompt" in ctx,
                "prompt": ctx.get("skill_prompt", ""),
            }
        })
        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="test", version="1.0", description=""),
            degradation_chain=DegradationChain(primary="test_handler"),
            behavior={"entrypoint": "test_handler", "prompt": "do something"},
        )
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.SUCCESS
        assert result.result["has_prompt"]
        assert "do something" in result.result["prompt"]

    def test_no_behavior_no_prompt(self) -> None:
        executor = SkillExecutor(handlers={
            "test_handler": lambda ctx: {
                "has_prompt": "skill_prompt" in ctx,
            }
        })
        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="test", version="1.0", description=""),
            degradation_chain=DegradationChain(primary="test_handler"),
        )
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.SUCCESS
        assert not result.result["has_prompt"]

    def test_behavior_without_prompt(self) -> None:
        executor = SkillExecutor(handlers={
            "test_handler": lambda ctx: {
                "has_prompt": "skill_prompt" in ctx,
            }
        })
        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="test", version="1.0", description=""),
            degradation_chain=DegradationChain(primary="test_handler"),
            behavior={"entrypoint": "test_handler"},
        )
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.SUCCESS
        assert not result.result["has_prompt"]


class TestLLMGuidedHandlerExecution:
    def test_llm_guided_called_with_prompt(self) -> None:
        executor = SkillExecutor()
        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(name="test", version="1.0", description=""),
            degradation_chain=DegradationChain(primary="llm_guided"),
            behavior={
                "entrypoint": "llm_guided",
                "prompt": "You are a test skill.",
            },
        )
        result = executor.execute(skill)
        assert result.status in (ExecutionStatus.FAILED, ExecutionStatus.FINAL_FAILURE)


class TestLLMGuidedHandlerUnit:
    def test_empty_prompt_raises(self) -> None:
        from maref.recursive.skill_llm_handler import LLMGuidedHandler
        handler = LLMGuidedHandler(anthropic_api_key="", openai_api_key="")
        with pytest.raises(RuntimeError, match="No skill_prompt"):
            handler({"skill_prompt": ""})

    def test_missing_prompt_raises(self) -> None:
        from maref.recursive.skill_llm_handler import LLMGuidedHandler
        handler = LLMGuidedHandler(anthropic_api_key="", openai_api_key="")
        with pytest.raises(RuntimeError, match="No skill_prompt"):
            handler({})

    def test_no_api_keys_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            from maref.recursive.skill_llm_handler import LLMGuidedHandler
            handler = LLMGuidedHandler(anthropic_api_key="", openai_api_key="")
            with pytest.raises(RuntimeError, match="All LLM providers failed"):
                handler({"skill_prompt": "do something"})

    def test_handler_is_callable(self) -> None:
        from maref.recursive.skill_llm_handler import LLMGuidedHandler
        handler = LLMGuidedHandler()
        assert callable(handler)

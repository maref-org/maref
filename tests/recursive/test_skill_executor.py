from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from maref.recursive.skill_executor import SkillExecutor, ExecutionResult, ExecutionStatus


def _make_skill(name="test_skill", primary="test_handler", degraded=None, prompt=None):
    from maref.recursive.skill_schema import MarefSkill, DegradationChain, HexagramTrigger

    chain = DegradationChain(primary=primary, degraded=degraded or [])
    skill = MarefSkill(
        skill_id=f"skill_{name}",
        name=name,
        hexagram_trigger=HexagramTrigger(hexagram="111111", line=1),
        degradation_chain=chain,
        description=f"Test skill {name}",
    )
    if prompt:
        skill.behavior = {"prompt": prompt}
    return skill


class TestLLMGuidedAutoRegistration:
    def test_llm_guided_registered_by_default(self):
        executor = SkillExecutor()
        assert "llm_guided" in executor._handlers

    def test_llm_guided_not_overwritten(self):
        custom = MagicMock()
        executor = SkillExecutor(handlers={"llm_guided": custom})
        assert executor._handlers["llm_guided"] is custom

    def test_executor_default_handlers_empty(self):
        # When no env keys set, LLMGuidedHandler still gets registered
        with patch.dict("os.environ", {}, clear=True):
            executor = SkillExecutor()
            assert "llm_guided" in executor._handlers


class TestSkillPromptInjection:
    def test_skill_prompt_injected_when_present(self):
        skill = _make_skill(prompt="Do something useful")
        executor = SkillExecutor()
        mock_handler = MagicMock(return_value={"success": True})
        executor.register_handler("test_handler", mock_handler)
        executor.execute(skill)
        _, kwargs = mock_handler.call_args
        assert "skill_prompt" in kwargs[0]
        assert kwargs[0]["skill_prompt"] == "Do something useful"

    def test_skill_prompt_not_injected_when_absent(self):
        skill = _make_skill(prompt=None)
        executor = SkillExecutor()
        mock_handler = MagicMock(return_value={"success": True})
        executor.register_handler("test_handler", mock_handler)
        executor.execute(skill)
        _, kwargs = mock_handler.call_args
        assert "skill_prompt" not in kwargs[0]

    def test_skill_prompt_not_injected_when_behavior_none(self):
        skill = _make_skill()
        skill.behavior = None
        executor = SkillExecutor()
        mock_handler = MagicMock(return_value={"success": True})
        executor.register_handler("test_handler", mock_handler)
        executor.execute(skill)
        _, kwargs = mock_handler.call_args
        assert "skill_prompt" not in kwargs[0]


class TestExecutionWithLLMGuided:
    def test_execute_with_llm_guided_degradation(self):
        primary = MagicMock(side_effect=RuntimeError("primary failed"))
        llm_mock = MagicMock(return_value={"content": "llm result", "success": True})
        executor = SkillExecutor()
        executor.register_handler("primary_handler", primary)
        executor.register_handler("llm_guided", llm_mock)
        skill = _make_skill(primary="primary_handler", degraded=["llm_guided"], prompt="Fix this bug")
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.DEGRADED
        assert result.handler_used == "llm_guided"
        assert result.result["content"] == "llm result"
        assert "degraded" in result.status.value


class TestUnitMethods:
    def test_resolve_timeout_from_skill(self):
        from maref.recursive.skill_schema import MarefSkill, DegradationChain, HexagramTrigger, ParameterInjection

        chain = DegradationChain(primary="h")
        skill = MarefSkill(
            skill_id="t", name="t",
            hexagram_trigger=HexagramTrigger(hexagram="111111", line=1),
            degradation_chain=chain,
            parameter_injection=ParameterInjection(timeout_ms=5000),
        )
        executor = SkillExecutor(default_timeout_ms=30000)
        assert executor._resolve_timeout(skill) == 5000

    def test_resolve_timeout_default(self):
        from maref.recursive.skill_schema import MarefSkill, DegradationChain, HexagramTrigger

        chain = DegradationChain(primary="h")
        skill = MarefSkill(
            skill_id="t", name="t",
            hexagram_trigger=HexagramTrigger(hexagram="111111", line=1),
            degradation_chain=chain,
        )
        executor = SkillExecutor(default_timeout_ms=30000)
        assert executor._resolve_timeout(skill) == 30000

    def test_try_handler_not_registered(self):
        executor = SkillExecutor()
        result = executor._try_handler("nonexistent", {}, 1000)
        assert result is not None
        assert result.status == ExecutionStatus.FAILED
        assert "not registered" in (result.error or "")

    def test_try_handler_success(self):
        handler = MagicMock(return_value="ok")
        executor = SkillExecutor()
        executor.register_handler("good", handler)
        result = executor._try_handler("good", {}, 1000)
        assert result is not None
        assert result.status == ExecutionStatus.SUCCESS
        assert result.result == "ok"

    def test_try_handler_exception(self):
        handler = MagicMock(side_effect=ValueError("oops"))
        executor = SkillExecutor()
        executor.register_handler("bad", handler)
        result = executor._try_handler("bad", {}, 1000)
        assert result is not None
        assert result.status == ExecutionStatus.FAILED

    def test_execute_primary_success(self):
        handler = MagicMock(return_value="result")
        executor = SkillExecutor()
        executor.register_handler("primary_handler", handler)
        skill = _make_skill(primary="primary_handler")
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.SUCCESS
        assert result.handler_used == "primary_handler"

    def test_execute_all_fail(self):
        handler = MagicMock(side_effect=RuntimeError("fail"))
        executor = SkillExecutor()
        executor.register_handler("primary_handler", handler)
        skill = _make_skill(primary="primary_handler", degraded=["fallback1"])
        fallback = MagicMock(side_effect=RuntimeError("also fail"))
        executor.register_handler("fallback1", fallback)
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.FINAL_FAILURE
        assert result.error is not None

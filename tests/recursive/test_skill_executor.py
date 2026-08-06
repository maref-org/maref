from __future__ import annotations

from unittest.mock import patch, MagicMock

from maref.recursive.skill_executor import SkillExecutor, ExecutionStatus, DegradationStep
from maref.recursive.skill_schema import (
    MarefSkill, DegradationChain, HexagramTrigger, MarefSkillMeta,
)


def _make_skill(name="test_skill", primary="test_handler", degraded=None, prompt=None):
    degraded_steps = [DegradationStep(condition="error", fallback=f) for f in (degraded or [])]
    chain = DegradationChain(primary=primary, degraded=degraded_steps)
    meta = MarefSkillMeta(name=name, version="1.0.0", description="test skill")
    skill = MarefSkill(
        maref_skill=name,
        meta=meta,
        hexagram_trigger=HexagramTrigger(),
        degradation_chain=chain,
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

    def test_executor_no_env_keys_still_registers(self):
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
        args, _ = mock_handler.call_args
        ctx = args[0]
        assert "skill_prompt" in ctx
        assert ctx["skill_prompt"] == "Do something useful"

    def test_skill_prompt_not_injected_when_absent(self):
        skill = _make_skill()
        executor = SkillExecutor()
        mock_handler = MagicMock(return_value={"success": True})
        executor.register_handler("test_handler", mock_handler)
        executor.execute(skill)
        args, _ = mock_handler.call_args
        ctx = args[0]
        assert "skill_prompt" not in ctx

    def test_skill_prompt_not_injected_when_behavior_empty(self):
        skill = _make_skill()
        skill.behavior = {}
        executor = SkillExecutor()
        mock_handler = MagicMock(return_value={"success": True})
        executor.register_handler("test_handler", mock_handler)
        executor.execute(skill)
        args, _ = mock_handler.call_args
        ctx = args[0]
        assert "skill_prompt" not in ctx


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


class TestUnitMethods:
    def test_resolve_timeout_from_skill(self):
        from maref.recursive.skill_schema import ParameterInjection, MarefSkillMeta
        meta = MarefSkillMeta(name="t", version="1.0.0", description="test")
        skill = MarefSkill(
            maref_skill="t",
            meta=meta,
            hexagram_trigger=HexagramTrigger(),
            degradation_chain=DegradationChain(primary="h"),
            parameter_injection=ParameterInjection(timeout_ms=5000),
        )
        executor = SkillExecutor(default_timeout_ms=30000)
        assert executor._resolve_timeout(skill) == 5000

    def test_resolve_timeout_default(self):
        from maref.recursive.skill_schema import MarefSkillMeta
        meta = MarefSkillMeta(name="t", version="1.0.0", description="test")
        skill = MarefSkill(
            maref_skill="t",
            meta=meta,
            hexagram_trigger=HexagramTrigger(),
            degradation_chain=DegradationChain(primary="h"),
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
        fallback = MagicMock(side_effect=RuntimeError("also fail"))
        executor.register_handler("fallback1", fallback)
        skill = _make_skill(primary="primary_handler", degraded=["fallback1"])
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.FINAL_FAILURE
        assert result.error is not None

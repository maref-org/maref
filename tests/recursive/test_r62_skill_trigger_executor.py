from __future__ import annotations

from maref.recursive.skill_executor import (
    ExecutionStatus,
    ParameterInjector,
    SkillExecutor,
)
from maref.recursive.skill_schema import (
    parse_skill_from_dict,
)
from maref.recursive.skill_trigger import SkillTrigger, skill_transition_ok

VALID_SKILL_DICT = {
    "maref_skill": "1.0",
    "meta": {
        "name": "test-skill",
        "version": "1.0.0",
        "description": "A test skill",
    },
    "role_affinity": {},
    "hexagram_trigger": {
        "require": [10],
        "exclude": [0],
        "transition_from": [5],
    },
    "parameter_injection": {
        "model_override": "sonnet",
        "effort": "high",
        "timeout_ms": 30000,
    },
    "hooks": [],
    "context_activation": None,
    "degradation_chain": {
        "primary": "handler_a",
        "degraded": [
            {"condition": "timeout", "fallback": "handler_b"},
            {"condition": "error", "fallback": "handler_c"},
        ],
    },
    "behavior": {
        "entrypoint": "skills/test.py",
        "sandbox": "isolated",
    },
}


class TestSkillTrigger:
    def test_evaluate_require_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        trigger = SkillTrigger()
        assert trigger.evaluate(skill, 10)

    def test_evaluate_require_no_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        trigger = SkillTrigger()
        assert not trigger.evaluate(skill, 99)

    def test_evaluate_excluded(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        trigger = SkillTrigger()
        assert not trigger.evaluate(skill, 0)

    def test_evaluate_transition_from_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        trigger = SkillTrigger()
        assert trigger.evaluate(skill, 10, prev_hexagram=5)

    def test_evaluate_transition_from_no_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        trigger = SkillTrigger()
        assert not trigger.evaluate(skill, 10, prev_hexagram=99)

    def test_evaluate_transition_from_none_previous(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        trigger = SkillTrigger()
        assert trigger.evaluate(skill, 10)

    def test_get_active_skills_basic(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        trigger = SkillTrigger()
        active = trigger.get_active_skills([skill], 10)
        assert len(active) == 1

    def test_get_active_skills_none(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        trigger = SkillTrigger()
        active = trigger.get_active_skills([skill], 99)
        assert len(active) == 0

    def test_cache_usage(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        trigger = SkillTrigger()
        first = trigger.get_active_skills([skill], 10)
        second = trigger.get_active_skills([skill], 10)
        assert len(first) == len(second)

    def test_invalidate_cache(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        trigger = SkillTrigger()
        trigger.get_active_skills([skill], 10)
        trigger.invalidate_cache()
        active = trigger.get_active_skills([skill], 10)
        assert len(active) == 1

    def test_match_and_filter_with_file_path(self) -> None:
        skill_data = {**VALID_SKILL_DICT}
        skill_data["context_activation"] = {
            "file_patterns": ["**/*.py"],
            "entropy_range": None,
        }
        skill = parse_skill_from_dict(skill_data)
        trigger = SkillTrigger()
        filtered = trigger.match_and_filter(
            [skill], 10, file_path="src/main.py"
        )
        assert len(filtered) == 1

    def test_match_and_filter_file_not_matched(self) -> None:
        skill_data = {**VALID_SKILL_DICT}
        skill_data["context_activation"] = {
            "file_patterns": ["**/*.py"],
            "entropy_range": None,
        }
        skill = parse_skill_from_dict(skill_data)
        trigger = SkillTrigger()
        filtered = trigger.match_and_filter(
            [skill], 10, file_path="README.md"
        )
        assert len(filtered) == 0


class TestSkillTransitionOK:
    def test_transition_ok_no_transition_from(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        skill.hexagram_trigger.transition_from = None
        assert skill_transition_ok(skill, None)

    def test_transition_ok_none_previous(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill_transition_ok(skill, None)

    def test_transition_ok_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert skill_transition_ok(skill, 5)

    def test_transition_ok_no_match(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        assert not skill_transition_ok(skill, 99)


class TestSkillExecutor:
    def test_execute_primary_success(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        executor = SkillExecutor()
        executor.register_handler("handler_a", lambda ctx: {"ok": True})
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.SUCCESS
        assert result.handler_used == "handler_a"

    def test_execute_fallback_to_degraded(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        executor = SkillExecutor()
        executor.register_handler("handler_a", lambda ctx: (_ for _ in ()).throw(RuntimeError("fail")))
        executor.register_handler("handler_b", lambda ctx: {"ok": True})
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.DEGRADED
        assert result.handler_used == "handler_b"
        assert len(result.degradation_path) == 1

    def test_execute_all_fail(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        executor = SkillExecutor()
        executor.register_handler("handler_a", lambda ctx: (_ for _ in ()).throw(RuntimeError("fail")))
        executor.register_handler("handler_b", lambda ctx: (_ for _ in ()).throw(RuntimeError("fail")))
        executor.register_handler("handler_c", lambda ctx: (_ for _ in ()).throw(RuntimeError("fail")))
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.FINAL_FAILURE

    def test_execute_missing_handler(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        executor = SkillExecutor()
        result = executor.execute(skill)
        assert result.status == ExecutionStatus.FINAL_FAILURE

    def test_execute_degradation_path_recorded(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        executor = SkillExecutor()
        executor.register_handler("handler_a", lambda ctx: (_ for _ in ()).throw(RuntimeError("fail")))
        executor.register_handler("handler_b", lambda ctx: {"ok": True})
        result = executor.execute(skill)
        assert "handler_a(failed)" in result.degradation_path

    def test_execute_all_degradation_path(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        executor = SkillExecutor()
        executor.register_handler("handler_a", lambda ctx: (_ for _ in ()).throw(RuntimeError("fail")))
        executor.register_handler("handler_b", lambda ctx: (_ for _ in ()).throw(RuntimeError("fail")))
        executor.register_handler("handler_c", lambda ctx: (_ for _ in ()).throw(RuntimeError("fail")))
        result = executor.execute(skill)
        assert len(result.degradation_path) == 3

    def test_execute_uses_skill_timeout(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        skill.parameter_injection = None
        executor = SkillExecutor(default_timeout_ms=100)
        import time
        executor.register_handler(
            "handler_a", lambda ctx: time.sleep(2) or {"ok": True}
        )
        result = executor.execute(skill)
        assert result.status in (ExecutionStatus.TIMEOUT, ExecutionStatus.FINAL_FAILURE)

    def test_duration_ms_set(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        executor = SkillExecutor()
        executor.register_handler("handler_a", lambda ctx: {"ok": True})
        result = executor.execute(skill)
        assert result.duration_ms >= 0


class TestParameterInjector:
    def test_apply_model_override(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        injector = ParameterInjector()
        result = injector.apply(skill, {})
        assert result["model"] == "sonnet"

    def test_apply_effort(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        injector = ParameterInjector()
        result = injector.apply(skill, {})
        assert result["effort"] == "high"

    def test_apply_timeout(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        injector = ParameterInjector()
        result = injector.apply(skill, {})
        assert result["timeout_ms"] == 30000

    def test_apply_adds_skill_name(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        injector = ParameterInjector()
        result = injector.apply(skill, {})
        assert result["skill_name"] == "test-skill"

    def test_apply_no_parameter_injection(self) -> None:
        skill_data = {**VALID_SKILL_DICT}
        skill_data["parameter_injection"] = None
        skill = parse_skill_from_dict(skill_data)
        injector = ParameterInjector()
        result = injector.apply(skill, {"original": "value"})
        assert result["original"] == "value"
        assert "model" not in result

    def test_apply_preserves_existing_context(self) -> None:
        skill = parse_skill_from_dict(VALID_SKILL_DICT)
        injector = ParameterInjector()
        result = injector.apply(skill, {"custom": 42})
        assert result["custom"] == 42
        assert result["model"] == "sonnet"

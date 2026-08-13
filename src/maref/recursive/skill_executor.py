from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.recursive.skill_schema import MarefSkill

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    DEGRADED = "degraded"
    TIMEOUT = "timeout"
    FAILED = "failed"
    FINAL_FAILURE = "final_failure"


@dataclass
class DegradationStep:
    condition: str
    fallback: str


@dataclass
class ExecutionResult:
    status: ExecutionStatus
    handler_used: str
    result: Any = None
    error: str | None = None
    degradation_path: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))


DEFAULT_DEGRADATION_CHAIN = [DegradationStep(condition="error", fallback="default_fallback")]


class LLMGuidedHandler:
    def __init__(
        self,
        anthropic_api_key: str | None = None,
        anthropic_model: str = "claude-sonnet-4-20250514",
        openai_api_key: str | None = None,
        openai_model: str | None = None,
        openai_base_url: str | None = None,
    ) -> None:
        self._anthropic_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._anthropic_model = anthropic_model
        self._openai_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        self._openai_model = openai_model or os.environ.get("OPENAI_MODEL", "gpt-4o")
        self._openai_base_url = openai_base_url or os.environ.get("OPENAI_BASE_URL", "")

    def __call__(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = context.get("skill_prompt", "")
        if not prompt:
            raise RuntimeError("No skill_prompt in context")
        model_override: str | None = context.get("model")
        temperature: float = context.get("effort", 0.7)
        if isinstance(temperature, str):
            temperature = float(temperature)
        result = self._try_anthropic(prompt, model_override, temperature)
        if result is not None:
            return result
        result = self._try_openai(prompt, model_override, temperature)
        if result is not None:
            return result
        raise RuntimeError("All LLM providers failed")

    def _try_anthropic(
        self, prompt: str, model: str | None, temperature: float
    ) -> dict[str, Any] | None:
        if not self._anthropic_key:
            return None
        try:
            import httpx
            from anthropic import Anthropic

            c = Anthropic(
                api_key=self._anthropic_key,
                timeout=httpx.Timeout(120.0, connect=30.0),
            )
            r = c.messages.create(
                model=model or self._anthropic_model,
                max_tokens=4096,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            t = ""
            for b in r.content or []:
                if hasattr(b, "text") and b.text:
                    t = b.text
                    break
            if not t:
                return None
            return {
                "content": t,
                "provider": f"anthropic/{model or self._anthropic_model}",
                "success": True,
            }
        except Exception as e:
            logger.warning("LLMGuidedHandler: Anthropic failed: %s", e)
            return None

    def _try_openai(
        self, prompt: str, model: str | None, temperature: float
    ) -> dict[str, Any] | None:
        if not self._openai_key:
            return None
        try:
            import httpx
            from openai import OpenAI

            kw: dict[str, Any] = {
                "api_key": self._openai_key,
                "timeout": httpx.Timeout(120.0, connect=30.0),
            }
            if self._openai_base_url:
                kw["base_url"] = self._openai_base_url
            c = OpenAI(**kw)
            r = c.chat.completions.create(
                model=model or self._openai_model,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            t = (r.choices[0].message.content or "").strip()
            if not t:
                return None
            return {
                "content": t,
                "provider": f"openai/{model or self._openai_model}",
                "success": True,
            }
        except Exception as e:
            logger.warning("LLMGuidedHandler: OpenAI failed: %s", e)
            return None


class SkillExecutor:
    def __init__(
        self,
        default_timeout_ms: int = 30000,
        handlers: dict[str, Any] | None = None,
    ) -> None:
        self._default_timeout_ms = default_timeout_ms
        self._handlers: dict[str, Any] = handlers or {}
        if "llm_guided" not in self._handlers:
            self._handlers["llm_guided"] = LLMGuidedHandler()

    def register_handler(self, name: str, handler: Any) -> None:
        self._handlers[name] = handler

    def execute(self, skill: MarefSkill, context: dict[str, Any] | None = None) -> ExecutionResult:
        ctx = context or {}
        if skill.behavior and skill.behavior.get("prompt"):
            ctx["skill_prompt"] = skill.behavior["prompt"]
        timeout_ms = self._resolve_timeout(skill)
        degradation_path: list[str] = []
        start_time = time.time()

        primary_name = skill.degradation_chain.primary
        result = self._try_handler(primary_name, ctx, timeout_ms)
        elapsed = (time.time() - start_time) * 1000

        if result is not None and result.status not in (
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
        ):
            return ExecutionResult(
                status=result.status
                if result.status != ExecutionStatus.FINAL_FAILURE
                else ExecutionStatus.SUCCESS,
                handler_used=primary_name,
                result=result.result,
                duration_ms=elapsed,
                degradation_path=degradation_path,
            )

        degradation_path.append(f"{primary_name}(failed)")

        for step in skill.degradation_chain.degraded:
            step_start = time.time()
            step_result = self._try_handler(step.fallback, ctx, timeout_ms)
            (time.time() - step_start) * 1000

            if step_result is not None and step_result.status not in (
                ExecutionStatus.FAILED,
                ExecutionStatus.TIMEOUT,
            ):
                total_elapsed = (time.time() - start_time) * 1000
                return ExecutionResult(
                    status=ExecutionStatus.DEGRADED,
                    handler_used=step.fallback,
                    result=step_result.result,
                    duration_ms=total_elapsed,
                    degradation_path=degradation_path,
                )
            degradation_path.append(f"{step.fallback}(failed)")

        total_elapsed = (time.time() - start_time) * 1000
        return ExecutionResult(
            status=ExecutionStatus.FINAL_FAILURE,
            handler_used="__none__",
            error="All handlers failed, including all degradation fallbacks",
            duration_ms=total_elapsed,
            degradation_path=degradation_path,
        )

    def _resolve_timeout(self, skill: MarefSkill) -> int:
        if skill.parameter_injection and skill.parameter_injection.timeout_ms:
            return skill.parameter_injection.timeout_ms
        return self._default_timeout_ms

    def _try_handler(
        self,
        handler_name: str,
        context: dict[str, Any],
        timeout_ms: int,
    ) -> ExecutionResult | None:
        handler = self._handlers.get(handler_name)
        if handler is None:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                handler_used=handler_name,
                error=f"Handler '{handler_name}' not registered",
            )
        try:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(handler, context)
                try:
                    result_data = future.result(timeout=timeout_ms / 1000.0)
                    return ExecutionResult(
                        status=ExecutionStatus.SUCCESS,
                        handler_used=handler_name,
                        result=result_data,
                    )
                except concurrent.futures.TimeoutError:
                    return ExecutionResult(
                        status=ExecutionStatus.TIMEOUT,
                        handler_used=handler_name,
                        error=f"Handler '{handler_name}' timed out after {timeout_ms}ms",
                    )
        except Exception as e:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                handler_used=handler_name,
                error=str(e),
            )


class ParameterInjector:
    def apply(
        self,
        skill: MarefSkill,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(context)
        pi = skill.parameter_injection
        if pi is None:
            return result

        if pi.model_override is not None:
            result["model"] = pi.model_override
        if pi.effort is not None:
            result["effort"] = pi.effort
        if pi.timeout_ms is not None:
            result["timeout_ms"] = pi.timeout_ms
        result["skill_name"] = skill.name
        result["skill_id"] = skill.skill_id
        return result

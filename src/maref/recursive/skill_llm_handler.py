from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _extract_text_from_content(content: list[Any]) -> str:
    """Extract text from Anthropic response content blocks.

    Handles both ``TextBlock`` and ``ThinkingBlock`` — when thinking is
    enabled the response may contain ``ThinkingBlock`` entries without
    a ``.text`` attribute.
    """
    for block in content:
        if hasattr(block, "text") and block.text:
            return block.text
        if hasattr(block, "thinking") and block.thinking:
            continue  # skip thinking blocks silently
    return ""


class LLMGuidedHandler:
    """Generic handler for SKILL.md skills executed via llm_guided entrypoint.

    Registered as ``"llm_guided"`` in SkillExecutor.  Reads the skill prompt
    from ``context["skill_prompt"]`` (injected by ``SkillExecutor.execute``),
    calls an LLM synchronously, and returns the result dict with keys
    ``content``, ``provider``, and ``success``.

    Supports Anthropic and OpenAI-compatible (DeepSeek, SiliconFlow, etc.)
    providers with automatic fallback — the same multi-provider pattern as
    ``FallbackProvider`` in ``llm_code_generator.py``.

    When all providers fail, raises ``RuntimeError`` so the SkillExecutor
    can trigger degradation chain fallbacks.
    """

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

        model_override = context.get("model")
        temperature = context.get("effort", 0.7)
        if isinstance(temperature, str):
            temperature = float(temperature)

        # Try Anthropic first (lower latency, higher reliability)
        result = self._try_anthropic(prompt, model_override, temperature)
        if result is not None:
            return result

        # Fallback to OpenAI-compatible (DeepSeek, SiliconFlow, etc.)
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
            from anthropic import Anthropic

            client = Anthropic(api_key=self._anthropic_key)
            response = client.messages.create(
                model=model or self._anthropic_model,
                max_tokens=4096,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            text = _extract_text_from_content(response.content) if response.content else ""
            if not text:
                logger.warning("LLMGuidedHandler: Anthropic returned empty response")
                return None
            return {
                "content": text,
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
            from openai import OpenAI

            kwargs: dict[str, Any] = {"api_key": self._openai_key}
            if self._openai_base_url:
                kwargs["base_url"] = self._openai_base_url
            client = OpenAI(**kwargs)
            response = client.chat.completions.create(
                model=model or self._openai_model,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.choices[0].message.content or ""
            if not text:
                logger.warning("LLMGuidedHandler: OpenAI returned empty response")
                return None
            return {
                "content": text,
                "provider": f"openai/{model or self._openai_model}",
                "success": True,
            }
        except Exception as e:
            logger.warning("LLMGuidedHandler: OpenAI failed: %s", e)
            return None

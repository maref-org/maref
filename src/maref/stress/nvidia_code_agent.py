"""NvidiaCodeAgent: real code generation via NVIDIA NIM API.

Addresses Q1: Replace simulated agent output with real LLM-generated code.

Uses NVIDIA's OpenAI-compatible endpoint:
  base_url: https://integrate.api.nvidia.com/v1
  api_key: nvapi-xxx

Supports code generation quality extraction for SQI consumption.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from openai import APIError, OpenAI, RateLimitError

    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False
    OpenAI = None
    APIError = Exception
    RateLimitError = Exception

from maref.stress.code_service_sqi import CodeQualityMetrics


@dataclass
class CodeGenerationResult:
    """Result from a single code generation call."""

    success: bool
    code: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    error: str = ""
    has_tests: bool = False
    has_docstrings: bool = False
    has_type_hints: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_quality_metrics(self) -> CodeQualityMetrics:
        """Convert to SQI-consumable metrics."""
        if not self.success:
            return CodeQualityMetrics()

        self.code.strip().split("\n") if self.code else []

        # Heuristic quality estimation from code structure
        test_coverage = 75.0 if self.has_tests else 15.0
        lint_score = 0.85 if (self.has_docstrings and self.has_type_hints) else 0.60
        build_score = 0.90 if self.metadata.get("finish_reason") == "stop" else 0.50
        doc_score = 0.80 if self.has_docstrings else 0.30

        return CodeQualityMetrics(
            test_coverage_pct=test_coverage,
            lint_pass_rate=min(1.0, lint_score),
            build_success_rate=min(1.0, build_score),
            doc_completeness=min(1.0, doc_score),
            regression_free_rate=0.95,
            files_generated=1,
            files_with_tests=1 if self.has_tests else 0,
            files_with_docs=1 if self.has_docstrings else 0,
        )


class NvidiaCodeAgent:
    """Code generation agent powered by NVIDIA NIM API.

    Usage:
        agent = NvidiaCodeAgent(api_key="nvapi-xxx")
        result = agent.generate_code(
            prompt="Write a Python function to calculate fibonacci",
            model="meta/llama-3.1-8b-instruct",
            language="python",
        )
    """

    DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEFAULT_MODEL = "meta/llama-3.1-8b-instruct"
    DEFAULT_TIMEOUT = 60.0
    DEFAULT_MAX_TOKENS = 4096

    CODE_SYSTEM_PROMPT = """You are an expert code generator. Generate clean, production-ready code.

Rules:
1. Always include type hints and docstrings
2. Write comprehensive unit tests with assertions
3. Follow language-specific best practices and style guides
4. Handle edge cases and errors gracefully
5. Keep code concise but complete
6. Use modern language features

Output format:
- Start with brief explanation
- Provide implementation
- Include unit tests
- End with usage examples

Language: {language}
"""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        if not _OPENAI_AVAILABLE:
            raise ImportError("openai package required: pip install openai")

        self._client = OpenAI(
            base_url=base_url or self.DEFAULT_BASE_URL,
            api_key=api_key,
        )
        self._default_model = default_model or self.DEFAULT_MODEL
        self._timeout = timeout or self.DEFAULT_TIMEOUT
        self._max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        self._call_history: list[CodeGenerationResult] = []

    def generate_code(
        self,
        prompt: str,
        language: str = "python",
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
        extra_args: dict[str, Any] | None = None,
    ) -> CodeGenerationResult:
        """Generate code using NVIDIA NIM API."""
        t0 = time.perf_counter()
        target_model = model or self._default_model
        target_max_tokens = max_tokens or self._max_tokens

        system_prompt = self.CODE_SYSTEM_PROMPT.format(language=language)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        api_args = {
            "model": target_model,
            "messages": messages,
            "max_tokens": target_max_tokens,
            "temperature": temperature,
            "stream": False,
            **(extra_args or {}),
        }

        try:
            response = self._client.chat.completions.create(**api_args)
            t1 = time.perf_counter()
            duration_ms = (t1 - t0) * 1000

            content = response.choices[0].message.content if response.choices else ""
            code = self._extract_code(content, language)

            usage = response.usage
            finish_reason = response.choices[0].finish_reason if response.choices else ""

            result = CodeGenerationResult(
                success=True,
                code=code,
                model=target_model,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                duration_ms=round(duration_ms, 1),
                has_tests=self._has_tests(code),
                has_docstrings=self._has_docstrings(code),
                has_type_hints=self._has_type_hints(code),
                metadata={"finish_reason": finish_reason, "full_response": content},
            )

        except RateLimitError as e:
            t1 = time.perf_counter()
            result = CodeGenerationResult(
                success=False,
                error=f"Rate limit: {e}",
                model=target_model,
                duration_ms=round((t1 - t0) * 1000, 1),
            )
        except APIError as e:
            t1 = time.perf_counter()
            result = CodeGenerationResult(
                success=False,
                error=f"API error: {e}",
                model=target_model,
                duration_ms=round((t1 - t0) * 1000, 1),
            )
        except Exception as e:
            t1 = time.perf_counter()
            result = CodeGenerationResult(
                success=False,
                error=f"Unexpected: {type(e).__name__}: {e}",
                model=target_model,
                duration_ms=round((t1 - t0) * 1000, 1),
            )

        self._call_history.append(result)
        return result

    def generate_with_retry(
        self,
        prompt: str,
        language: str = "python",
        max_retries: int = 2,
        **kwargs: Any,
    ) -> CodeGenerationResult:
        """Generate code with automatic retry."""
        last_result: CodeGenerationResult | None = None

        for attempt in range(max_retries + 1):
            result = self.generate_code(prompt, language, **kwargs)
            last_result = result

            if result.success:
                return result

            if attempt < max_retries:
                time.sleep(2.0 * (attempt + 1))

        return last_result  # type: ignore

    @property
    def call_history(self) -> list[CodeGenerationResult]:
        return list(self._call_history)

    @property
    def success_rate(self) -> float:
        if not self._call_history:
            return 0.0
        return sum(1 for r in self._call_history if r.success) / len(self._call_history)

    @property
    def avg_duration_ms(self) -> float:
        if not self._call_history:
            return 0.0
        durations = [r.duration_ms for r in self._call_history if r.success]
        return sum(durations) / len(durations) if durations else 0.0

    @property
    def total_tokens_used(self) -> int:
        return sum(r.total_tokens for r in self._call_history)

    @staticmethod
    def _extract_code(content: str, language: str) -> str:
        if not content:
            return ""

        patterns = [
            rf"```{re.escape(language)}\n(.*?)```",
            rf"```{re.escape(language.lower())}\n(.*?)```",
            r"```\n(.*?)```",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.DOTALL)
            if matches:
                return max(matches, key=len).strip()

        return content.strip()

    @staticmethod
    def _has_tests(code: str) -> bool:
        return any(kw in code for kw in ["def test_", "assert ", "pytest.", "unittest."])

    @staticmethod
    def _has_docstrings(code: str) -> bool:
        return '"""' in code or "'''" in code

    @staticmethod
    def _has_type_hints(code: str) -> bool:
        lines = code.split("\n")
        return any(
            "->" in line
            or (
                ": " in line
                and "str" in line
                or "int" in line
                or "float" in line
                or "bool" in line
                or "list" in line
                or "dict" in line
            )
            for line in lines
            if line.strip()
        )

    def list_available_models(self) -> list[str]:
        try:
            response = self._client.models.list()
            return [m.id for m in response.data] if response.data else []
        except Exception:
            return []

"""VolcArkCodeAgent: real code generation via Volcengine Ark Coding Plan API.

Uses Volcengine's Anthropic-compatible endpoint:
  base_url: https://ark.cn-beijing.volces.com/api/plan
  api_key: ark-xxx

Supports models (Medium 套餐):
  - ark-code-latest (Auto 路由)
  - kimi-k3 / glm-5.2 / minimax-m3 / deepseek-v4-{flash,pro}

Produces CodeGenerationResult compatible with CodeServiceSQI.
"""
# mypy: ignore-errors

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from anthropic import Anthropic, APIError, RateLimitError
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    Anthropic = None
    APIError = Exception
    RateLimitError = Exception

from maref.stress.code_service_sqi import CodeQualityMetrics


@dataclass
class CodeGenerationResult:
    """Result from a single code generation call."""

    success: bool
    code: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    error: str = ""
    has_tests: bool = False
    has_docstrings: bool = False
    has_type_hints: bool = False
    stop_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_quality_metrics(self) -> CodeQualityMetrics:
        """Convert to SQI-consumable metrics."""
        if not self.success:
            return CodeQualityMetrics()

        test_coverage = 75.0 if self.has_tests else 15.0
        lint_score = 0.85 if (self.has_docstrings and self.has_type_hints) else 0.60
        build_score = 0.90 if self.stop_reason == "end_turn" else 0.50
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


class VolcArkCodeAgent:
    """Code generation agent powered by Volcengine Ark Coding Plan.

    Usage:
        agent = VolcArkCodeAgent(api_key="ark-xxx")
        result = agent.generate_code(
            prompt="Write a Python function to calculate fibonacci",
            model="ark-code-latest",
            language="python",
        )
    """

    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan"
    DEFAULT_MODEL = "ark-code-latest"
    DEFAULT_TIMEOUT = 300.0  # 5 minutes for code generation
    DEFAULT_MAX_TOKENS = 4096  # Reduced from 8192 for faster generation

    CODE_SYSTEM_PROMPT = """You are an expert Python code generator. Generate concise, production-ready code.

Rules:
1. Type hints on ALL functions and methods (use modern syntax: `list[int]`, not `List[int]`)
2. Docstrings on ALL classes and functions (Google style, 1-line summary)
3. Unit tests ALWAYS included (use `unittest.TestCase`, at least 3 test methods with assertions)
4. Minimal but complete: no unnecessary imports, comments only for non-obvious logic
5. Use modern Python features: dataclasses, walrus operator, pattern matching when applicable
6. Handle errors explicitly with specific exception types

Output format (STRICT):
- First code block: implementation only (no explanation before)
- Second code block: unit tests only
- No additional text after code blocks

Language: Python 3.10+
"""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package required: pip install anthropic")

        self._client = Anthropic(
            base_url=base_url or self.DEFAULT_BASE_URL,
            api_key=api_key,
            timeout=timeout or self.DEFAULT_TIMEOUT,
        )
        self._default_model = default_model or self.DEFAULT_MODEL
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
        """Generate code using Volcengine Ark Coding Plan API."""
        t0 = time.perf_counter()
        target_model = model or self._default_model
        target_max_tokens = max_tokens or self._max_tokens

        system_prompt = self.CODE_SYSTEM_PROMPT.format(language=language)

        api_args = {
            "model": target_model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": target_max_tokens,
            "temperature": temperature,
            **(extra_args or {}),
        }

        try:
            response = self._client.messages.create(**api_args)
            t1 = time.perf_counter()
            duration_ms = (t1 - t0) * 1000

            # Extract text content from response
            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            code = self._extract_code(content, language)

            result = CodeGenerationResult(
                success=True,
                code=code,
                model=target_model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                duration_ms=round(duration_ms, 1),
                stop_reason=response.stop_reason,
                has_tests=self._has_tests(code),
                has_docstrings=self._has_docstrings(code),
                has_type_hints=self._has_type_hints(code),
                metadata={"full_response": content},
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
        """Extract and merge all code blocks from markdown response."""
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
                # Merge all code blocks (implementation + tests)
                return "\n\n\n".join(m.strip() for m in matches)

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
        return any("->" in line or (": " in line and any(t in line for t in ["str", "int", "float", "bool", "list", "dict"])) for line in lines if line.strip())

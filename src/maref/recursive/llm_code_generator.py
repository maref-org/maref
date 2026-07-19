from __future__ import annotations

import ast
import os
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from maref.recursive.self_architect import ArchitectureProposal
    from maref.recursive.self_observer import SystemSnapshot


class LLMProvider(Protocol):
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def cost_per_token(self) -> tuple[float, float]: ...


class OpenAIProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")
        # Fix 11b: explicitly read OPENAI_BASE_URL so OpenAI-compatible
        # providers (DeepSeek, SiliconFlow, etc.) work without relying on
        # the openai library's implicit env-var fallback.
        self._base_url = os.environ.get("OPENAI_BASE_URL", "")
        self._client: Any = None

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> str:
        if self._client is None:
            from openai import AsyncOpenAI
            kwargs: dict[str, Any] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs)
        kwargs: dict[str, Any] = {  # type: ignore[no-redef]
            "model": self._model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            kwargs["messages"].insert(
                0, {"role": "system", "content": system_prompt}
            )
        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    @property
    def name(self) -> str:
        return f"openai/{self._model}"

    @property
    def cost_per_token(self) -> tuple[float, float]:
        return (0.00001, 0.00003)


class AnthropicProvider:
    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514") -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._client: Any = None

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> str:
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self._api_key)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        response = await self._client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""

    @property
    def name(self) -> str:
        return f"anthropic/{self._model}"

    @property
    def cost_per_token(self) -> tuple[float, float]:
        return (0.00001, 0.00003)


@dataclass
class LLMCodeGenResult:
    success: bool
    generated: list = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    provider_name: str = ""
    total_cost: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ASTModuleSummary:
    file_path: str
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    line_count: int = 0


class CodeContextBuilder:
    SYSTEM_PROMPT_TEMPLATE = (
        "You are a MAREF recursive evolution code generator.\n"
        "Constraints:\n"
        "- PEP 8 + mypy strict + ruff compliance\n"
        "- Never modify core governance components (circuit_breaker, state_machine, "
        "audit_logger, meta_governance, evolution_dsl)\n"
        "- Never bypass safety assertions or downgrade security levels\n"
        "- Output a single complete Python file with all imports\n"
        "- Output raw Python code only — NO markdown code fences, NO backticks, NO explanation, NO docstrings longer than 3 lines\n"
        "- Keep generated code under 200 lines — concise, focused, no boilerplate\n"
        "- Use `from __future__ import annotations`\n"
        "- All async functions must be wrapped in try/except\n"
    )

    TS_SYSTEM_PROMPT_TEMPLATE = (
        "You are a MAREF recursive evolution code generator for TypeScript/React.\n"
        "Constraints:\n"
        "- TypeScript strict mode + ESLint compliance\n"
        "- Never modify core governance components (circuit_breaker, state_machine, "
        "audit_logger, meta_governance, evolution_dsl)\n"
        "- Never bypass safety assertions or downgrade security levels\n"
        "- Output a single complete TypeScript/TSX file\n"
        "- Output raw code only — NO markdown fences, NO backticks, NO explanation\n"
        "- Keep generated code under 200 lines — concise, focused, no boilerplate\n"
        "- Preserve existing imports unless removing unused ones\n"
        "- React 19+ hooks patterns, functional components only\n"
        "\n"
        "React 19 ESLint rule fix patterns (use these EXACT patterns):\n"
        "- react-hooks/static-components: NEVER assign a component to a variable\n"
        "  then render it as <Var />. The rule forbids dynamic component lookup\n"
        "  during render. Instead use static conditional rendering:\n"
        "    // BAD: const Icon = map[ext]; return <Icon className=\"x\" />;\n"
        "    // GOOD: if (ext === '.ts') return <FileCode className=\"x\" />;\n"
        "    //        if (ext === '.json') return <FileJson className=\"x\" />;\n"
        "    //        return <File className=\"x\" />;\n"
        "- react-hooks/set-state-in-effect: NEVER call setState unconditionally\n"
        "  inside useEffect. Guard with a ref or condition to avoid infinite loop.\n"
        "- react-hooks/exhaustive-deps: list ALL reactive dependencies in the\n"
        "  dependency array, or wrap unstable values in useCallback/useMemo.\n"
    )

    @staticmethod
    def build_prompt(
        proposal: ArchitectureProposal,
        project_context: SystemSnapshot | None = None,
        affected_files: list[str] | None = None,
        feedback: str | None = None,
    ) -> tuple[str, str]:
        user_lines: list[str] = [
            f"# Change type: {proposal.change_type.value if hasattr(proposal.change_type, 'value') else proposal.change_type}",
            f"# Rationale: {proposal.rationale}",
        ]

        if hasattr(proposal, "target_files") and proposal.target_files:
            user_lines.append("# Target files:")
            for tf in proposal.target_files:
                user_lines.append(f"#   - {tf}")

        if hasattr(proposal, "affected_symbols") and proposal.affected_symbols:
            user_lines.append("# Affected symbols:")
            for sym in proposal.affected_symbols:
                user_lines.append(f"#   - {sym}")

        # Detect TypeScript targets to pick the right system prompt
        is_ts = bool(
            affected_files
            and any(f.endswith((".ts", ".tsx")) for f in affected_files)
        )

        if affected_files:
            for fp in affected_files:
                if fp.endswith((".ts", ".tsx")):
                    # TS files: read raw content (ast.parse cannot handle TypeScript)
                    # Fix 19: include enough lines to cover all error locations.
                    # The old limit of 80 lines meant errors past line 80 (e.g.,
                    # FileTreeItem.tsx L109 react-hooks/static-components) were
                    # invisible to the LLM, causing repeated failed fixes.
                    try:
                        with open(fp) as f:
                            lines = f.readlines()
                        # Determine the last error line for this file from
                        # affected_symbols (format: "L{n}:rule — msg").
                        max_err_line = 0
                        for sym in (proposal.affected_symbols or []):
                            try:
                                prefix = sym.split(":", 1)[0]  # e.g. "L109"
                                if prefix.startswith("L"):
                                    max_err_line = max(max_err_line, int(prefix[1:]))
                            except (ValueError, IndexError):
                                pass
                        # Read up to max(80, max_err_line + 20), capped at 250.
                        read_limit = min(250, max(80, max_err_line + 20))
                        user_lines.append(
                            f"\n# Current content of {fp} (first {read_limit} lines):"
                        )
                        for line in lines[:read_limit]:
                            user_lines.append(line.rstrip("\n"))
                    except OSError:
                        user_lines.append(f"\n# Could not read {fp}")
                else:
                    # Python files: full content + AST summary
                    # Fix 24: provide full file content (like TS files) so the
                    # LLM can resolve cross-module references for F821 (undefined
                    # name) and other context-dependent ruff errors. The AST
                    # summary alone (class/function names) doesn't give the LLM
                    # enough information to add missing imports or define
                    # variables that ruff cannot auto-fix.
                    try:
                        with open(fp) as f:
                            lines = f.readlines()
                        # Same max_err_line logic as TS files (Fix 19)
                        max_err_line = 0
                        for sym in (proposal.affected_symbols or []):
                            try:
                                prefix = sym.split(":", 1)[0]  # e.g. "L109"
                                if prefix.startswith("L"):
                                    max_err_line = max(max_err_line, int(prefix[1:]))
                            except (ValueError, IndexError):
                                pass
                        read_limit = min(250, max(80, max_err_line + 20))
                        user_lines.append(
                            f"\n# Current content of {fp} (first {read_limit} lines):"
                        )
                        for line in lines[:read_limit]:
                            user_lines.append(line.rstrip("\n"))
                        # AST summary as structured overview (bonus context)
                        import ast as _ast
                        try:
                            content = "".join(lines)
                            tree = _ast.parse(content)
                            classes = [
                                n.name for n in _ast.walk(tree) if isinstance(n, _ast.ClassDef)
                            ]
                            functions = [
                                n.name for n in _ast.walk(tree) if isinstance(n, _ast.FunctionDef)
                            ]
                            imports = [
                                (n.names[0].name if isinstance(n, _ast.Import) else n.module)
                                for n in _ast.walk(tree)
                                if isinstance(n, (_ast.Import, _ast.ImportFrom))
                            ][:30]
                            user_lines.append(f"\n# AST summary for {fp}:")
                            user_lines.append(f"#   classes: {classes}")
                            user_lines.append(f"#   functions: {functions}")
                            user_lines.append(f"#   imports: {imports}")
                        except SyntaxError:
                            pass
                    except OSError:
                        user_lines.append(f"\n# Could not read {fp}")

        if feedback:
            user_lines.append(f"\n# Feedback from previous attempt:\n{feedback}")

        user_lines.append("\n# Generate the complete file below:")
        user_prompt = "\n".join(user_lines)

        system_prompt = (
            CodeContextBuilder.TS_SYSTEM_PROMPT_TEMPLATE
            if is_ts
            else CodeContextBuilder.SYSTEM_PROMPT_TEMPLATE
        )
        return system_prompt, user_prompt


class MockProvider:
    def __init__(self, stub_content: str = "") -> None:
        self._stub = stub_content or (
            "from __future__ import annotations\n\n\n"
            "def generated_function() -> str:\n"
            '    return "generated by MockProvider"\n'
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        return self._stub

    @property
    def name(self) -> str:
        return "mock"

    @property
    def cost_per_token(self) -> tuple[float, float]:
        return (0.0, 0.0)


class LLMCodeGenerator:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        context_builder: CodeContextBuilder | None = None,
    ) -> None:
        if provider is None:
            provider = self._detect_provider()
        self._provider = provider or MockProvider()
        self._context_builder = context_builder or CodeContextBuilder()

    @staticmethod
    def _detect_provider() -> LLMProvider | None:
        if os.environ.get("OPENAI_API_KEY"):
            try:
                import openai  # noqa: F401
                return OpenAIProvider()
            except ImportError:
                pass
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic  # noqa: F401
                return AnthropicProvider()
            except ImportError:
                pass
        return None

    async def generate(
        self,
        proposal: ArchitectureProposal,
        snapshot: SystemSnapshot | None = None,
        feedback: str | None = None,
    ) -> LLMCodeGenResult:
        affected_files = list(getattr(proposal, "target_files", []) or [])
        system_prompt, user_prompt = self._context_builder.build_prompt(
            proposal=proposal,
            project_context=snapshot,
            affected_files=affected_files,
            feedback=feedback,
        )

        try:
            output = await self._provider.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
            )
        except Exception as e:
            return LLMCodeGenResult(
                success=False,
                validation_errors=[f"Provider error: {e}"],
                provider_name=self._provider.name,
            )

        validation_errors: list[str] = []
        output = self._strip_markdown_fences(output)
        # Skip ast.parse for TypeScript — it only validates Python syntax
        is_ts = any(f.endswith((".ts", ".tsx")) for f in affected_files)
        if not is_ts:
            try:
                ast.parse(output)
            except SyntaxError as e:
                validation_errors.append(f"Syntax error in generated code: {e}")

        gen = self._create_generated_code(output, proposal)
        if validation_errors:
            return LLMCodeGenResult(
                success=False,
                generated=[gen],
                validation_errors=validation_errors,
                provider_name=self._provider.name,
            )

        return LLMCodeGenResult(
            success=True,
            generated=[gen],
            provider_name=self._provider.name,
        )

    @staticmethod
    def _strip_markdown_fences(output: str) -> str:
        lines = output.split("\n")
        cleaned = [l for l in lines if not l.startswith("```")]
        result = "\n".join(cleaned).strip()
        if not result:
            return output.strip()
        return result

    def estimate_cost(self, proposal: ArchitectureProposal) -> float:
        prompt_chars = (
            len(proposal.rationale)
            + sum(len(tf) for tf in getattr(proposal, "target_files", []) or [])
        )
        est_tokens = prompt_chars // 4
        input_cost, output_cost = self._provider.cost_per_token
        return est_tokens * input_cost + 200 * output_cost

    def _create_generated_code(
        self, content: str, proposal: ArchitectureProposal
    ) -> Any:
        from maref.recursive.self_executor import GeneratedCode

        target = (
            proposal.target_files[0]
            if getattr(proposal, "target_files", None)
            else f"rel_gen_{uuid.uuid4().hex[:8]}.py"
        )
        language = "typescript" if target.endswith((".ts", ".tsx")) else "python"
        return GeneratedCode(
            file_path=target,
            content=content,
            target_module=getattr(proposal, "proposed_arch", target),
            language=language,
        )

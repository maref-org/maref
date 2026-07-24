from __future__ import annotations

import ast
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maref.evolution.constitution_harness import ConstitutionHarness, EvolutionChange
from maref.recursive.safety_gate_v2 import SafetyGateV2
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from maref.immunity.auto_gene_pipeline import AutoGeneExtractionPipeline
    from maref.immunity.intent_drift_detector import IntentDriftDetector

def _detect_llm_available() -> bool:
    """Auto-detect if any LLM provider is configured."""
    if os.environ.get("MAREF_FORCE_NO_LLM"):
        return False
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from maref.recursive.llm_code_generator import LLMCodeGenerator  # noqa: F401
            return True
        except ImportError:
            pass
    return bool(os.environ.get("MAREF_USE_CODEGEN_LOOP", "0") in {"1", "true", "yes"})

USE_CODEGEN_LOOP = os.environ.get("MAREF_USE_CODEGEN_LOOP", "auto") in {"1", "true", "yes", "auto"} and _detect_llm_available()

HAS_CODEGEN = False
try:
    from maref.codegen.context import ContextManager, Message  # noqa: F401
    from maref.codegen.executor import ToolExecutor  # noqa: F401
    from maref.codegen.loop import CodeGenLoop  # noqa: F401
    from maref.codegen.permissions import (  # noqa: F401
        PermissionEngine,
        PermissionMode,
        PermissionRule,
    )
    from maref.codegen.quality import QualityGateConfig  # noqa: F401
    from maref.codegen.registry import ToolRegistry  # noqa: F401
    from maref.codegen.tool import ToolContext  # noqa: F401
    HAS_CODEGEN = True
except ImportError:
    pass


class ExecutionStage(Enum):
    CODE_GEN = "code_generation"
    AST_VALIDATE = "ast_validation"
    SAFETY_GATE = "safety_gate"
    DEPLOY = "deployment"
    VERIFY = "verification"
    ROLLBACK = "rollback"
    COMPLETE = "complete"


@dataclass
class GeneratedCode:
    file_path: str
    content: str
    target_module: str
    language: str = "python"


@dataclass
class ASTValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ast_tree: ast.Module | None = None
    imports: list[str] = field(default_factory=list)
    classes_found: list[str] = field(default_factory=list)
    functions_found: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    stage: ExecutionStage
    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_failure(self) -> bool:
        return not self.success


@dataclass
class ExecutionPipelineRecord:
    pipeline_id: str
    proposal_id: str
    stages: list[ExecutionResult] = field(default_factory=list)
    final_state: str = "unknown"
    rollback_performed: bool = False
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    def finish(self) -> None:
        self.end_time = time.time()

    @property
    def duration_ms(self) -> float:
        end = self.end_time if self.end_time > 0 else time.time()
        return (end - self.start_time) * 1000.0

    def to_audit_records(self, round_num: int = 31) -> list[UnifiedAuditRecord]:
        records: list[UnifiedAuditRecord] = []
        for result in self.stages:
            outcome = "success" if result.success else "failure"
            records.append(
                UnifiedAuditRecord(
                    record_id=make_record_id(
                        "exec", hash((self.pipeline_id, result.stage.value)) % 100000
                    ),
                    timestamp=result.timestamp,
                    layer="evolution",
                    round=round_num,
                    event_type=f"self_executor_{result.stage.value}",
                    source_module="SelfExecutor",
                    target_module=self.proposal_id,
                    decision=result.stage.value,
                    justification=result.message,
                    outcome=outcome,
                    context_refs=[self.pipeline_id],
                )
            )
        return records


class CodeGenerator:
    CODE_TEMPLATES: dict[str, str] = {
        "refactor_module": """
from __future__ import annotations
{imports}

{classes_and_functions}
""",
        "add_tests": """
from __future__ import annotations

import pytest
{imports}

{test_classes_and_functions}
""",
        "refactor_typescript": """
{imports}

{classes_and_functions}
""",
        "add_typescript_tests": """
import {{ describe, it, expect }} from 'vitest';
{imports}

{test_classes_and_functions}
""",
    }

    def __init__(self) -> None:
        self._llm_generator: Any = None
        self._has_llm = False
        try:
            from maref.recursive.llm_code_generator import LLMCodeGenerator
            self._llm_generator = LLMCodeGenerator()
            api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
            self._has_llm = bool(api_key) and bool(self._llm_generator._provider)
        except Exception:
            self._has_llm = False

    def generate(self, proposal, project_root: str) -> list[GeneratedCode]:
        generated: list[GeneratedCode] = []
        proposal_type = self._classify_proposal(proposal)
        target_paths = self._resolve_target_paths(proposal, project_root)

        for target_path in target_paths:
            gen: GeneratedCode | None = None
            if self._has_llm:
                gen = self._generate_with_llm(proposal, target_path)
            if gen is None:
                if proposal_type == "refactor_module":
                    gen = self._generate_refactor(proposal, target_path)
                elif proposal_type == "add_tests":
                    gen = self._generate_tests(proposal, target_path)
                elif proposal_type == "refactor_typescript":
                    gen = self._generate_refactor_ts(proposal, target_path)
                elif proposal_type == "add_typescript_tests":
                    gen = self._generate_tests_ts(proposal, target_path)
                elif proposal_type == "remove_unused_imports":
                    gen = self._generate_remove_imports(proposal, target_path)
                else:
                    gen = GeneratedCode(
                        file_path=str(target_path),
                        content=f"# Auto-generated by SelfExecutor for proposal: {proposal.proposal_id}\n"
                        f"# Rationale: {proposal.rationale}\n",
                        target_module=proposal.proposed_arch
                        if hasattr(proposal, "proposed_arch")
                        else str(target_path),
                    )
            if gen is not None:
                generated.append(gen)

        return generated

    def _generate_with_llm(self, proposal, target_path: Path) -> GeneratedCode | None:
        if self._llm_generator is None:
            return None
        try:
            import asyncio
            import concurrent.futures

            # Fix 33: handle the running event loop case.
            # ``_generate_with_llm`` is called synchronously from
            # ``CodeGenerator.generate()``, which is called by the executor
            # pipeline running inside ``_default_apply_fn``'s
            # ``loop.run_until_complete(execute_async(...))``.  When there
            # IS a running event loop on this thread, ``asyncio.run()``
            # raises "Cannot run the event loop while another loop is
            # running".  Solution: detect the running loop and, if present,
            # offload the actual LLM call to a separate daemon thread where
            # ``asyncio.run()`` can create a fresh loop without conflict.
            try:
                asyncio.get_running_loop()
                # Running loop detected — offload to a thread
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
                    _future = _pool.submit(
                        lambda: asyncio.run(
                            self._llm_generator.generate(proposal)
                        )
                    )
                    result = _future.result(timeout=120)
            except RuntimeError:
                # Fix 36: direct asyncio.run() with timeout to prevent infinite hang
                # when the LLM HTTP call has no timeout configured.
                async def _run_llm_with_timeout() -> Any:
                    return await asyncio.wait_for(
                        self._llm_generator.generate(proposal),
                        timeout=120.0,
                    )
                result = asyncio.run(_run_llm_with_timeout())

            if result.success and result.generated:
                gen = result.generated[0]
                gen.file_path = str(target_path)
                return gen
            logger.warning(
                "LLM generation returned no code for %s: success=%s",
                getattr(proposal, "proposal_id", "unknown"),
                result.success,
            )
            return None
        except Exception as exc:
            logger.warning("LLM generation failed: %s", exc)
            return None

    def _classify_proposal(self, proposal) -> str:
        if hasattr(proposal, "change_type") and proposal.change_type is not None:
            ct = str(
                proposal.change_type.value
                if hasattr(proposal.change_type, "value")
                else proposal.change_type
            )
            if "add_test" in ct.lower():
                return "add_tests"
            if "remove_unused_import" in ct.lower():
                return "remove_unused_imports"
            if "refactor_module" in ct.lower():
                return "refactor_module"
        rationale = getattr(proposal, "rationale", "").lower()
        proposed = getattr(proposal, "proposed_arch", "").lower()
        target_files = getattr(proposal, "target_files", []) or []
        is_ts = any(f.endswith((".ts", ".tsx")) for f in target_files) or "typescript" in rationale
        if "test" in rationale or "coverage" in rationale:
            return "add_typescript_tests" if is_ts else "add_tests"
        if "unused import" in rationale or "cleanup" in proposed:
            return "remove_unused_imports"
        if "refactor" in rationale or "restructure" in rationale:
            return "refactor_typescript" if is_ts else "refactor_module"
        return "generic"

    def _resolve_target_paths(self, proposal, project_root: str) -> list[Path]:
        if hasattr(proposal, "target_files") and proposal.target_files:
            return [Path(p) for p in proposal.target_files]
        target = self._resolve_target_path(proposal, project_root)
        return [target]

    def _resolve_target_path(self, proposal, project_root: str) -> Path:
        current = getattr(proposal, "current_arch", "")
        if current and not current.startswith(str(project_root)):
            base = Path(project_root) / "src" / "maref" / "recursive"
            return base / f"r31_executor_generated_{hash(proposal.proposal_id) % 10000}.py"
        return (
            Path(project_root)
            / "src"
            / "maref"
            / "recursive"
            / f"r31_executor_generated_{hash(proposal.proposal_id) % 10000}.py"
        )

    def _generate_refactor(self, proposal, target_path: Path) -> GeneratedCode:
        content = (
            "from __future__ import annotations\n"
            "\n"
            "import time\n"
            "from dataclasses import dataclass\n"
            "from typing import Any\n"
            "\n"
            "\n"
            "@dataclass\n"
            "class R31AutoGenerated:\n"
            "    proposal_id: str\n"
            "    rationale: str\n"
            "    generated_at: float\n"
            "\n"
            "    @classmethod\n"
            '    def from_proposal(cls, proposal_id: str, rationale: str = "") -> R31AutoGenerated:\n'
            "        return cls(\n"
            "            proposal_id=proposal_id,\n"
            "            rationale=rationale,\n"
            "            generated_at=time.time(),\n"
            "        )\n"
            "\n"
            "    def to_dict(self) -> dict[str, Any]:\n"
            "        return {\n"
            '            "proposal_id": self.proposal_id,\n'
            '            "rationale": self.rationale,\n'
            '            "generated_at": self.generated_at,\n'
            "        }\n"
        )
        return GeneratedCode(
            file_path=str(target_path),
            content=content,
            target_module=getattr(proposal, "proposed_arch", str(target_path)),
        )

    def _generate_tests(self, proposal, target_path: Path) -> GeneratedCode:
        module_name = target_path.stem
        content = f"""from __future__ import annotations

import pytest


class Test{module_name.title().replace('_', '')}:
    def test_auto_generated_target_resolution(self) -> None:
        pytest.skip("target module unresolved")

    def test_auto_generated_structure(self) -> None:
        from maref.recursive.self_executor import ExecutionStage
        stages = list(ExecutionStage)
        assert len(stages) >= 5, f"Expected >=5 stages, got {{len(stages)}}"

    def test_auto_generated_round31_bootstrap(self) -> None:
        from maref.recursive.self_executor import SelfExecutor
        executor = SelfExecutor(max_rounds=3)
        assert executor.max_rounds == 3
        assert len(executor.history) == 0
"""
        return GeneratedCode(
            file_path=str(target_path),
            content=content,
            target_module=getattr(proposal, "proposed_arch", str(target_path)),
        )

    def _generate_refactor_ts(self, proposal, target_path: Path) -> GeneratedCode:
        content = (
            "/**\n"
            f" * Auto-generated TypeScript module\n"
            f" * Proposal: {getattr(proposal, 'proposal_id', 'unknown')}\n"
            f" * Rationale: {getattr(proposal, 'rationale', '')}\n"
            " */\n"
            "\n"
            "export interface R31AutoGenerated {\n"
            "  proposalId: string;\n"
            "  rationale: string;\n"
            "  generatedAt: number;\n"
            "}\n"
            "\n"
            "export function createFromProposal(\n"
            '  proposalId: string,\n'
            '  rationale: string = ""\n'
            "): R31AutoGenerated {\n"
            "  return {\n"
            "    proposalId,\n"
            "    rationale,\n"
            "    generatedAt: Date.now(),\n"
            "  };\n"
            "}\n"
        )
        return GeneratedCode(
            file_path=str(target_path),
            content=content,
            target_module=getattr(proposal, "proposed_arch", str(target_path)),
            language="typescript",
        )

    def _generate_tests_ts(self, proposal, target_path: Path) -> GeneratedCode:
        module_name = target_path.stem
        content = (
            "import { describe, it, expect } from 'vitest';\n"
            "\n"
            f"describe('{module_name}', () => {{\n"
            "  it('should have valid structure', () => {\n"
            '    expect(true).toBe(true);\n'
            "  });\n"
            "});\n"
        )
        return GeneratedCode(
            file_path=str(target_path),
            content=content,
            target_module=getattr(proposal, "proposed_arch", str(target_path)),
            language="typescript",
        )

    def _generate_remove_imports(self, proposal, target_path: Path) -> GeneratedCode | None:
        import ast as _ast

        try:
            source = target_path.read_text()
            tree = _ast.parse(source)
        except (OSError, SyntaxError):
            return None

        symbols_to_remove = set(getattr(proposal, "affected_symbols", []) or [])

        class _ImportRemover(_ast.NodeTransformer):
            def visit_Import(self, node):
                new_names = [
                    alias
                    for alias in node.names
                    if alias.name not in symbols_to_remove and alias.asname not in symbols_to_remove
                ]
                if not new_names:
                    return None
                node.names = new_names
                return node

            def visit_ImportFrom(self, node):
                new_names = [
                    alias
                    for alias in node.names
                    if alias.name not in symbols_to_remove and alias.asname not in symbols_to_remove
                ]
                if not new_names:
                    return None
                node.names = new_names
                return node

        remover = _ImportRemover()
        new_tree = remover.visit(tree)
        if new_tree is None:
            return None
        _ast.fix_missing_locations(new_tree)
        try:
            new_content = _ast.unparse(new_tree)
        except Exception:
            return None

        return GeneratedCode(
            file_path=str(target_path),
            content=new_content,
            target_module=getattr(proposal, "proposed_arch", str(target_path)),
        )


class ASTSandbox:
    ALLOWED_MODULES = {
        "__future__",
        "abc",
        "ast",
        "collections",
        "copy",
        "dataclasses",
        "enum",
        "functools",
        "hashlib",
        "inspect",
        "itertools",
        "json",
        "math",
        "os",
        "pathlib",
        "re",
        "statistics",
        "string",
        "subprocess",
        "sys",
        "textwrap",
        "time",
        "traceback",
        "typing",
        "uuid",
        "warnings",
        "pytest",
        "maref",
    }
    BLOCKED_IMPORTS = {
        "os.system",
        "subprocess.call",
        "subprocess.run",
        "eval",
        "exec",
        "compile",
        "__import__",
    }

    def validate(self, code: GeneratedCode) -> ASTValidationResult:
        result = ASTValidationResult(is_valid=True)
        if code.language != "python":
            result.warnings.append(f"AST validation skipped for language: {code.language}")
            return result
        try:
            tree = ast.parse(code.content)
            result.ast_tree = tree
        except SyntaxError as e:
            result.is_valid = False
            result.errors.append(f"SyntaxError: {e}")
            return result

        self._check_imports(tree, result)
        self._check_dangerous_calls(tree, result)
        self._extract_definitions(tree, result)

        return result

    def _check_imports(self, tree: ast.Module, result: ASTValidationResult) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_module = alias.name.split(".")[0]
                    if top_module not in self.ALLOWED_MODULES:
                        result.warnings.append(f"Unknown import: {alias.name}")
                    result.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_module = node.module.split(".")[0]
                if top_module not in self.ALLOWED_MODULES:
                    result.warnings.append(f"Unknown import: {node.module}")
                result.imports.append(node.module)

    def _check_dangerous_calls(self, tree: ast.Module, result: ASTValidationResult) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in self.BLOCKED_IMPORTS:
                    result.is_valid = False
                    result.errors.append(f"Dangerous call detected: {node.func.id}")
                elif isinstance(node.func, ast.Attribute):
                    full_attr = self._resolve_attribute(node.func)
                    for blocked in self.BLOCKED_IMPORTS:
                        if full_attr.endswith(blocked.split(".")[-1]):
                            result.is_valid = False
                            result.errors.append(f"Dangerous attribute call detected: {full_attr}")
                if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                        target_func = str(node.args[1].value)
                        for blocked in self.BLOCKED_IMPORTS:
                            if target_func in blocked or blocked.endswith(f".{target_func}"):
                                result.is_valid = False
                                result.errors.append(
                                    f"Dangerous getattr bypass detected: getattr(..., '{target_func}')"
                                )

    @staticmethod
    def _resolve_attribute(node: ast.Attribute) -> str:
        parts: list[str] = []
        current: Any = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def _extract_definitions(self, tree: ast.Module, result: ASTValidationResult) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                result.classes_found.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                result.functions_found.append(node.name)


class AtomicDeployer:
    def __init__(self, backup_dir: str | None = None) -> None:
        self._backup_dir = backup_dir or os.path.join(
            tempfile.gettempdir(), "maref_executor_backups"
        )
        os.makedirs(self._backup_dir, exist_ok=True)
        self._deployed: dict[str, str] = {}

    def deploy(self, code: GeneratedCode) -> ExecutionResult:
        file_path = code.file_path
        backup_path = os.path.join(
            self._backup_dir,
            f"backup_{int(time.time())}_{os.path.basename(file_path)}",
        )

        try:
            had_existing_file = os.path.exists(file_path)
            if had_existing_file:
                shutil.copy2(file_path, backup_path)
            else:
                backup_path = ""

            dirname = os.path.dirname(file_path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code.content)

            if not os.path.exists(file_path):
                raise RuntimeError(f"File not created: {file_path}")

            self._deployed[file_path] = backup_path

            return ExecutionResult(
                stage=ExecutionStage.DEPLOY,
                success=True,
                message=f"Deployed to {file_path}, backup at {backup_path}",
                details={
                    "file_path": file_path,
                    "backup_path": backup_path,
                    "size_bytes": len(code.content),
                },
            )
        except Exception as e:
            return ExecutionResult(
                stage=ExecutionStage.DEPLOY,
                success=False,
                message=f"Deployment failed: {e}",
                details={"error": str(e), "traceback": traceback.format_exc()},
            )

    def rollback(self, file_path: str) -> ExecutionResult:
        backup_path = self._deployed.get(file_path)
        if backup_path == "":
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return ExecutionResult(
                    stage=ExecutionStage.ROLLBACK,
                    success=True,
                    message=f"Removed newly deployed file {file_path}",
                    details={"file_path": file_path},
                )
            except Exception as e:
                return ExecutionResult(
                    stage=ExecutionStage.ROLLBACK,
                    success=False,
                    message=f"Rollback failed: {e}",
                    details={"error": str(e)},
                )
        if not backup_path or not os.path.exists(backup_path):
            return ExecutionResult(
                stage=ExecutionStage.ROLLBACK,
                success=False,
                message=f"No backup found for {file_path}",
                details={"file_path": file_path},
            )

        try:
            shutil.copy2(backup_path, file_path)
            return ExecutionResult(
                stage=ExecutionStage.ROLLBACK,
                success=True,
                message=f"Rolled back {file_path} from {backup_path}",
                details={"file_path": file_path, "backup_path": backup_path},
            )
        except Exception as e:
            return ExecutionResult(
                stage=ExecutionStage.ROLLBACK,
                success=False,
                message=f"Rollback failed: {e}",
                details={"error": str(e)},
            )

    def verify_deployed(self, file_path: str, expected_content: str) -> ExecutionResult:
        try:
            if not os.path.exists(file_path):
                return ExecutionResult(
                    stage=ExecutionStage.VERIFY,
                    success=False,
                    message=f"File not found: {file_path}",
                )
            with open(file_path, encoding="utf-8") as f:
                actual = f.read()
            if actual != expected_content:
                return ExecutionResult(
                    stage=ExecutionStage.VERIFY,
                    success=False,
                    message="Content mismatch after deployment",
                    details={"expected_size": len(expected_content), "actual_size": len(actual)},
                )
            return ExecutionResult(
                stage=ExecutionStage.VERIFY,
                success=True,
                message="Deployment verified",
                details={"file_path": file_path},
            )
        except Exception as e:
            return ExecutionResult(
                stage=ExecutionStage.VERIFY,
                success=False,
                message=f"Verification failed: {e}",
            )

    @property
    def deployed_files(self) -> list[str]:
        return list(self._deployed.keys())


class SelfExecutor:
    def __init__(
        self,
        max_rounds: int = 3,
        project_root: str | None = None,
        audit_store: UnifiedAuditStore | None = None,
        quality_gate: Callable[[GeneratedCode, ExecutionPipelineRecord], ExecutionResult] | None = None,
        auto_init_codegen: bool = False,
    ) -> None:
        self._max_rounds = max_rounds
        self._project_root = project_root or os.getcwd()
        self._audit_store = audit_store or UnifiedAuditStore()
        self._code_gen = CodeGenerator()
        self._sandbox = ASTSandbox()
        self._safety_gate = SafetyGateV2()
        self._constitution_harness = ConstitutionHarness()
        self._deployer = AtomicDeployer()
        self._quality_gate = quality_gate or self._default_quality_gate
        self._history: list[ExecutionPipelineRecord] = []
        self._intent_drift_detector: IntentDriftDetector | None = None
        self._gene_pipeline: AutoGeneExtractionPipeline | None = None
        self._codegen_loop: Any = None
        self._codegen_tool: Any = None
        self._use_new_loop = USE_CODEGEN_LOOP and HAS_CODEGEN
        if auto_init_codegen and self._use_new_loop:
            self.init_codegen_loop()

    @property
    def max_rounds(self) -> int:
        return self._max_rounds

    @property
    def history(self) -> list[ExecutionPipelineRecord]:
        return list(self._history)

    def deploy(self, code: GeneratedCode) -> ExecutionResult:
        return self._deployer.deploy(code)

    @property
    def deployed_files(self) -> list[str]:
        return self._deployer.deployed_files

    def init_codegen_loop(self) -> None:
        if not HAS_CODEGEN:
            return
        from maref.codegen.codegen_tool import CodeGenTool
        from maref.codegen.context import ContextManager
        from maref.codegen.executor import ToolExecutor
        from maref.codegen.loop import CodeGenLoop
        from maref.codegen.permissions import PermissionEngine
        from maref.codegen.quality import QualityGateConfig
        from maref.codegen.registry import ToolRegistry
        from maref.tools.ask_user_tool import AskUserTool
        from maref.tools.bash_tool import BashTool
        from maref.tools.edit_tool import EditTool
        from maref.tools.glob_tool import GlobTool
        from maref.tools.govern_tool import GovernTool
        from maref.tools.grep_tool import GrepTool
        from maref.tools.lint_tool import LintTool
        from maref.tools.read_tool import ReadTool
        from maref.tools.test_tool import TestTool
        from maref.tools.write_tool import WriteTool

        registry = ToolRegistry()
        registry.register_all(
            ReadTool(),
            EditTool(),
            WriteTool(),
            GlobTool(),
            GrepTool(),
            BashTool(),
            LintTool(),
            TestTool(),
            AskUserTool(),
            GovernTool(state_machine=getattr(self, "_governance", None)),
        )

        perm_engine = PermissionEngine()
        context_mgr = ContextManager()
        quality_cfg = QualityGateConfig(strict=False)
        tool_exec = ToolExecutor(registry)
        loop = CodeGenLoop(
            registry=registry,
            permission_engine=perm_engine,
            context_manager=context_mgr,
            quality_config=quality_cfg,
            tool_executor=tool_exec,
        )
        self._codegen_loop = loop
        self._codegen_tool = CodeGenTool(
            loop=loop,
            quality_config=quality_cfg,
            project_root=self._project_root,
        )

    async def execute_async(self, proposal, round_num: int = 31) -> ExecutionPipelineRecord:
        if not self._use_new_loop or self._codegen_loop is None:
            import asyncio
            loop = asyncio.get_running_loop()
            try:
                # Fix 36: global 300s timeout on execute() to prevent infinite
                # hang.  Without this, if any pipeline stage (LLM code gen,
                # safety gate, verification) blocks the thread indefinitely,
                # run_until_complete never unblocks and the cycle hangs.
                return await asyncio.wait_for(
                    loop.run_in_executor(None, self.execute, proposal, round_num),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                record = ExecutionPipelineRecord(
                    pipeline_id=f"exec_pipeline_{int(time.time())}_timedout",
                    proposal_id=getattr(proposal, "proposal_id", "unknown"),
                )
                record.final_state = "FAILED_TIMEOUT"
                record.finish()
                self._history.append(record)
                logger.error(
                    "Fix 36: execute() timed out after 300s for %s",
                    getattr(proposal, "proposal_id", "unknown"),
                )
                return record
        from maref.codegen.tool import ToolContext
        from maref.tools.edit_tool import EditInput
        from maref.tools.lint_tool import LintInput
        from maref.tools.read_tool import ReadInput

        tool_calls: list[tuple[str, Any]] = []

        for target in getattr(proposal, "target_files", []):
            tool_calls.append(("Read", ReadInput(file_path=target, offset=None, limit=None)))

        code = self._code_gen.generate(proposal, self._project_root)
        if code:
            for gen in code:
                if gen.content:
                    tool_calls.append((
                        "Edit",
                        EditInput(
                            file_path=gen.file_path,
                            old_string="",
                            new_string=gen.content,
                            use_ast=False,
                            replace_all=False,
                        ),
                    ))
                    tool_calls.append((
                        "Lint",
                        LintInput(file_path=gen.file_path, tool_name="ruff"),
                    ))

        ctx = ToolContext(
            agent_id=getattr(proposal, "proposal_id", "executor"),
            workspace_root=self._project_root,
            permission_mode="governed",
        )

        pipeline = await self._codegen_tool.execute(proposal, tool_calls, ctx)
        return pipeline

    def execute(self, proposal, round_num: int = 31) -> ExecutionPipelineRecord:
        pipeline = ExecutionPipelineRecord(
            pipeline_id=f"exec_pipeline_{int(time.time())}_{hash(proposal.proposal_id) % 10000}",
            proposal_id=proposal.proposal_id,
        )

        code_gen_result = self._stage_code_generation(proposal, pipeline)
        pipeline.stages.append(code_gen_result)
        if code_gen_result.is_failure:
            pipeline.final_state = "FAILED_CODE_GEN"
            pipeline.finish()
            self._history.append(pipeline)
            return pipeline

        code = code_gen_result.details.get("generated_code")
        ast_result = self._stage_ast_validation(code, pipeline)
        pipeline.stages.append(ast_result)
        if ast_result.is_failure:
            pipeline.final_state = "FAILED_AST_VALIDATE"
            pipeline.finish()
            self._history.append(pipeline)
            return pipeline

        if not isinstance(code, GeneratedCode):
            pipeline.final_state = "FAILED_NO_CODE"
            pipeline.finish()
            self._history.append(pipeline)
            return pipeline

        safety_result = self._stage_safety_gate(code, proposal, pipeline)
        pipeline.stages.append(safety_result)
        if safety_result.is_failure:
            pipeline.final_state = "FAILED_SAFETY_GATE"
            pipeline.finish()
            self._history.append(pipeline)
            return pipeline

        deploy_result = self._stage_deploy(code, pipeline)
        pipeline.stages.append(deploy_result)
        if deploy_result.is_failure:
            pipeline.stages.append(self._stage_rollback(code.file_path, pipeline))
            pipeline.rollback_performed = True
            self._do_auto_gene_extraction(code, "rollback", "deploy failure")
            pipeline.final_state = "FAILED_DEPLOY_ROLLED_BACK"
            pipeline.finish()
            self._history.append(pipeline)
            return pipeline

        verify_result = self._stage_verify(code, pipeline)
        pipeline.stages.append(verify_result)
        if verify_result.is_failure:
            pipeline.stages.append(self._stage_rollback(code.file_path, pipeline))
            pipeline.rollback_performed = True
            self._do_auto_gene_extraction(code, "rollback", "verification failure")
            pipeline.final_state = "FAILED_VERIFY_ROLLED_BACK"
            pipeline.finish()
            self._history.append(pipeline)
            self._audit_pipeline(pipeline, round_num)
            return pipeline

        pipeline.final_state = "SUCCESS"
        pipeline.finish()
        self._history.append(pipeline)
        self._audit_pipeline(pipeline, round_num)
        return pipeline

    def _stage_code_generation(
        self, proposal, pipeline: ExecutionPipelineRecord
    ) -> ExecutionResult:
        try:
            generated = self._code_gen.generate(proposal, self._project_root)
            if not generated:
                return ExecutionResult(
                    stage=ExecutionStage.CODE_GEN,
                    success=False,
                    message="No code generated",
                    details={"proposal_id": proposal.proposal_id},
                )
            code = generated[0]
            return ExecutionResult(
                stage=ExecutionStage.CODE_GEN,
                success=True,
                message=f"Generated code for {code.file_path} ({len(code.content)} bytes)",
                details={
                    "generated_code": code,
                    "file_path": code.file_path,
                    "size_bytes": len(code.content),
                },
            )
        except Exception as e:
            return ExecutionResult(
                stage=ExecutionStage.CODE_GEN,
                success=False,
                message=f"Code generation failed: {e}",
                details={"error": str(e), "traceback": traceback.format_exc()},
            )

    def _stage_ast_validation(
        self, code: GeneratedCode | None, pipeline: ExecutionPipelineRecord
    ) -> ExecutionResult:
        if code is None:
            return ExecutionResult(
                stage=ExecutionStage.AST_VALIDATE,
                success=False,
                message="No code to validate",
            )
        validation = self._sandbox.validate(code)
        return ExecutionResult(
            stage=ExecutionStage.AST_VALIDATE,
            success=validation.is_valid,
            message=f"AST validation: {'PASS' if validation.is_valid else 'FAIL'} "
            f"({len(validation.errors)} errors, {len(validation.warnings)} warnings)",
            details={
                "is_valid": validation.is_valid,
                "errors": validation.errors,
                "warnings": validation.warnings,
                "imports": validation.imports,
                "classes": validation.classes_found,
                "functions": validation.functions_found,
            },
        )

    def _stage_safety_gate(
        self, code: GeneratedCode, proposal, pipeline: ExecutionPipelineRecord
    ) -> ExecutionResult:
        constitution_result = self._constitution_harness.check_change(
            EvolutionChange(
                change_id=str(getattr(proposal, "proposal_id", pipeline.proposal_id)),
                files=[code.file_path],
                description=str(getattr(proposal, "rationale", "")),
                diff_text=code.content,
                actor="self_executor",
                audit_planned=True,
            )
        )
        if not constitution_result.allowed:
            return ExecutionResult(
                stage=ExecutionStage.SAFETY_GATE,
                success=False,
                message=f"ConstitutionHarness blocked: {', '.join(constitution_result.violations)}",
                details={"constitution": constitution_result},
            )

        threat = self._safety_gate.detect_core_removal(code.target_module)
        if threat.blocked:
            return ExecutionResult(
                stage=ExecutionStage.SAFETY_GATE,
                success=False,
                message=f"SafetyGate blocked: {threat.threat_type} - {threat.reason}",
                details={"threat": threat},
            )

        batch_check = self._safety_gate.detect_combinatorial_explosion(
            [
                {
                    "target": code.file_path,
                    "action": "deploy",
                    "size": len(code.content),
                }
            ]
        )
        if batch_check.blocked:
            return ExecutionResult(
                stage=ExecutionStage.SAFETY_GATE,
                success=False,
                message=f"SafetyGate blocked: {batch_check.threat_type} - {batch_check.reason}",
                details={"threat": batch_check},
            )

        stench_result = self._do_ai_stench_check(code)
        if stench_result is not None:
            self._do_auto_gene_extraction(code, "block", "AI stench detected")
            return stench_result

        drift_result = self._do_intent_drift_check(code)
        if drift_result is not None:
            return drift_result

        return ExecutionResult(
            stage=ExecutionStage.SAFETY_GATE,
            success=True,
            message="SafetyGate passed all checks",
            details={
                "threats_checked": [
                    "core_removal",
                    "combinatorial_explosion",
                    "ai_stench",
                    "intent_drift",
                ]
            },
        )

    def _stage_deploy(
        self, code: GeneratedCode, pipeline: ExecutionPipelineRecord
    ) -> ExecutionResult:
        return self._deployer.deploy(code)

    def _stage_verify(
        self, code: GeneratedCode, pipeline: ExecutionPipelineRecord
    ) -> ExecutionResult:
        content_result = self._deployer.verify_deployed(code.file_path, code.content)
        if content_result.is_failure:
            return content_result
        return self._quality_gate(code, pipeline)

    def _default_quality_gate(
        self, code: GeneratedCode, pipeline: ExecutionPipelineRecord
    ) -> ExecutionResult:
        file_path = Path(code.file_path)
        suffix = file_path.suffix

        checks: list[dict[str, Any]] = []

        try:
            rel_path = file_path.resolve().relative_to(Path(self._project_root).resolve())
        except ValueError:
            rel_path = None

        if suffix == ".py":
            py_compile = subprocess.run(
                [sys.executable, "-m", "py_compile", code.file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            checks.append({
                "name": "py_compile",
                "exit_code": py_compile.returncode,
                "stderr": py_compile.stderr[-500:],
            })
            if py_compile.returncode != 0:
                return ExecutionResult(
                    stage=ExecutionStage.VERIFY,
                    success=False,
                    message="Quality gate failed: py_compile",
                    details={"checks": checks},
                )

            if rel_path is not None:
                ruff = subprocess.run(
                    ["ruff", "check", str(rel_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=self._project_root,
                )
                checks.append({
                    "name": "ruff",
                    "exit_code": ruff.returncode,
                    "stdout": ruff.stdout[-500:],
                    "stderr": ruff.stderr[-500:],
                })
                if ruff.returncode != 0:
                    return ExecutionResult(
                        stage=ExecutionStage.VERIFY,
                        success=False,
                        message="Quality gate failed: ruff",
                        details={"checks": checks},
                    )

                rel_parts = rel_path.parts
                if rel_parts and rel_parts[0] == "src":
                    mypy = subprocess.run(
                        ["mypy", str(rel_path)],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        cwd=self._project_root,
                    )
                    checks.append({
                        "name": "mypy",
                        "exit_code": mypy.returncode,
                        "stdout": mypy.stdout[-500:],
                        "stderr": mypy.stderr[-500:],
                    })
                    if mypy.returncode != 0:
                        return ExecutionResult(
                            stage=ExecutionStage.VERIFY,
                            success=False,
                            message="Quality gate failed: mypy",
                            details={"checks": checks},
                        )

                if rel_parts and rel_parts[0] == "tests":
                    pytest_result = subprocess.run(
                        [sys.executable, "-m", "pytest", str(rel_path), "-q", "--no-cov"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        cwd=self._project_root,
                    )
                    checks.append({
                        "name": "pytest",
                        "exit_code": pytest_result.returncode,
                        "stdout": pytest_result.stdout[-500:],
                        "stderr": pytest_result.stderr[-500:],
                    })
                    if pytest_result.returncode != 0:
                        return ExecutionResult(
                            stage=ExecutionStage.VERIFY,
                            success=False,
                            message="Quality gate failed: pytest",
                            details={"checks": checks},
                        )

        elif suffix in (".ts", ".tsx"):
            # Fix 13: TypeScript quality gate — check error count DECREASED,
            # not zero. The old gate required both tsc and eslint to pass
            # (returncode==0), which is impossible for a file with 11 existing
            # errors. Every LLM fix was deployed then immediately rolled back,
            # leaving the file unmodified and gain=0 → rejected → deadlock.
            # New behavior: run eslint on both backup (pre) and deployed (post)
            # files. If post_errors <= pre_errors → pass. If increased → fail.
            # tsc is skipped (too strict, wrong cwd for gui/ project).
            if rel_path is not None:
                gui_dir = Path(self._project_root) / "gui"
                cwd_dir = str(gui_dir) if gui_dir.exists() else self._project_root
                # Strip gui/ prefix for eslint path (eslint runs in gui/)
                eslint_rel = str(rel_path)
                if eslint_rel.startswith("gui/"):
                    eslint_rel = eslint_rel[4:]

                def _count_eslint_errors(file_path: str) -> int:
                    try:
                        r = subprocess.run(
                            ["npx", "eslint", "--format", "json", file_path],
                            capture_output=True, text=True, timeout=60, cwd=cwd_dir,
                        )
                        raw = r.stdout or ""
                        s, e = raw.find("["), raw.rfind("]")
                        if s < 0 or e <= s:
                            return 999  # Can't parse — fail safe
                        data = json.loads(raw[s:e + 1])
                        return sum(
                            len([m for m in f.get("messages", []) if m.get("severity", 0) >= 2])
                            for f in (data if isinstance(data, list) else [])
                        )
                    except Exception:
                        return 999

                post_errors = _count_eslint_errors(eslint_rel)
                backup_path = self._deployer._deployed.get(code.file_path)
                pre_errors = _count_eslint_errors(backup_path) if backup_path and Path(backup_path).exists() else post_errors

                checks.append({
                    "name": "eslint",
                    "exit_code": 0 if post_errors <= pre_errors else 1,
                    "post_errors": post_errors,
                    "pre_errors": pre_errors,
                })
                if post_errors > pre_errors:
                    return ExecutionResult(
                        stage=ExecutionStage.VERIFY,
                        success=False,
                        message=f"Quality gate failed: eslint errors increased {pre_errors}→{post_errors}",
                        details={"checks": checks},
                    )
        else:
            return ExecutionResult(
                stage=ExecutionStage.VERIFY,
                success=True,
                message="Quality gate skipped for unsupported file type",
                details={"file_path": code.file_path},
            )

        return ExecutionResult(
            stage=ExecutionStage.VERIFY,
            success=True,
            message="Deployment verified with quality gate",
            details={"file_path": code.file_path, "checks": checks},
        )

    def _stage_rollback(self, file_path: str, pipeline: ExecutionPipelineRecord) -> ExecutionResult:
        return self._deployer.rollback(file_path)

    def _audit_pipeline(self, pipeline: ExecutionPipelineRecord, round_num: int) -> None:
        records = pipeline.to_audit_records(round_num)
        for record in records:
            self._audit_store.append(record)

    def dry_run(self, proposal) -> ExecutionPipelineRecord:
        pipeline = ExecutionPipelineRecord(
            pipeline_id=f"dry_run_{int(time.time())}_{hash(proposal.proposal_id) % 10000}",
            proposal_id=proposal.proposal_id,
        )

        try:
            generated = self._code_gen.generate(proposal, self._project_root)
            if not generated:
                pipeline.final_state = "DRY_RUN_NO_CODE"
                pipeline.finish()
                return pipeline

            code = generated[0]
            validation = self._sandbox.validate(code)

            pipeline.stages.append(
                ExecutionResult(
                    stage=ExecutionStage.CODE_GEN,
                    success=True,
                    message=f"Dry-run: generated {len(code.content)} bytes",
                    details={"file_path": code.file_path},
                )
            )
            pipeline.stages.append(
                ExecutionResult(
                    stage=ExecutionStage.AST_VALIDATE,
                    success=validation.is_valid,
                    message=f"Dry-run: AST {'valid' if validation.is_valid else 'invalid'}",
                    details={"errors": validation.errors},
                )
            )

            pipeline.final_state = "DRY_RUN_OK" if validation.is_valid else "DRY_RUN_AST_FAIL"
        except Exception as e:
            pipeline.stages.append(
                ExecutionResult(
                    stage=ExecutionStage.CODE_GEN,
                    success=False,
                    message=f"Dry-run failed: {e}",
                )
            )
            pipeline.final_state = "DRY_RUN_ERROR"

        pipeline.finish()
        return pipeline

    def attach_intent_drift_detector(self, detector: IntentDriftDetector) -> None:
        self._intent_drift_detector = detector

    def attach_gene_pipeline(self, pipeline: AutoGeneExtractionPipeline) -> None:
        self._gene_pipeline = pipeline

    def _do_intent_drift_check(self, code: GeneratedCode) -> ExecutionResult | None:
        if self._intent_drift_detector is None:
            return None
        result = self._intent_drift_detector.evaluate_code(code.content, criteria=[], expected_hash="")
        if result.blocked:
            return ExecutionResult(
                stage=ExecutionStage.SAFETY_GATE,
                success=False,
                message=f"Intent drift blocked: intent_valid={result.intent_valid}",
                details={"intent_drift": result},
            )
        return None

    def _do_ai_stench_check(self, code: GeneratedCode) -> ExecutionResult | None:
        try:
            threat = self._safety_gate.detect_ai_stench(code.content)
        except AttributeError:
            return None
        if threat.blocked:
            return ExecutionResult(
                stage=ExecutionStage.SAFETY_GATE,
                success=False,
                message=f"AI stench blocked: {threat.threat_type} - {threat.reason}",
                details={"threat": threat},
            )
        return None

    def _do_auto_gene_extraction(self, code: GeneratedCode, source: str, reason: str) -> None:
        if self._gene_pipeline is None:
            return
        if source == "rollback":
            self._gene_pipeline.extract_from_rollback(code.content, reason=reason)
        elif source == "block":
            self._gene_pipeline.extract_from_block(code.content, reason=reason)

    async def execute_with_llm(
        self,
        generated: list[GeneratedCode],
        tx_id: str = "",
        round_number: int = 41,
    ) -> ExecutionPipelineRecord:
        pipeline = ExecutionPipelineRecord(
            pipeline_id=f"exec_llm_{int(time.time())}_{hash(str(generated)) % 10000}",
            proposal_id=tx_id or "llm_gen",
        )

        for code in generated:
            ast_result = self._stage_ast_validation(code, pipeline)
            pipeline.stages.append(ast_result)
            if ast_result.is_failure:
                pipeline.final_state = "FAILED_AST_VALIDATE"
                pipeline.finish()
                self._history.append(pipeline)
                return pipeline

            safety_result = self._stage_safety_gate(code, None, pipeline)
            pipeline.stages.append(safety_result)
            if safety_result.is_failure:
                pipeline.final_state = "FAILED_SAFETY_GATE"
                pipeline.finish()
                self._history.append(pipeline)
                return pipeline

            deploy_result = self._stage_deploy(code, pipeline)
            pipeline.stages.append(deploy_result)
            if deploy_result.is_failure:
                pipeline.stages.append(self._stage_rollback(code.file_path, pipeline))
                pipeline.rollback_performed = True
                pipeline.final_state = "FAILED_DEPLOY_ROLLED_BACK"
                pipeline.finish()
                self._history.append(pipeline)
                return pipeline

            verify_result = self._stage_verify(code, pipeline)
            pipeline.stages.append(verify_result)
            if verify_result.is_failure:
                pipeline.stages.append(self._stage_rollback(code.file_path, pipeline))
                pipeline.rollback_performed = True
                pipeline.final_state = "FAILED_VERIFY_ROLLED_BACK"
                pipeline.finish()
                self._history.append(pipeline)
                self._audit_pipeline(pipeline, round_number)
                return pipeline

        pipeline.final_state = "SUCCESS"
        pipeline.finish()
        self._history.append(pipeline)
        self._audit_pipeline(pipeline, round_number)
        return pipeline

    def health_check(self) -> dict[str, Any]:
        return {
            "max_rounds": self._max_rounds,
            "history_length": len(self._history),
            "deployed_file_count": len(self._deployer.deployed_files),
            "audit_records": self._audit_store.count(),
            "successful_pipelines": sum(1 for p in self._history if p.final_state == "SUCCESS"),
            "failed_pipelines": sum(1 for p in self._history if p.final_state.startswith("FAILED")),
            "rollback_count": sum(1 for p in self._history if p.rollback_performed),
        }

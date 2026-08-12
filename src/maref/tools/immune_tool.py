import ast
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from maref.codegen.tool import Tool, ToolContext, ToolResult, ValidationResult

_IMMUNE_PATTERNS: list[tuple[str, str, int, str]] = [
    (
        "hardcoded_secret",
        "Hardcoded password or API key",
        5,
        "(?x)\n        (password|secret|api_key|token|credential)\\s*=\\s*['\\\"][^'\\\"]{4,}['\\\"]\n    ",
    ),
    (
        "insecure_hash",
        "Insecure hash algorithm (MD5/SHA1)",
        4,
        "\\b(hashlib\\.md5|hashlib\\.sha1|import\\s+md5)\\b",
    ),
    ("eval_exec", "Use of eval/exec on untrusted input", 5, "\\b(eval|exec)\\s*\\("),
    (
        "sql_injection",
        "Possible SQL injection (string formatting in query)",
        5,
        "(?x)\n        (execute|executemany)\\s*\\(\\s*['\\\"](?:.|\\n)*?\\{.*?\\}\n    ",
    ),
    (
        "pickle_load",
        "Unsafe pickle deserialization",
        4,
        "\\b(pickle\\.load|pickle\\.loads|cPickle\\.load|cPickle\\.loads)\\s*\\(",
    ),
    ("assert", "assert statement used in production path", 3, "^\\s*assert\\s+"),
    ("print_to_stdout", "print statement in production code", 2, "^\\s*print\\s*\\("),
    ("bare_except", "Bare except clause", 3, "^\\s*except\\s*:"),
    (
        "shell_injection",
        "os.system/subprocess with shell=True",
        4,
        "(?x)\n        (os\\.system|subprocess\\.call|subprocess\\.Popen|subprocess\\.run)\\s*\\(\n        (?:.|\\n)*?shell\\s*=\\s*True\n    ",
    ),
    (
        "mutable_default_arg",
        "Mutable default argument",
        2,
        "(?x)\n        def\\s+\\w+\\s*\\([^)]*=\\s*(\\[\\s*\\]|\\{\\s*\\}|set\\(\\s*\\))\n    ",
    ),
]


class ImmuneScanInput(BaseModel):
    code: str = Field(..., description="Code to scan")
    file_path: str | None = Field(None, description="Optional file path for file-based scan")
    language: str = Field("python", description="Programming language")


class ImmuneHit(BaseModel):
    gene_id: str = ""
    gene_title: str = ""
    risk_level: str = "info"
    severity: int = 0
    blocked: bool = False
    match_type: str = ""
    match_location: tuple[int, int] = (0, 0)
    match_snippet: str = ""
    fix_suggestion: str | None = None


class ImmuneScanOutput(BaseModel):
    hits: list[ImmuneHit] = Field(default_factory=list)
    blocked: bool = False
    scan_count: int = 0


class ImmuneScanTool(Tool[ImmuneScanInput, ImmuneScanOutput]):
    name = "ImmuneScan"
    description: str = "Scan code with immune system for known vulnerability patterns"

    def __init__(self, immune_checker: Any | None = None) -> None:
        self._immune_checker = immune_checker

    def is_read_only(self, input: ImmuneScanInput) -> bool:
        return True

    def is_concurrency_safe(self, input: ImmuneScanInput) -> bool:
        return True

    async def validate(self, input: ImmuneScanInput) -> ValidationResult:
        if not input.code.strip() and (not input.file_path):
            return ValidationResult(
                is_valid=False, message="Either code or file_path must be provided"
            )
        return ValidationResult(is_valid=True)

    async def call(self, input: ImmuneScanInput, ctx: ToolContext) -> ToolResult[ImmuneScanOutput]:
        code = input.code
        if input.file_path and (not code):
            try:
                code = Path(input.file_path).read_text(encoding="utf-8")
            except Exception as e:
                return ToolResult(
                    data=ImmuneScanOutput(hits=[], blocked=False, scan_count=0),
                    metadata={"error": f"Failed to read file: {e}"},
                )
        if self._immune_checker is not None:
            try:
                if input.file_path:
                    hits_raw = self._immune_checker.scan_file(input.file_path, input.language)
                else:
                    hits_raw = self._immune_checker.scan(code, input.language)
                hits = [
                    ImmuneHit(
                        gene_id=getattr(h, "gene_id", ""),
                        gene_title=getattr(h, "gene_title", ""),
                        risk_level=getattr(h, "risk_level", "info"),
                        severity=getattr(h, "severity", 0),
                        blocked=getattr(h, "blocked", False),
                        match_type=getattr(h, "match_type", ""),
                        match_location=getattr(h, "match_location", (0, 0)),
                        match_snippet=getattr(h, "match_snippet", ""),
                        fix_suggestion=getattr(h, "fix_suggestion", None),
                    )
                    for h in hits_raw
                ]
                blocked = any(h.blocked for h in hits)
                return ToolResult(
                    data=ImmuneScanOutput(hits=hits, blocked=blocked, scan_count=len(hits))
                )
            except Exception as e:
                return ToolResult(
                    data=ImmuneScanOutput(hits=[], blocked=False, scan_count=0),
                    metadata={
                        "fallback": "Checker failed, using built-in patterns",
                        "error": str(e),
                    },
                )
        return await self._scan_with_builtin_patterns(code)

    async def _scan_with_builtin_patterns(self, code: str) -> ToolResult[ImmuneScanOutput]:
        hits: list[ImmuneHit] = []
        lines = code.split("\n")
        for gene_id, title, severity, pattern in _IMMUNE_PATTERNS:
            for match in re.finditer(pattern, code, re.MULTILINE):
                start_pos = match.start()
                line_no = code[:start_pos].count("\n") + 1
                col = start_pos - code.rfind("\n", 0, start_pos) - 1
                snippet = match.group()[:120]
                context_line = lines[line_no - 1].strip() if line_no <= len(lines) else snippet
                risk = (
                    "critical"
                    if severity >= 5
                    else "high"
                    if severity >= 4
                    else "medium"
                    if severity >= 3
                    else "low"
                )
                hits.append(
                    ImmuneHit(
                        gene_id=gene_id,
                        gene_title=title,
                        risk_level=risk,
                        severity=severity,
                        blocked=severity >= 5,
                        match_type="regex",
                        match_location=(line_no, col),
                        match_snippet=context_line,
                        fix_suggestion=self._get_fix_suggestion(gene_id),
                    )
                )
        ast_hits = self._scan_ast(code)
        hits.extend(ast_hits)
        hits.sort(key=lambda h: (-h.severity, h.match_location[0]))
        blocked = any(h.blocked for h in hits)
        return ToolResult(data=ImmuneScanOutput(hits=hits, blocked=blocked, scan_count=len(hits)))

    def _scan_ast(self, code: str) -> list[ImmuneHit]:
        hits: list[ImmuneHit] = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "system"
                        and isinstance(func.value, ast.Name)
                        and (func.value.id == "os")
                    ):
                        hits.append(
                            ImmuneHit(
                                gene_id="os_system",
                                gene_title="os.system call",
                                risk_level="high",
                                severity=4,
                                blocked=False,
                                match_type="ast",
                                match_location=(node.lineno, node.col_offset),
                                match_snippet=f"os.system() at line {node.lineno}",
                                fix_suggestion="Use subprocess.run() instead",
                            )
                        )
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "setdefaultencoding"
                        and isinstance(func.value, ast.Name)
                        and (func.value.id == "sys")
                    ):
                        hits.append(
                            ImmuneHit(
                                gene_id="setdefaultencoding",
                                gene_title="sys.setdefaultencoding() called",
                                risk_level="high",
                                severity=4,
                                blocked=True,
                                match_type="ast",
                                match_location=(node.lineno, node.col_offset),
                                match_snippet="sys.setdefaultencoding() at line {node.lineno}",
                                fix_suggestion="Remove this call - Python 3 uses UTF-8 by default",
                            )
                        )
        except SyntaxError:
            pass
        return hits

    def _get_fix_suggestion(self, gene_id: str) -> str | None:
        suggestions = {
            "hardcoded_secret": "Use environment variables or Keychain for secrets",
            "insecure_hash": "Use hashlib.sha256 or stronger",
            "eval_exec": "Use ast.literal_eval() or a safer alternative",
            "sql_injection": "Use parameterized queries with ? placeholders",
            "pickle_load": "Use json or a safer serialization format",
            "assert": "Replace assert with proper if/raise for defensive checks",
            "print_to_stdout": "Use logging module instead of print()",
            "bare_except": "Always specify exception type(s) to catch",
            "shell_injection": "Avoid shell=True; pass arguments as a list",
            "mutable_default_arg": "Use None default with None-guard inside function",
            "os_system": "Use subprocess.run() instead",
        }
        return suggestions.get(gene_id)

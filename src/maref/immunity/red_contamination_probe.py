from __future__ import annotations

import ast
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from maref.recursive.unified_audit import NullAuditStore
from maref.security.decorators import security_critical

if TYPE_CHECKING:
    from maref.recursive.unified_audit import UnifiedAuditStore


@dataclass
class ContaminationFinding:
    type: str
    severity: str
    line: int
    message: str
    suggestion: str
    code_snippet: str = ""


_PROFESSIONAL_KW = {"production", "enterprise", "secure", "safe", "robust", "battle-tested"}
_DANGEROUS_KW_IN_BODY = {"pickle", "eval(", "exec(", "md5", "sha1", "unsafe"}

_WRONG_COMMENT_MAP: list[tuple[str, list[str]]] = [
    ("eval", ["use eval", "using eval is safe", "eval is secure"]),
    ("pickle", ["safe to unpickle", "secure pickle", "pickle is safe"]),
    ("md5", ["md5 is secure", "md5 encryption", "secure md5"]),
    ("sha1", ["sha1 is secure", "SHA1 secure", "sha1 encryption"]),
    ("exec(", ["use exec", "using exec", "exec is safe"]),
]

_DANGEROUS_TRIGGERS = ["eval(", "exec(", "pickle", "md5(", "sha1("]


class RedContaminationProbe:
    def __init__(self, audit_store: UnifiedAuditStore | None = None) -> None:
        self._audit_store = audit_store or NullAuditStore()
        self._findings: list[ContaminationFinding] = []

    @security_critical
    def scan(self, code: str) -> list[ContaminationFinding]:
        self._findings = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return self._findings

        self._findings.extend(self._detect_pickle_usage(tree, code))
        self._findings.extend(self._detect_wrong_comments(tree, code))
        self._findings.extend(self._detect_missing_timeout(tree, code))

        self._write_to_audit()

        return list(self._findings)

    def _detect_pickle_usage(self, tree: ast.AST, code: str) -> list[ContaminationFinding]:
        findings: list[ContaminationFinding] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [n.name for n in node.names]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                if "pickle" in " ".join(names):
                    findings.append(
                        ContaminationFinding(
                            type="deprecated_pickle",
                            severity="POLLUTION",
                            line=node.lineno or 0,
                            message="pickle import detected — insecure deserialization can execute arbitrary code",
                            suggestion="Replace pickle with JSON (json.loads/json.dumps) or MessagePack",
                            code_snippet=ast.unparse(node)[:100],
                        )
                    )
            if isinstance(node, ast.Call):
                name = ast.unparse(node.func)
                if "pickle." in name:
                    findings.append(
                        ContaminationFinding(
                            type="deprecated_pickle",
                            severity="POLLUTION",
                            line=node.lineno or 0,
                            message=f"pickle operation '{name}' — insecure deserialization risk",
                            suggestion="Replace pickle with JSON or another safe serialization format",
                            code_snippet=ast.unparse(node)[:100],
                        )
                    )
        return findings

    def _detect_wrong_comments(self, tree: ast.AST, code: str) -> list[ContaminationFinding]:
        findings: list[ContaminationFinding] = []
        code_lines = code.splitlines()
        code_lower = code.lower()

        for trigger, bad_phrases in _WRONG_COMMENT_MAP:
            for phrase in bad_phrases:
                if phrase not in code_lower:
                    continue
                for i, line in enumerate(code_lines, 1):
                    if phrase in line.lower():
                        nearby = code_lines[max(0, i - 3) : min(len(code_lines), i + 2)]
                        has_authoritative = any(
                            any(kw in l.lower() for kw in _PROFESSIONAL_KW)
                            for l in nearby
                            if l.strip().startswith(("#", '"""', "'''"))
                        )
                        if has_authoritative:
                            findings.append(
                                ContaminationFinding(
                                    type="wrong_comment",
                                    severity="POLLUTION",
                                    line=i,
                                    message=f"Dangerous '{trigger}' with authoritative comment — teaches bad practices",
                                    suggestion=f"Remove {trigger} usage and replace with a safe alternative",
                                    code_snippet=line.strip()[:100],
                                )
                            )
                            break

        for i, line in enumerate(code_lines, 1):
            line_lower = line.lower()
            if not line_lower.strip().startswith("#"):
                continue
            has_authoritative = any(kw in line_lower for kw in _PROFESSIONAL_KW)
            if not has_authoritative:
                continue
            nearby = code_lines[max(0, i - 3) : min(len(code_lines), i + 2)]
            has_danger = any(any(t in l.lower() for t in _DANGEROUS_TRIGGERS) for l in nearby)
            if has_danger:
                findings.append(
                    ContaminationFinding(
                        type="wrong_comment",
                        severity="POLLUTION",
                        line=i,
                        message=f"Authoritative comment near dangerous pattern — '{line.strip()[:80]}'",
                        suggestion="Remove authoritative-sounding justification for dangerous code patterns",
                        code_snippet=line.strip()[:100],
                    )
                )

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstring = ast.get_docstring(node) or ""
            if not docstring:
                continue
            doc_lower = docstring.lower()
            body_code = ast.unparse(node)
            body_lower = body_code.lower()

            sounds_professional = any(kw in doc_lower for kw in _PROFESSIONAL_KW)
            has_danger = any(kw in body_lower for kw in _DANGEROUS_KW_IN_BODY)
            if sounds_professional and has_danger:
                findings.append(
                    ContaminationFinding(
                        type="wrong_comment",
                        severity="POLLUTION",
                        line=node.lineno or 0,
                        message=f"Professional docstring with dangerous body — '{docstring[:80]}'",
                        suggestion="Fix code to use safe alternatives or honestly describe limitations",
                        code_snippet=docstring[:120],
                    )
                )

        return findings

    def _detect_missing_timeout(self, tree: ast.AST, code: str) -> list[ContaminationFinding]:
        findings: list[ContaminationFinding] = []
        _HTTP_METHODS = (".get", ".post", ".put", ".delete", ".patch", ".request")

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = ast.unparse(node.func)
            if "requests." not in func_name:
                continue
            if not any(m in func_name for m in _HTTP_METHODS):
                continue

            has_timeout = any(kw.arg == "timeout" for kw in node.keywords if kw.arg is not None)

            if not has_timeout:
                findings.append(
                    ContaminationFinding(
                        type="missing_dangerous_pattern",
                        severity="POLLUTION",
                        line=node.lineno or 0,
                        message=f"'{func_name}' without timeout — teaches AI that omitting timeout is acceptable",
                        suggestion="Always add explicit timeout: requests.get(url, timeout=30)",
                        code_snippet=ast.unparse(node)[:120],
                    )
                )

        return findings

    def _write_to_audit(self) -> None:
        from maref.recursive.unified_audit import UnifiedAuditRecord

        ts = time.time()
        for i, f in enumerate(self._findings):
            record = UnifiedAuditRecord(
                record_id=f"contam_{i:06d}_{int(ts * 1000)}",
                timestamp=ts,
                layer="execution",
                round=0,
                event_type=f"contamination_{f.type}",
                source_module="red_contamination_probe",
                target_module="code_analysis",
                decision=f.severity,
                justification=f.message,
                outcome=None,
                context_refs=[],
            )
            self._audit_store.append(record)

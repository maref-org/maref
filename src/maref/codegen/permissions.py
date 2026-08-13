from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from maref.codegen.tool import Tool, ToolContext
from maref.evolution.constitution_harness import ConstitutionHarness, EvolutionChange
from maref.recursive.safety_gate_v2 import SafetyGateV2


class PermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "accept_edits"
    BYPASS = "bypass"
    DENY_ALL = "deny_all"
    GOVERNED = "governed"
    PLAN = "plan"


@dataclass
class PermissionRule:
    pattern: str
    behavior: Literal["allow", "deny", "ask"]
    source: Literal["settings", "session", "policy", "constitution"] = "settings"
    bypass_immune: bool = False
    priority: int = 0


class BashValidator:
    SHELL_METACHARACTERS = re.compile(r"[;&|`]")
    COMMAND_SUBSTITUTION = re.compile(r"\$\([^)]*\)|`[^`]*`")
    PROCESS_SUBSTITUTION = re.compile(r"<\([^)]*\)|>\([^)]*\)")
    HEREDOC_IN_SUBST = re.compile(r"<<\s*\w+.*\$\(", re.DOTALL)
    IFS_PATTERN = re.compile(r"\bIFS\s*=", re.IGNORECASE)
    PROC_ENVIRON_PATTERN = re.compile(r"/proc/\d+/environ")
    SLEEP_PATTERN = re.compile(r"\bsleep\s+(\d+)")

    BLOCKED_COMMANDS: set[str] = {"sudo", "su", "doas", "pkexec"}
    BLOCKED_PATHS: set[str] = {"/etc", "/proc", "/sys", "/dev"}

    def validate(self, command: str) -> tuple[bool, str, list[str]]:
        warnings: list[str] = []

        if self.SHELL_METACHARACTERS.search(command):
            warnings.append("Shell metacharacters detected")

        if self.COMMAND_SUBSTITUTION.search(command):
            warnings.append("Command substitution detected")

        if self.PROCESS_SUBSTITUTION.search(command):
            warnings.append("Process substitution detected")

        if self.HEREDOC_IN_SUBST.search(command):
            warnings.append("Heredoc with command substitution detected")

        if self.IFS_PATTERN.search(command):
            warnings.append("IFS injection detected")

        if self.PROC_ENVIRON_PATTERN.search(command):
            return False, "Access to process environment is blocked", warnings

        tokens = command.split()
        if tokens and tokens[0] in self.BLOCKED_COMMANDS:
            return False, f"Command '{tokens[0]}' is blocked", warnings

        sleep_match = self.SLEEP_PATTERN.search(command)
        if sleep_match and int(sleep_match.group(1)) >= 2:
            warnings.append(
                f"sleep {sleep_match.group(1)}s detected; consider background execution"
            )

        if not tokens:
            return False, "Empty command", warnings

        return True, "", warnings


class PathSafety:
    UNC_PATTERN = re.compile(r"^\\\\")
    WINDOWS_ADS_PATTERN = re.compile(r":.*\$")
    TRAVERSAL_PATTERN = re.compile(r"(?:^|[/\\])\.\.(?:$|[/\\])")

    BLOCKED_EXTENSIONS: set[str] = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin"}
    MAX_FILE_SIZE = 1 * 1024 * 1024 * 1024

    BLOCKED_IMMUNE_PATHS: set[str] = {
        ".git/",
        ".claude/",
        ".opencode/",
        ".bashrc",
        ".zshrc",
        ".profile",
        "AGENTS.md",
        "CLAUDE.md",
        "opencode.json",
    }

    def check(self, path: str) -> tuple[bool, str]:
        if self.UNC_PATTERN.match(path):
            return False, "UNC paths are blocked"

        if self.WINDOWS_ADS_PATTERN.search(path):
            return False, "Windows alternate data streams are blocked"

        if self.TRAVERSAL_PATTERN.search(path):
            return False, "Path traversal detected"

        p = Path(path)
        if p.suffix in self.BLOCKED_EXTENSIONS:
            return False, f"File extension '{p.suffix}' is blocked"

        try:
            if p.exists() and p.stat().st_size > self.MAX_FILE_SIZE:
                return False, "File exceeds maximum allowed size"
        except OSError:
            pass

        return True, ""

    def check_immune(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return any(blocked in normalized for blocked in self.BLOCKED_IMMUNE_PATHS)


@dataclass
class PermissionResult:
    granted: bool = True
    mode: str = "allow"
    reason: str = ""
    ask_user: bool = False
    details: dict[str, Any] = field(default_factory=dict)


class PermissionEngine:
    def __init__(
        self,
        constitution_harness: ConstitutionHarness | None = None,
        safety_gate: SafetyGateV2 | None = None,
    ) -> None:
        self._rules: list[PermissionRule] = []
        self._mode: PermissionMode = PermissionMode.GOVERNED
        self._bash_validator = BashValidator()
        self._path_safety = PathSafety()
        self._constitution = constitution_harness or ConstitutionHarness()
        self._safety_gate = safety_gate or SafetyGateV2()

    @property
    def mode(self) -> PermissionMode:
        return self._mode

    def set_mode(self, mode: PermissionMode) -> None:
        self._mode = mode

    def add_rule(self, rule: PermissionRule) -> None:
        self._rules.append(rule)

    def add_rules(self, *rules: PermissionRule) -> None:
        self._rules.extend(rules)

    def clear_rules(self) -> None:
        self._rules.clear()

    def evaluate(
        self,
        tool: Tool[Any, Any],
        inp: Any,
        ctx: ToolContext,
    ) -> PermissionResult:
        if self._mode == PermissionMode.DENY_ALL:
            return PermissionResult(granted=False, mode="deny_all", reason="deny_all mode active")

        if self._mode == PermissionMode.PLAN:
            if not tool.is_read_only(inp):
                return PermissionResult(
                    granted=False, mode="plan", reason="plan mode: write operations disabled"
                )
            return PermissionResult(granted=True, mode="plan")

        path = self._get_path(inp)
        input_str = str(inp)

        sorted_rules = sorted(self._rules, key=lambda r: -r.priority)
        for rule in sorted_rules:
            if self._match_pattern(rule.pattern, tool.name.lower(), input_str):
                if rule.behavior == "deny":
                    return PermissionResult(
                        granted=False,
                        mode="deny",
                        reason=f"Rule denies {tool.name} matching '{rule.pattern}'",
                        details={"rule": rule.pattern, "source": rule.source},
                    )
                if rule.behavior == "allow":
                    return PermissionResult(
                        granted=True,
                        mode="allow",
                        reason=f"Rule allows {tool.name} matching '{rule.pattern}'",
                    )
                if rule.behavior == "ask":
                    return PermissionResult(
                        granted=True,
                        mode="ask",
                        ask_user=True,
                        reason=f"Rule requires confirmation for {tool.name}",
                    )

        if path:
            safe, msg = self._path_safety.check(path)
            if not safe:
                return PermissionResult(
                    granted=False,
                    mode="path_safety",
                    reason=f"Path safety check failed: {msg}",
                    details={"path": path},
                )

            if not self._path_safety.check_immune(path):
                pass
            else:
                try:
                    threat = self._safety_gate.detect_core_removal(path)
                    if threat.blocked:
                        return PermissionResult(
                            granted=False,
                            mode="safety_gate",
                            reason=f"Safety gate blocked: {threat.reason}",
                            details={"threat_type": threat.threat_type},
                        )
                except (AttributeError, Exception):
                    pass

        if self._mode == PermissionMode.BYPASS:
            return PermissionResult(granted=True, mode="bypass")

        if self._mode == PermissionMode.ACCEPT_EDITS:
            if tool.name.lower() in {"read", "glob", "grep", "bash", "test", "lint"}:
                return PermissionResult(granted=True, mode="accept_edits")
            if tool.name.lower() in {"edit", "write"}:
                workspace = ctx.workspace_root
                if path and workspace and str(path).startswith(str(workspace)):
                    return PermissionResult(granted=True, mode="accept_edits")
            return PermissionResult(
                granted=False,
                mode="accept_edits",
                reason=f"Tool '{tool.name}' not in accept_edits scope",
            )

        if self._mode == PermissionMode.GOVERNED:
            return PermissionResult(
                granted=True,
                mode="governed",
                details={"note": "governed mode: will be checked by governance FSM"},
            )

        return PermissionResult(granted=True, mode="default")

    def check_constitution(
        self,
        tool: Tool[Any, Any],
        inp: Any,
        ctx: ToolContext,
    ) -> PermissionResult:
        path = self._get_path(inp)
        change = EvolutionChange(
            change_id=f"perm_{tool.name}_{int(__import__('time').time())}",
            files=[path] if path else [],
            description=f"Permission check for {tool.name}",
            actor="permission_engine",
            audit_planned=True,
        )
        result = self._constitution.check_change(change)
        if not result.allowed:
            return PermissionResult(
                granted=False,
                mode="constitution",
                reason=f"Constitution blocked: {', '.join(result.violations)}",
                details={"violations": result.violations},
            )
        return PermissionResult(granted=True, mode="constitution")

    def _match_pattern(self, pattern: str, tool_name: str, input_str: str) -> bool:
        if "(" in pattern and ")" in pattern:
            name_part = pattern.split("(")[0].strip().lower()
            constraint = pattern[pattern.find("(") + 1 : pattern.find(")")]
            if name_part == tool_name or name_part == "*":
                return constraint.lower() in input_str.lower()
            return False
        if pattern == tool_name or pattern == "*":
            return True
        return pattern.lower() in input_str.lower()

    def _get_path(self, inp: Any) -> str | None:
        if hasattr(inp, "file_path"):
            return inp.file_path
        if hasattr(inp, "path"):
            return inp.path
        if isinstance(inp, dict):
            return inp.get("file_path") or inp.get("path")
        return None

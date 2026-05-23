from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ToolRiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolCategory(Enum):
    FILE = "file"
    SHELL = "shell"
    GIT = "git"
    BROWSER = "browser"
    EMAIL = "email"
    NETWORK = "network"
    AI = "ai"
    DATABASE = "database"
    CUSTOM = "custom"


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str = ""
    required: bool = False
    default: Any = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: ToolCategory = ToolCategory.CUSTOM
    risk_level: ToolRiskLevel = ToolRiskLevel.MEDIUM
    version: str = "0.1.0"
    tools: list[str] = field(default_factory=list)
    tool_parameters: dict[str, list[ToolParameter]] = field(default_factory=dict)
    security_controls: list[str] = field(default_factory=list)
    default_config: dict[str, Any] = field(default_factory=dict)
    requires_hitl: bool = False
    timeout_seconds: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_read_only(self) -> bool:
        read_only_keywords = {"read", "list", "get", "search", "status", "log", "diff"}
        return all(
            any(t.startswith(kw) for kw in read_only_keywords)
            for t in self.tools
        ) if self.tools else False

    def to_dict(self) -> dict[str, Any]:
        def _convert(obj: Any) -> Any:
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, list):
                return [_convert(v) for v in obj]
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            return obj
        return _convert(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolDefinition:
        data = dict(data)
        if "category" in data and isinstance(data["category"], str):
            data["category"] = ToolCategory(data["category"])
        if "risk_level" in data and isinstance(data["risk_level"], str):
            data["risk_level"] = ToolRiskLevel(data["risk_level"])
        if "tool_parameters" in data:
            params = {}
            for tool_name, param_list in data["tool_parameters"].items():
                params[tool_name] = [
                    ToolParameter(**p) if isinstance(p, dict) else p
                    for p in param_list
                ]
            data["tool_parameters"] = params
        return cls(**data)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> ToolDefinition:
        return cls.from_dict(json.loads(raw))

    def get_recommended_rule(self) -> str:
        if self.risk_level in (ToolRiskLevel.CRITICAL, ToolRiskLevel.HIGH):
            return "mcp-rule-003"
        if self.requires_hitl or not self.is_read_only():
            return "mcp-rule-005"
        return "mcp-rule-002"


def create_file_tool() -> ToolDefinition:
    return ToolDefinition(
        name="file",
        description="File system operations with path sandbox",
        category=ToolCategory.FILE,
        risk_level=ToolRiskLevel.HIGH,
        version="0.27.0",
        tools=["read_file", "write_file", "list_directory", "delete_file", "copy_file", "move_file", "get_file_info"],
        tool_parameters={
            "read_file": [ToolParameter(name="path", type="string", description="File path", required=True)],
            "write_file": [ToolParameter(name="path", type="string", description="File path", required=True), ToolParameter(name="content", type="string", description="File content", required=True)],
        },
        security_controls=["PathSandbox", "FileSizeLimit"],
        default_config={"max_read_size": 10485760},
        requires_hitl=False,
        timeout_seconds=30.0,
    )


def create_shell_tool() -> ToolDefinition:
    return ToolDefinition(
        name="shell",
        description="Shell command execution with command whitelist and timeout",
        category=ToolCategory.SHELL,
        risk_level=ToolRiskLevel.CRITICAL,
        version="0.27.0",
        tools=["run_command", "get_shell_help"],
        tool_parameters={
            "run_command": [ToolParameter(name="command", type="string", description="Command to execute", required=True)],
        },
        security_controls=["CommandWhitelist", "Timeout", "OutputLimit", "MetacharacterBlock"],
        default_config={},
        requires_hitl=True,
        timeout_seconds=60.0,
    )


def create_git_tool() -> ToolDefinition:
    return ToolDefinition(
        name="git",
        description="Git repository operations with repo whitelist and write mode gate",
        category=ToolCategory.GIT,
        risk_level=ToolRiskLevel.MEDIUM,
        version="0.27.0",
        tools=["git_status", "git_log", "git_diff", "git_branch", "git_commit", "git_push"],
        security_controls=["RepoWhitelist", "WriteModeGate"],
        default_config={"repo_whitelist": [], "write_mode": False},
    )


def create_browser_tool() -> ToolDefinition:
    return ToolDefinition(
        name="browser",
        description="Web page fetching and link extraction with domain whitelist",
        category=ToolCategory.BROWSER,
        risk_level=ToolRiskLevel.LOW,
        version="0.27.0",
        tools=["browser_open", "browser_screenshot", "browser_get_html", "browser_get_links"],
        security_controls=["DomainWhitelist", "URLValidation", "ContentSizeLimit"],
        default_config={"domain_whitelist": None, "max_content_size": 5242880},
    )


def create_email_tool() -> ToolDefinition:
    return ToolDefinition(
        name="email",
        description="Email sending and listing with recipient whitelist and sensitive word filter",
        category=ToolCategory.EMAIL,
        risk_level=ToolRiskLevel.MEDIUM,
        version="0.27.0",
        tools=["email_send", "email_list", "email_read", "email_search"],
        security_controls=["RecipientWhitelist", "SensitiveWordFilter", "WriteModeGate"],
        default_config={"write_mode": False},
    )


BUILTIN_TOOL_DEFINITIONS: dict[str, ToolDefinition] = {
    "file": create_file_tool(),
    "shell": create_shell_tool(),
    "git": create_git_tool(),
    "browser": create_browser_tool(),
    "email": create_email_tool(),
}


def get_tool_definition(name: str) -> ToolDefinition | None:
    return BUILTIN_TOOL_DEFINITIONS.get(name)


def list_tool_definitions() -> list[ToolDefinition]:
    return list(BUILTIN_TOOL_DEFINITIONS.values())

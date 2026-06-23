from __future__ import annotations

import json

from maref.tools.tool_schema import (
    BUILTIN_TOOL_DEFINITIONS,
    ToolCategory,
    ToolDefinition,
    ToolParameter,
    ToolRiskLevel,
    create_browser_tool,
    create_email_tool,
    create_file_tool,
    create_git_tool,
    create_github_tool,
    create_jira_tool,
    create_notion_tool,
    create_shell_tool,
    create_slack_tool,
    create_web_search_tool,
    get_tool_definition,
    list_tool_definitions,
)


class TestEnums:
    def test_tool_risk_level_values(self) -> None:
        assert ToolRiskLevel.LOW.value == "low"
        assert ToolRiskLevel.MEDIUM.value == "medium"
        assert ToolRiskLevel.HIGH.value == "high"
        assert ToolRiskLevel.CRITICAL.value == "critical"

    def test_tool_category_values(self) -> None:
        assert ToolCategory.FILE.value == "file"
        assert ToolCategory.SHELL.value == "shell"
        assert ToolCategory.GIT.value == "git"
        assert ToolCategory.BROWSER.value == "browser"
        assert ToolCategory.EMAIL.value == "email"
        assert ToolCategory.SEARCH.value == "search"
        assert ToolCategory.NETWORK.value == "network"
        assert ToolCategory.AI.value == "ai"
        assert ToolCategory.DATABASE.value == "database"
        assert ToolCategory.CUSTOM.value == "custom"


class TestToolParameter:
    def test_default_values(self) -> None:
        p = ToolParameter(name="test", type="string")
        assert p.name == "test"
        assert p.type == "string"
        assert p.description == ""
        assert p.required is False
        assert p.default is None

    def test_all_fields(self) -> None:
        p = ToolParameter(
            name="path",
            type="string",
            description="File path",
            required=True,
            default="/tmp",
        )
        assert p.name == "path"
        assert p.description == "File path"
        assert p.required is True
        assert p.default == "/tmp"


class TestToolDefinition:
    def test_default_values(self) -> None:
        t = ToolDefinition(name="test", description="Test tool")
        assert t.category == ToolCategory.CUSTOM
        assert t.risk_level == ToolRiskLevel.MEDIUM
        assert t.version == "0.1.0"
        assert t.tools == []
        assert t.tool_parameters == {}
        assert t.security_controls == []
        assert t.default_config == {}
        assert t.requires_hitl is False
        assert t.timeout_seconds == 30.0

    def test_is_read_only_all_read(self) -> None:
        t = ToolDefinition(
            name="reader",
            description="Read only",
            tools=["read_file", "list_directory", "get_file_info"],
        )
        assert t.is_read_only() is True

    def test_is_read_only_with_write(self) -> None:
        t = ToolDefinition(
            name="writer",
            description="Write tool",
            tools=["read_file", "write_file"],
        )
        assert t.is_read_only() is False

    def test_is_read_only_empty(self) -> None:
        t = ToolDefinition(name="empty", description="Empty")
        assert t.is_read_only() is False

    def test_to_dict(self) -> None:
        t = ToolDefinition(
            name="test",
            description="Test",
            category=ToolCategory.FILE,
            risk_level=ToolRiskLevel.HIGH,
        )
        d = t.to_dict()
        assert d["name"] == "test"
        assert d["category"] == "file"
        assert d["risk_level"] == "high"

    def test_to_dict_with_enum_parameters(self) -> None:
        t = ToolDefinition(
            name="test",
            description="Test",
            tool_parameters={
                "read": [ToolParameter(name="path", type="string", required=True)]
            },
        )
        d = t.to_dict()
        assert d["tool_parameters"]["read"][0]["name"] == "path"
        assert d["tool_parameters"]["read"][0]["required"] is True

    def test_from_dict_roundtrip(self) -> None:
        t = ToolDefinition(
            name="file",
            description="File ops",
            category=ToolCategory.FILE,
            risk_level=ToolRiskLevel.HIGH,
            tools=["read_file", "write_file"],
            tool_parameters={
                "read_file": [
                    ToolParameter(name="path", type="string", required=True)
                ]
            },
        )
        d = t.to_dict()
        t2 = ToolDefinition.from_dict(d)
        assert t2.name == t.name
        assert t2.category == t.category
        assert t2.risk_level == t.risk_level
        assert t2.tools == t.tools
        assert t2.tool_parameters["read_file"][0].name == "path"

    def test_from_dict_string_enums(self) -> None:
        data = {
            "name": "test",
            "description": "Test",
            "category": "file",
            "risk_level": "high",
            "tools": [],
        }
        t = ToolDefinition.from_dict(data)
        assert t.category == ToolCategory.FILE
        assert t.risk_level == ToolRiskLevel.HIGH

    def test_to_json_and_from_json(self) -> None:
        t = create_file_tool()
        raw = t.to_json()
        parsed = json.loads(raw)
        assert parsed["name"] == "file"
        t2 = ToolDefinition.from_json(raw)
        assert t2.name == t.name
        assert t2.description == t.description

    def test_get_recommended_rule_critical(self) -> None:
        t = ToolDefinition(
            name="critical",
            description="Critical",
            risk_level=ToolRiskLevel.CRITICAL,
        )
        assert t.get_recommended_rule() == "mcp-rule-003"

    def test_get_recommended_rule_high(self) -> None:
        t = ToolDefinition(
            name="high",
            description="High",
            risk_level=ToolRiskLevel.HIGH,
        )
        assert t.get_recommended_rule() == "mcp-rule-003"

    def test_get_recommended_rule_write(self) -> None:
        t = ToolDefinition(
            name="write",
            description="Write",
            risk_level=ToolRiskLevel.MEDIUM,
            tools=["write_file"],
        )
        assert t.get_recommended_rule() == "mcp-rule-005"

    def test_get_recommended_rule_read_only(self) -> None:
        t = ToolDefinition(
            name="read",
            description="Read",
            risk_level=ToolRiskLevel.LOW,
            tools=["read_file", "list_directory"],
            requires_hitl=False,
        )
        assert t.get_recommended_rule() == "mcp-rule-002"

    def test_get_recommended_rule_hitl(self) -> None:
        t = ToolDefinition(
            name="hitl",
            description="HITL",
            risk_level=ToolRiskLevel.LOW,
            requires_hitl=True,
            tools=["read_file"],
        )
        assert t.get_recommended_rule() == "mcp-rule-005"


class TestFactoryFunctions:
    def test_create_file_tool(self) -> None:
        t = create_file_tool()
        assert t.name == "file"
        assert t.category == ToolCategory.FILE
        assert t.risk_level == ToolRiskLevel.HIGH
        assert "read_file" in t.tools
        assert "write_file" in t.tools
        assert "PathSandbox" in t.security_controls

    def test_create_shell_tool(self) -> None:
        t = create_shell_tool()
        assert t.name == "shell"
        assert t.category == ToolCategory.SHELL
        assert t.risk_level == ToolRiskLevel.CRITICAL
        assert t.requires_hitl is True
        assert t.timeout_seconds == 60.0

    def test_create_git_tool(self) -> None:
        t = create_git_tool()
        assert t.name == "git"
        assert t.category == ToolCategory.GIT
        assert "RepoWhitelist" in t.security_controls
        assert "WriteModeGate" in t.security_controls

    def test_create_browser_tool(self) -> None:
        t = create_browser_tool()
        assert t.name == "browser"
        assert t.category == ToolCategory.BROWSER
        assert t.risk_level == ToolRiskLevel.LOW

    def test_create_email_tool(self) -> None:
        t = create_email_tool()
        assert t.name == "email"
        assert t.category == ToolCategory.EMAIL
        assert t.risk_level == ToolRiskLevel.MEDIUM

    def test_create_web_search_tool(self) -> None:
        t = create_web_search_tool()
        assert t.name == "web_search"
        assert t.category == ToolCategory.SEARCH
        assert t.risk_level == ToolRiskLevel.LOW
        assert "QuerySanitizer" in t.security_controls

    def test_create_github_tool(self) -> None:
        t = create_github_tool()
        assert t.name == "github"
        assert t.category == ToolCategory.CUSTOM
        assert "github_list_repos" in t.tools

    def test_create_notion_tool(self) -> None:
        t = create_notion_tool()
        assert t.name == "notion"
        assert t.category == ToolCategory.CUSTOM
        assert "notion_query_database" in t.tools

    def test_create_slack_tool(self) -> None:
        t = create_slack_tool()
        assert t.name == "slack"
        assert t.category == ToolCategory.CUSTOM
        assert "slack_send_message" in t.tools

    def test_create_jira_tool(self) -> None:
        t = create_jira_tool()
        assert t.name == "jira"
        assert t.category == ToolCategory.CUSTOM
        assert "jira_get_issue" in t.tools


class TestModuleFunctions:
    def test_get_tool_definition_exists(self) -> None:
        t = get_tool_definition("file")
        assert t is not None
        assert t.name == "file"

    def test_get_tool_definition_nonexistent(self) -> None:
        assert get_tool_definition("nonexistent") is None

    def test_list_tool_definitions(self) -> None:
        tools = list_tool_definitions()
        names = [t.name for t in tools]
        assert "file" in names
        assert "shell" in names
        assert "git" in names
        assert "browser" in names
        assert "email" in names
        assert "web_search" in names
        assert "github" in names
        assert "notion" in names
        assert "slack" in names
        assert "jira" in names
        assert len(tools) == 10

    def test_builtin_definitions_dict(self) -> None:
        assert "file" in BUILTIN_TOOL_DEFINITIONS
        assert "shell" in BUILTIN_TOOL_DEFINITIONS
        assert "jira" in BUILTIN_TOOL_DEFINITIONS
        assert len(BUILTIN_TOOL_DEFINITIONS) == 10

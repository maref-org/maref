from __future__ import annotations

from maref.tools.tool_schema import (
    ToolCategory,
    ToolDefinition,
    ToolParameter,
    ToolRiskLevel,
    create_browser_tool,
    create_email_tool,
    create_file_tool,
    create_git_tool,
    create_shell_tool,
    get_tool_definition,
    list_tool_definitions,
)


class TestToolEnums:
    def test_risk_level_values(self):
        assert ToolRiskLevel.LOW.value == "low"
        assert ToolRiskLevel.MEDIUM.value == "medium"
        assert ToolRiskLevel.HIGH.value == "high"
        assert ToolRiskLevel.CRITICAL.value == "critical"

    def test_category_values(self):
        assert ToolCategory.FILE.value == "file"
        assert ToolCategory.SHELL.value == "shell"
        assert ToolCategory.GIT.value == "git"
        assert ToolCategory.BROWSER.value == "browser"
        assert ToolCategory.EMAIL.value == "email"


class TestToolParameter:
    def test_defaults(self):
        p = ToolParameter(name="path", type="string")
        assert p.name == "path"
        assert p.type == "string"
        assert p.description == ""
        assert p.required is False
        assert p.default is None

    def test_required_param(self):
        p = ToolParameter(name="path", type="string", description="File path", required=True)
        assert p.required is True
        assert p.description == "File path"


class TestToolDefinition:
    def test_minimal_creation(self):
        t = ToolDefinition(name="test", description="A test tool")
        assert t.name == "test"
        assert t.description == "A test tool"
        assert t.category == ToolCategory.CUSTOM
        assert t.risk_level == ToolRiskLevel.MEDIUM

    def test_read_only_detection(self):
        t = ToolDefinition(name="reader", description="Read-only", tools=["read_file", "list_directory", "get_info"])
        assert t.is_read_only() is True

    def test_not_read_only_with_write(self):
        t = ToolDefinition(name="writer", description="Has write", tools=["read_file", "write_file"])
        assert t.is_read_only() is False

    def test_empty_tools_not_read_only(self):
        t = ToolDefinition(name="empty", description="No tools")
        assert t.is_read_only() is False

    def test_to_dict(self):
        t = ToolDefinition(name="test", description="Test", category=ToolCategory.FILE, risk_level=ToolRiskLevel.HIGH)
        d = t.to_dict()
        assert d["name"] == "test"
        assert d["category"] == "file"
        assert d["risk_level"] == "high"

    def test_from_dict(self):
        data = {
            "name": "restored",
            "description": "Restored from dict",
            "category": "git",
            "risk_level": "low",
            "tools": ["git_status", "git_log"],
            "security_controls": ["Whitelist"],
        }
        t = ToolDefinition.from_dict(data)
        assert t.name == "restored"
        assert t.category == ToolCategory.GIT
        assert t.risk_level == ToolRiskLevel.LOW
        assert t.tools == ["git_status", "git_log"]

    def test_from_dict_with_params(self):
        data = {
            "name": "with_params",
            "description": "Has params",
            "tool_parameters": {
                "run": [{"name": "cmd", "type": "string", "required": True}],
            },
        }
        t = ToolDefinition.from_dict(data)
        assert t.tool_parameters["run"][0].name == "cmd"
        assert t.tool_parameters["run"][0].required is True

    def test_to_json_roundtrip(self):
        t1 = create_file_tool()
        raw = t1.to_json()
        t2 = ToolDefinition.from_json(raw)
        assert t1.name == t2.name
        assert t1.category == t2.category
        assert t1.risk_level == t2.risk_level
        assert t1.tools == t2.tools
        assert t1.security_controls == t2.security_controls

    def test_get_recommended_rule_critical(self):
        t = ToolDefinition(name="danger", description="Dangerous", risk_level=ToolRiskLevel.CRITICAL)
        assert t.get_recommended_rule() == "mcp-rule-003"

    def test_get_recommended_rule_write(self):
        t = ToolDefinition(name="writer", description="Write tool", tools=["write_file"])
        assert t.get_recommended_rule() == "mcp-rule-005"

    def test_get_recommended_rule_read(self):
        t = ToolDefinition(name="reader", description="Read-only", tools=["read_file", "list_directory"])
        assert t.get_recommended_rule() == "mcp-rule-002"

    def test_get_recommended_rule_hitl(self):
        t = ToolDefinition(name="hitl", description="Requires HITL", requires_hitl=True, tools=["write"])
        assert t.get_recommended_rule() == "mcp-rule-005"


class TestBuiltinTools:
    def test_file_tool(self):
        t = create_file_tool()
        assert t.name == "file"
        assert t.category == ToolCategory.FILE
        assert t.risk_level == ToolRiskLevel.HIGH
        assert "read_file" in t.tools
        assert "PathSandbox" in t.security_controls

    def test_shell_tool(self):
        t = create_shell_tool()
        assert t.name == "shell"
        assert t.category == ToolCategory.SHELL
        assert t.risk_level == ToolRiskLevel.CRITICAL
        assert t.requires_hitl is True
        assert t.timeout_seconds == 60.0

    def test_git_tool(self):
        t = create_git_tool()
        assert t.name == "git"
        assert t.category == ToolCategory.GIT
        assert t.risk_level == ToolRiskLevel.MEDIUM

    def test_browser_tool(self):
        t = create_browser_tool()
        assert t.name == "browser"
        assert t.category == ToolCategory.BROWSER
        assert t.risk_level == ToolRiskLevel.LOW

    def test_email_tool(self):
        t = create_email_tool()
        assert t.name == "email"
        assert t.category == ToolCategory.EMAIL
        assert t.risk_level == ToolRiskLevel.MEDIUM

    def test_get_tool_definition(self):
        t = get_tool_definition("file")
        assert t is not None
        assert t.name == "file"
        assert get_tool_definition("nonexistent") is None

    def test_list_tool_definitions(self):
        tools = list_tool_definitions()
        assert len(tools) == 5
        names = [t.name for t in tools]
        assert "file" in names
        assert "shell" in names
        assert "git" in names
        assert "browser" in names
        assert "email" in names

    def test_all_tools_have_correct_category(self):
        for t in list_tool_definitions():
            assert t.category != ToolCategory.CUSTOM

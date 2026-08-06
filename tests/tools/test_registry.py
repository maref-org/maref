from __future__ import annotations

from unittest.mock import MagicMock, patch

from maref.integration.mcp_server import MCPServer
from maref.tools.registry import (
    TOOL_REGISTRY,
    ToolRegistry,
    get_tool_info,
    list_tools,
)


class TestToolRegistryDiscover:
    def test_discover_returns_all_tools(self):
        registry = ToolRegistry()
        tools = registry.discover()
        names = [t["name"] for t in tools]
        assert "file" in names
        assert "shell" in names
        assert "git" in names
        assert "browser" in names
        assert "email" in names

    def test_discover_contains_required_fields(self):
        tools = ToolRegistry().discover()
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "version" in t
            assert "tools" in t
            assert "security_controls" in t

    def test_list_tools_function(self):
        tools = list_tools()
        assert len(tools) == 11
        assert "factory" not in tools[0]


class TestToolRegistryInstall:
    def test_install_file_server(self):
        registry = ToolRegistry()
        server = registry.install("file")
        assert server is not None
        assert "file" in registry._instances

    def test_install_shell_server(self):
        registry = ToolRegistry()
        server = registry.install("shell")
        assert server is not None

    def test_install_git_server(self):
        registry = ToolRegistry()
        server = registry.install("git")
        assert server is not None

    def test_install_browser_server(self):
        registry = ToolRegistry()
        server = registry.install("browser")
        assert server is not None

    def test_install_email_server(self):
        registry = ToolRegistry()
        server = registry.install("email")
        assert server is not None

    def test_install_with_custom_config(self):
        registry = ToolRegistry()
        server = registry.install("file", {"max_read_size": 1024})
        assert server is not None

    def test_install_unknown_tool_raises(self):
        registry = ToolRegistry()
        try:
            registry.install("nonexistent")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "Unknown tool" in str(e)

    def test_install_twice_creates_new_instance(self):
        registry = ToolRegistry()
        server1 = registry.install("file")
        server2 = registry.install("file")
        assert server1 is not server2


class TestToolRegistryListInstalled:
    def test_list_installed_empty_by_default(self):
        registry = ToolRegistry()
        assert registry.list_installed() == []

    def test_list_installed_after_install(self):
        registry = ToolRegistry()
        registry.install("file")
        installed = registry.list_installed()
        assert len(installed) == 1
        assert installed[0]["name"] == "file"

    def test_list_installed_multiple(self):
        registry = ToolRegistry()
        registry.install("file")
        registry.install("shell")
        registry.install("git")
        assert len(registry.list_installed()) == 3


class TestToolRegistryInfo:
    def test_info_valid_tool(self):
        info = ToolRegistry().info("file")
        assert info is not None
        assert info["name"] == "file"
        assert "read_file" in info["tools"]
        assert "PathSandbox" in info["security_controls"]

    def test_info_invalid_tool(self):
        assert ToolRegistry().info("nonexistent") is None

    def test_get_tool_info_function(self):
        info = get_tool_info("shell")
        assert info is not None
        assert "run_command" in info["tools"]
        assert "factory" not in info


class TestToolRegistryPolicy:
    def test_policy_contains_governance_rules(self):
        policy = ToolRegistry().policy("file")
        assert "tools" in policy
        assert "security_controls" in policy
        assert "default_governance_rules" in policy

    def test_policy_safe_tools_mapped_to_rule_002(self):
        policy = ToolRegistry().policy("file")
        for rule in policy["default_governance_rules"]:
            if rule["tool"] in ("read_file", "list_directory", "get_file_info"):
                assert rule["recommended_rule"] == "mcp-rule-002"

    def test_policy_write_tools_mapped_to_rule_005(self):
        policy = ToolRegistry().policy("file")
        for rule in policy["default_governance_rules"]:
            if rule["tool"] in ("write_file", "delete_file", "copy_file", "move_file"):
                assert rule["recommended_rule"] == "mcp-rule-005"

    def test_policy_invalid_tool_raises(self):
        try:
            ToolRegistry().policy("nonexistent")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "Unknown tool" in str(e)


class TestToolRegistryGetServer:
    def test_get_server_none_before_install(self):
        registry = ToolRegistry()
        assert registry.get_server("file") is None

    def test_get_server_after_install(self):
        registry = ToolRegistry()
        registry.install("file")
        assert registry.get_server("file") is not None

    def test_get_server_unknown(self):
        assert ToolRegistry().get_server("nonexistent") is None


class TestToolRegistryGetTransport:
    def test_get_transport_none_before_install(self):
        registry = ToolRegistry()
        assert registry.get_transport("file") is None

    def test_get_transport_after_install(self):
        registry = ToolRegistry()
        registry.install("file")
        transport = registry.get_transport("file")
        assert transport is not None


class TestCodedepthRegistry:
    def test_codedepth_in_discover(self):
        tools = list_tools()
        names = [t["name"] for t in tools]
        assert "codedepth" in names

    def test_codedepth_registry_entry(self):
        assert "codedepth" in TOOL_REGISTRY
        entry = TOOL_REGISTRY["codedepth"]
        assert entry["name"] == "codedepth"
        assert "depth_rebuild" in entry["tools"]

    def test_codedepth_is_installable(self):
        registry = ToolRegistry()
        with patch("maref.codedepth.server.create_code_depth_server") as mock_create:
            mock_server = MagicMock(spec=MCPServer)
            mock_create.return_value = mock_server
            server = registry.install("codedepth", {"repo_path": "/tmp/test"})
            assert server is mock_server
            assert registry.get_server("codedepth") is mock_server

    def test_codedepth_does_not_auto_install(self):
        assert "codedepth" not in ToolRegistry()._instances

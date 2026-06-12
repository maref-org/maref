"""Harness 运行时权限检查钩子。

注册到 "harness.tool_call" 话题，在每次工具调用前检查权限。
危险操作返回 BLOCK，安全操作返回 PASS。
"""

from __future__ import annotations

import re
from typing import Any

from maref.execution.harness.hooks import HarnessHookRegistry
from maref.recursive.hook_registry import HookResult, HookVerdict

# 默认禁止的操作模式（正则）
_DENIED_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-rf\s+/", "filesystem: recursive root deletion"),
    (r"DROP\s+TABLE", "database: DROP TABLE"),
    (r"DROP\s+DATABASE", "database: DROP DATABASE"),
    (r"git\s+push\s+--force", "git: force push"),
    (r"\bchmod\s+777\s+/", "filesystem: world-writable root path"),
    (r":\(\)\{\s*:\|:&\s*\};:", "shell: fork bomb"),
    (r"sudo\s+rm\s+-rf", "filesystem: sudo recursive deletion"),
    (r"format\s+/fs:ntfs", "filesystem: format drive"),
]


class PermissionHook:
    """运行时权限检查钩子。

    用法:
        hook = PermissionHook(harness_registry)
        # 自动在 "harness.tool_call" 话题注册 _check
    """

    def __init__(self, registry: HarnessHookRegistry) -> None:
        self._registry = registry
        self._denied: list[tuple[re.Pattern, str]] = [
            (re.compile(p, re.IGNORECASE), desc) for p, desc in _DENIED_PATTERNS
        ]
        registry.register("harness.tool_call", self._check, priority=100, handler_id="permission_hook")

    def _check(self, event_data: dict[str, Any]) -> HookResult:
        tool = event_data.get("tool", "")
        args = event_data.get("args", "")
        content = f"{tool} {args}"

        for compiled, description in self._denied:
            if compiled.search(content):
                return HookResult(
                    verdict=HookVerdict.BLOCK,
                    handler_id="permission_hook",
                    message=f"Permission denied: {description} (matched: {compiled.pattern})",
                )
        return HookResult(verdict=HookVerdict.PASS, handler_id="permission_hook")


class AllowlistPermissionHook(PermissionHook):
    """白名单模式权限检查：只允许白名单中的工具。"""

    def __init__(self, registry: HarnessHookRegistry, allowed_tools: set[str] | None = None) -> None:
        self._allowed = allowed_tools or {"read", "list", "search", "status", "help"}
        super().__init__(registry)

    def _check(self, event_data: dict[str, Any]) -> HookResult:
        tool = event_data.get("tool", "")
        if tool not in self._allowed:
            return HookResult(
                verdict=HookVerdict.BLOCK,
                handler_id="allowlist_permission_hook",
                message=f"Tool '{tool}' not in allowlist: {sorted(self._allowed)}",
            )
        return HookResult(verdict=HookVerdict.PASS, handler_id="allowlist_permission_hook")

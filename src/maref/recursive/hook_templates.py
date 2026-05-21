from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from maref.recursive.hook_registry import HookRegistry, HookResult, HookVerdict


def destructive_operation_guard(event_data: dict[str, Any]) -> HookResult:
    patterns = [
        r"rm\s+-rf",
        r"DROP\s+TABLE",
        r"DROP\s+DATABASE",
        r"git\s+push\s+--force",
        r"\bsudo\b",
        r"\bchmod\s+777",
        r":(){ :\|:& };:",
    ]
    content = str(event_data)
    for pattern in patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return HookResult(
                verdict=HookVerdict.BLOCK,
                handler_id="destructive_operation_guard",
                message=f"Destructive operation detected: {pattern}",
            )
    return HookResult(verdict=HookVerdict.PASS, handler_id="destructive_operation_guard")


def secret_leak_guard(event_data: dict[str, Any]) -> HookResult:
    patterns = [
        r"sk-[a-zA-Z0-9]{32,}",
        r"AKIA[A-Z0-9]{16}",
        r"Bearer\s+[A-Za-z0-9_\-]{20,}",
        r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----",
    ]
    content = str(event_data)
    for pattern in patterns:
        if re.search(pattern, content):
            return HookResult(
                verdict=HookVerdict.BLOCK,
                handler_id="secret_leak_guard",
                message="Potential secret/key leak detected",
            )
    return HookResult(verdict=HookVerdict.PASS, handler_id="secret_leak_guard")


def integrity_guard(event_data: dict[str, Any]) -> HookResult:
    expected_checksums = event_data.get("expected_checksums", {})
    actual_checksums = event_data.get("actual_checksums", {})
    for path, expected in expected_checksums.items():
        actual = actual_checksums.get(path)
        if actual is None or actual != expected:
            return HookResult(
                verdict=HookVerdict.FATAL,
                handler_id="integrity_guard",
                message=f"Integrity check failed for {path}",
            )
    return HookResult(verdict=HookVerdict.PASS, handler_id="integrity_guard")


def sensitive_path_guard(event_data: dict[str, Any]) -> HookResult:
    sensitive = [
        ".git",
        ".claude",
        ".maref/integrity",
        ".env",
        "credentials",
    ]
    path = event_data.get("path", "") or str(event_data)
    for s in sensitive:
        if s in path:
            return HookResult(
                verdict=HookVerdict.BLOCK,
                handler_id="sensitive_path_guard",
                message=f"Sensitive path access blocked: {s}",
            )
    return HookResult(verdict=HookVerdict.PASS, handler_id="sensitive_path_guard")


@dataclass
class HookTemplate:
    topic: str
    name: str
    handler_func: Any
    description: str = ""
    priority: int = 0


class HookTemplateLibrary:
    def __init__(self) -> None:
        self._templates: dict[str, HookTemplate] = {}

    def register(self, template: HookTemplate) -> None:
        self._templates[template.name] = template

    def get(self, name: str) -> HookTemplate | None:
        return self._templates.get(name)

    def list_templates(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "topic": t.topic,
                "description": t.description,
                "priority": t.priority,
            }
            for t in self._templates.values()
        ]

    def install_all(self, registry: HookRegistry, topic: str) -> list[str]:
        ids: list[str] = []
        for template in self._templates.values():
            if template.topic == topic:
                hid = registry.register(topic, template.handler_func, template.priority, template.name)
                ids.append(hid)
        return ids


def create_default_template_library() -> HookTemplateLibrary:
    lib = HookTemplateLibrary()

    lib.register(HookTemplate(
        topic="maref.layer3.role.pre_invoke",
        name="destructive_operation_guard",
        handler_func=destructive_operation_guard,
        description="Blocks destructive operations (rm -rf, DROP TABLE, sudo, etc.)",
        priority=100,
    ))

    lib.register(HookTemplate(
        topic="maref.layer3.role.post_invoke",
        name="secret_leak_guard",
        handler_func=secret_leak_guard,
        description="Detects and blocks potential secret/key leaks in output",
        priority=90,
    ))

    lib.register(HookTemplate(
        topic="maref.session.start",
        name="integrity_check",
        handler_func=integrity_guard,
        description="SHA256 integrity check on session start",
        priority=200,
    ))

    lib.register(HookTemplate(
        topic="maref.layer3.role.pre_invoke",
        name="sensitive_path_guard",
        handler_func=sensitive_path_guard,
        description="Blocks access to sensitive paths (.git, .claude, credentials)",
        priority=80,
    ))

    return lib

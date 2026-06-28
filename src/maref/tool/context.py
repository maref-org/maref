from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolUseContext:
    agent_id: str = "unknown"
    session_id: str = ""
    project_root: str = ""
    dry_run: bool = True
    environment: dict[str, str] = field(default_factory=dict)
    permissions: dict[str, bool] = field(default_factory=dict)

    def can(self, action: str) -> bool:
        return self.permissions.get(action, False)

    @classmethod
    def default(cls) -> ToolUseContext:
        return cls(
            agent_id="default",
            session_id="",
            project_root=".",
            dry_run=True,
        )

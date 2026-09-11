from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


class ContextOverflowError(RuntimeError):
    pass


ContentRole = Literal["user", "assistant", "tool_result", "system"]


@dataclass
class Message:
    role: ContentRole
    content: str
    name: str = ""
    tool_call_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextMetrics:
    total_chars: int = 0
    total_tokens: int = 0
    message_count: int = 0
    tool_result_count: int = 0
    budget_applied: bool = False
    micro_compacted: bool = False
    collapsed: bool = False
    auto_compacted: bool = False
    snipped: bool = False


class ContextManager:
    TOOL_RESULT_BUDGET: int = 50_000
    COMPACT_THRESHOLD: int = 120_000
    HARD_LIMIT: int = 200_000

    def __init__(
        self,
        tool_result_budget: int | None = None,
        compact_threshold: int | None = None,
        hard_limit: int | None = None,
    ) -> None:
        self._tool_result_budget = tool_result_budget or self.TOOL_RESULT_BUDGET
        self._compact_threshold = compact_threshold or self.COMPACT_THRESHOLD
        self._hard_limit = hard_limit or self.HARD_LIMIT

    async def prepare(self, messages: list[Message]) -> tuple[list[Message], ContextMetrics]:
        metrics = ContextMetrics(total_chars=sum(len(m.content) for m in messages))

        messages = self._apply_tool_result_budget(messages)
        metrics.budget_applied = True
        metrics.tool_result_count = sum(1 for m in messages if m.role == "tool_result")

        messages = self._microcompact(messages)
        metrics.micro_compacted = True

        if self._token_count(messages) > self._compact_threshold:
            messages = await self._collapse(messages)
            metrics.collapsed = True

        if self._token_count(messages) > self._compact_threshold:
            messages = await self._auto_compact(messages)
            metrics.auto_compacted = True

        if self._token_count(messages) > self._compact_threshold:
            messages = await self._snip(messages)
            metrics.snipped = True

        final_tokens = self._token_count(messages)
        if final_tokens > self._hard_limit:
            raise ContextOverflowError(
                f"Context size {final_tokens} exceeds hard limit {self._hard_limit}"
            )

        metrics.total_chars = sum(len(m.content) for m in messages)
        metrics.total_tokens = final_tokens
        metrics.message_count = len(messages)
        return messages, metrics

    def _apply_tool_result_budget(self, messages: list[Message]) -> list[Message]:
        result: list[Message] = []
        for msg in messages:
            if msg.role == "tool_result" and len(msg.content) > self._tool_result_budget:
                ref_path = msg.metadata.get("file_path", "")
                if ref_path:
                    msg.content = (
                        f"[Tool result truncated: {len(msg.content)} chars. "
                        f"Full result at {ref_path}]"
                    )
                else:
                    msg.content = (
                        msg.content[: self._tool_result_budget]
                        + f"\n... [truncated {len(msg.content) - self._tool_result_budget} chars]"
                    )
            result.append(msg)
        return result

    def _microcompact(self, messages: list[Message]) -> list[Message]:
        result: list[Message] = []
        for msg in messages:
            if msg.role == "tool_result" and msg.content:
                lines = msg.content.split("\n")
                if len(lines) > 100:
                    head = lines[:50]
                    tail = lines[-50:]
                    msg.content = (
                        "\n".join(head)
                        + f"\n... [{len(lines) - 100} lines collapsed in tool result] ...\n"
                        + "\n".join(tail)
                    )
            result.append(msg)
        return result

    async def _collapse(self, messages: list[Message]) -> list[Message]:
        result: list[Message] = []
        tool_turns: list[Message] = []

        for msg in messages:
            if msg.role == "tool_result":
                tool_turns.append(msg)
            else:
                result.append(msg)

        if tool_turns:
            total_chars = sum(len(m.content) for m in tool_turns)
            result.append(
                Message(
                    role="tool_result",
                    content=f"[{len(tool_turns)} tool results collapsed: {total_chars} chars total]",
                    metadata={"collapsed": True, "original_count": len(tool_turns)},
                )
            )

        return result

    async def _auto_compact(self, messages: list[Message]) -> list[Message]:
        result: list[Message] = []
        assistant_buffer: list[str] = []

        for msg in messages:
            if msg.role == "assistant":
                assistant_buffer.append(msg.content)
            else:
                if assistant_buffer:
                    merged = "\n".join(assistant_buffer)
                    if len(merged) > self._tool_result_budget:
                        merged = (
                            merged[: self._tool_result_budget]
                            + f"\n... [compressed {len(merged) - self._tool_result_budget} chars]"
                        )
                    result.append(Message(role="assistant", content=merged))
                    assistant_buffer = []
                result.append(msg)

        if assistant_buffer:
            merged = "\n".join(assistant_buffer)
            result.append(Message(role="assistant", content=merged))

        return result

    async def _snip(self, messages: list[Message]) -> list[Message]:
        snip_count = 0
        while self._token_count(messages) > self._compact_threshold:
            idx_to_remove: int | None = None
            for i, msg in enumerate(messages):
                if msg.role == "tool_result" and not msg.metadata.get("critical", False):
                    idx_to_remove = i
                    break
            if idx_to_remove is None:
                break
            removed = messages.pop(idx_to_remove)
            snip_count += 1
            logger.info(
                "Snip removed tool result (%d chars): %s",
                len(removed.content),
                removed.name or "unnamed",
            )
        if snip_count:
            messages.append(
                Message(
                    role="system",
                    content=f"[{snip_count} tool results snipped to fit context budget]",
                    metadata={"snipped": True, "removed_count": snip_count},
                )
            )
        return messages

    @property
    def compact_threshold(self) -> int:
        return self._compact_threshold

    def token_count(self, messages: list[Message]) -> int:
        return self._token_count(messages)

    def _token_count(self, messages: list[Message]) -> int:
        total = 0
        for msg in messages:
            total += len(msg.content)
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_result_budget": self._tool_result_budget,
            "compact_threshold": self._compact_threshold,
            "hard_limit": self._hard_limit,
        }

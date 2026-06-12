from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.recursive.hook_registry import HookRegistry, HookResult, HookVerdict


class AssimilationStage(Enum):
    OBSERVE = "observe"
    ANALYZE = "analyze"
    DISTILL = "distill"
    INTEGRATE = "integrate"
    VERIFY = "verify"


@dataclass
class ToolCallRecord:
    tool_name: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    context_truncated: str
    reasoning_before: str
    reasoning_after: str
    latency_ms: float
    success: bool
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class ReasoningStyleDelta:
    tool_pattern_id: str
    weight_delta: dict[str, float]
    preference_bias: dict[str, float]
    confidence_shift: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_pattern_id": self.tool_pattern_id,
            "weight_delta": self.weight_delta,
            "preference_bias": self.preference_bias,
            "confidence_shift": self.confidence_shift,
        }


class ReverseAssimilationEngine:
    WINDOW_SIZE: int = 50
    DISTILL_THRESHOLD: int = 5

    def __init__(
        self,
        hook_registry: HookRegistry,
    ) -> None:
        self._records: dict[str, list[ToolCallRecord]] = defaultdict(list)
        self._deltas: dict[str, list[ReasoningStyleDelta]] = defaultdict(list)
        self._distill_count: dict[str, int] = defaultdict(int)
        hook_registry.register(
            "maref.layer5.mcp.post_tool_call",
            self._on_tool_call,
            priority=30,
            handler_id="reverse-assimilation",
        )

    def _on_tool_call(self, event_data: dict[str, Any]) -> HookResult:
        agent_id = event_data.get("agent_id", "unknown")
        record = ToolCallRecord(
            tool_name=event_data.get("tool_name", "unknown"),
            input_schema=event_data.get("input_schema", {}),
            output_schema=event_data.get("output_schema", {}),
            context_truncated=str(event_data.get("context_truncated", ""))[:200],
            reasoning_before=str(event_data.get("reasoning_before", ""))[:200],
            reasoning_after=str(event_data.get("reasoning_after", ""))[:200],
            latency_ms=float(event_data.get("latency_ms", 0)),
            success=bool(event_data.get("success", True)),
        )
        records = self._records[agent_id]
        records.append(record)
        if len(records) > self.WINDOW_SIZE:
            records.pop(0)

        if len(records) >= self.DISTILL_THRESHOLD:
            self._distill(agent_id)

        return HookResult(
            verdict=HookVerdict.PASS,
            handler_id="reverse-assimilation",
            message=f"recorded tool call to {record.tool_name}",
        )

    def _distill(self, agent_id: str) -> ReasoningStyleDelta | None:
        records = self._records[agent_id]
        if len(records) < self.DISTILL_THRESHOLD:
            return None

        recent = records[-self.DISTILL_THRESHOLD:]
        successes = sum(1 for r in recent if r.success)
        success_rate = successes / len(recent)
        tool_patterns: dict[str, int] = defaultdict(int)
        for r in recent:
            tool_patterns[r.tool_name] += 1

        primary_tool = max(tool_patterns, key=lambda k: tool_patterns.get(k, 0))
        tool_pattern_id = f"{primary_tool}@{uuid.uuid4().hex[:6]}"

        delta = ReasoningStyleDelta(
            tool_pattern_id=tool_pattern_id,
            weight_delta={"success_rate_bias": success_rate - 0.5},
            preference_bias={primary_tool: tool_patterns[primary_tool] / len(recent)},
            confidence_shift=(success_rate - 0.5) * 0.1,
        )
        self._deltas[agent_id].append(delta)
        self._distill_count[agent_id] += 1

        overflow = len(self._deltas[agent_id]) - self.WINDOW_SIZE
        if overflow > 0:
            self._deltas[agent_id] = self._deltas[agent_id][overflow:]

        return delta

    def get_assimilation_profile(self, agent_id: str) -> dict[str, Any]:
        deltas = self._deltas.get(agent_id, [])
        records = self._records.get(agent_id, [])
        return {
            "agent_id": agent_id,
            "total_records": len(records),
            "total_deltas": len(deltas),
            "distill_count": self._distill_count.get(agent_id, 0),
            "recent_records": [r.to_dict() for r in records[-10:]],
            "assimilated_patterns": [d.to_dict() for d in deltas[-10:]],
        }

    def get_agent_preference_bias(self, agent_id: str) -> dict[str, float]:
        deltas = self._deltas.get(agent_id, [])
        aggregated: dict[str, float] = {}
        for d in deltas:
            for tool, bias in d.preference_bias.items():
                aggregated[tool] = aggregated.get(tool, 0.0) + bias
        if aggregated:
            total = sum(aggregated.values())
            return {k: v / total for k, v in aggregated.items()}
        return {}

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_agents": len(self._records),
            "total_records": sum(len(r) for r in self._records.values()),
            "total_deltas": sum(len(d) for d in self._deltas.values()),
            "total_distills": sum(self._distill_count.values()),
            "agents": list(self._records.keys()),
        }

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from maref.codegen.context import ContextManager, ContextMetrics, Message
from maref.codegen.executor import ToolExecutor
from maref.codegen.permissions import PermissionEngine
from maref.codegen.quality import QualityGateConfig
from maref.codegen.registry import ToolRegistry
from maref.codegen.tool import ToolContext, ToolResult, ToolResultStatus
from maref.evolution.constitution_harness import ConstitutionHarness, EvolutionChange
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.recursive.safety_gate_v2 import SafetyGateV2
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


@dataclass
class LLMToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[tuple[str, dict[str, Any]]]
    stop_reason: Literal["end_turn", "tool_use", "error"]


class CodeGenLLMBackend(Protocol):
    async def generate(
        self,
        messages: list[Message],
        available_tools: list[LLMToolDef],
    ) -> LLMResponse: ...


@dataclass
class LoopState:
    messages: list[Message] = field(default_factory=list)
    tool_use_context: dict[str, Any] = field(default_factory=dict)
    turn_count: int = 0
    max_turns: int = 25
    max_cost_usd: float = 0.50
    accumulated_cost: float = 0.0
    compact_tracking: dict[str, int] = field(default_factory=dict)
    governance_events: list[str] = field(default_factory=list)
    context_metrics: ContextMetrics | None = None


@dataclass
class LoopEvent:
    type: Literal[
        "tool_call",
        "tool_result",
        "text",
        "error",
        "compact_boundary",
        "max_turns",
        "max_cost",
        "governance_transition",
        "audit_log",
    ]
    payload: Any = None
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def tool_call(cls, name: str, inp: Any) -> LoopEvent:
        return cls(type="tool_call", payload={"name": name, "input": inp})

    @classmethod
    def tool_result(cls, name: str, result: ToolResult[Any]) -> LoopEvent:
        return cls(type="tool_result", payload={"name": name, "result": result})

    @classmethod
    def text(cls, content: str) -> LoopEvent:
        return cls(type="text", payload=content)

    @classmethod
    def error(cls, message: str, details: Any = None) -> LoopEvent:
        return cls(type="error", payload={"message": message, "details": details})

    @classmethod
    def compact_boundary(cls, reason: str) -> LoopEvent:
        return cls(type="compact_boundary", payload=reason)

    @classmethod
    def max_turns(cls) -> LoopEvent:
        return cls(type="max_turns")

    @classmethod
    def max_cost(cls) -> LoopEvent:
        return cls(type="max_cost")

    @classmethod
    def governance_transition(cls, from_state: str, to_state: str, reason: str) -> LoopEvent:
        return cls(
            type="governance_transition",
            payload={"from": from_state, "to": to_state, "reason": reason},
        )

    @classmethod
    def audit_log(cls, record_id: str, event_type: str) -> LoopEvent:
        return cls(type="audit_log", payload={"record_id": record_id, "event_type": event_type})


@dataclass
class ExecutionPipelineRecord:
    pipeline_id: str
    proposal_id: str
    events: list[LoopEvent] = field(default_factory=list)
    final_state: str = "unknown"
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    total_turns: int = 0
    tool_call_count: int = 0
    errors: list[str] = field(default_factory=list)

    def finish(self, final_state: str = "completed") -> None:
        self.end_time = time.time()
        self.final_state = final_state

    @property
    def duration_ms(self) -> float:
        end = self.end_time if self.end_time > 0 else time.time()
        return (end - self.start_time) * 1000.0

    def to_audit_records(self, round_num: int = 31) -> list[UnifiedAuditRecord]:
        records: list[UnifiedAuditRecord] = []
        for event in self.events:
            if event.type == "tool_call":
                p = event.payload or {}
                records.append(
                    UnifiedAuditRecord(
                        record_id=make_record_id(
                            "codegen", hash((self.pipeline_id, p.get("name", ""))) % 100000
                        ),
                        timestamp=event.timestamp,
                        layer="evolution",
                        round=round_num,
                        event_type=f"codegen_tool_call_{p.get('name', 'unknown')}",
                        source_module="CodeGenLoop",
                        target_module=self.proposal_id,
                        decision=str(p.get("input", "")),
                        justification=f"Tool call: {p.get('name', 'unknown')}",
                        outcome="initiated",
                        context_refs=[self.pipeline_id],
                    )
                )
            elif event.type == "tool_result":
                p = event.payload or {}
                r = p.get("result")
                outcome = "success" if r and r.is_success else "failure"
                records.append(
                    UnifiedAuditRecord(
                        record_id=make_record_id(
                            "codegen", hash((self.pipeline_id, p.get("name", ""))) % 100000 + 1
                        ),
                        timestamp=event.timestamp,
                        layer="evolution",
                        round=round_num,
                        event_type=f"codegen_tool_result_{p.get('name', 'unknown')}",
                        source_module="CodeGenLoop",
                        target_module=self.proposal_id,
                        decision=str(getattr(r, "status", ToolResultStatus.ERROR).value),
                        justification=f"Tool result: {p.get('name', 'unknown')}",
                        outcome=outcome,
                        context_refs=[self.pipeline_id],
                    )
                )
        return records


class CodeGenLoop:
    def __init__(
        self,
        registry: ToolRegistry,
        permission_engine: PermissionEngine,
        context_manager: ContextManager,
        quality_config: QualityGateConfig | None = None,
        tool_executor: ToolExecutor | None = None,
        governance: GovernanceStateMachine | None = None,
        audit_store: UnifiedAuditStore | None = None,
        constitution_harness: ConstitutionHarness | None = None,
        safety_gate: SafetyGateV2 | None = None,
    ) -> None:
        self._registry = registry
        self._permission_engine = permission_engine
        self._context_manager = context_manager
        self._quality_config = quality_config or QualityGateConfig()
        self._tool_executor = tool_executor or ToolExecutor(registry)
        self._governance = governance or GovernanceStateMachine()
        self._audit_store = audit_store or UnifiedAuditStore()
        self._constitution = constitution_harness or ConstitutionHarness()
        self._safety_gate = safety_gate or SafetyGateV2()
        self._llm_backend: CodeGenLLMBackend | None = None

    def attach_llm(self, backend: CodeGenLLMBackend) -> None:
        self._llm_backend = backend

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def permission_engine(self) -> PermissionEngine:
        return self._permission_engine

    @property
    def governance(self) -> GovernanceStateMachine:
        return self._governance

    async def execute(
        self,
        initial_messages: list[Message],
        tool_calls: list[tuple[str, Any]],
        ctx: ToolContext,
        max_turns: int = 25,
        max_cost_usd: float = 0.50,
        proposal: Any = None,
        round_num: int = 31,
    ) -> ExecutionPipelineRecord:
        state = LoopState(
            messages=list(initial_messages),
            max_turns=max_turns,
            max_cost_usd=max_cost_usd,
        )
        pipeline = ExecutionPipelineRecord(
            pipeline_id=f"codegen_{int(time.time())}_{id(state)}",
            proposal_id=ctx.agent_id,
        )

        state.messages, metrics = await self._context_manager.prepare(state.messages)
        state.context_metrics = metrics

        if self._llm_backend is not None:
            async for event in self._loop_llm(state, ctx, pipeline, proposal, round_num):
                pipeline.events.append(event)
                if event.type == "tool_call":
                    pipeline.tool_call_count += 1
                elif event.type == "error":
                    pipeline.errors.append(str(event.payload))
                elif event.type == "max_turns":
                    pipeline.finish("max_turns_reached")
                    return pipeline
                elif event.type == "max_cost":
                    pipeline.finish("max_cost_reached")
                    return pipeline
        else:
            async for event in self._loop(state, tool_calls, ctx):
                pipeline.events.append(event)
                if event.type == "tool_call":
                    pipeline.tool_call_count += 1
                elif event.type == "error":
                    pipeline.errors.append(str(event.payload))
                elif event.type == "max_turns":
                    pipeline.finish("max_turns_reached")
                    return pipeline
                elif event.type == "max_cost":
                    pipeline.finish("max_cost_reached")
                    return pipeline

        pipeline.total_turns = state.turn_count
        pipeline.finish("completed")
        return pipeline

    async def _loop_llm(
        self,
        state: LoopState,
        ctx: ToolContext,
        pipeline: ExecutionPipelineRecord,
        proposal: Any = None,
        round_num: int = 31,
    ) -> AsyncGenerator[LoopEvent, None]:
        if self._llm_backend is None:
            return

        self._governance.transition(GovernanceState.INIT, "codegen_loop_start")
        yield LoopEvent.governance_transition("NONE", "INIT", "codegen_loop_start")

        available_tools = self._build_tool_defs()

        while state.turn_count < state.max_turns:
            state.messages, metrics = await self._context_manager.prepare(state.messages)
            state.context_metrics = metrics

            self._governance.transition(GovernanceState.ANALYZE, f"turn_{state.turn_count}")
            yield LoopEvent.governance_transition(
                self._governance.current_state.name, "ANALYZE", f"turn_{state.turn_count}"
            )

            try:
                response = await self._llm_backend.generate(state.messages, available_tools)
            except Exception as e:
                yield LoopEvent.error(f"LLM generation failed: {e}")
                self._governance.force_halt("llm_error")
                return

            if response.text:
                yield LoopEvent.text(response.text)
                state.messages.append(Message(role="assistant", content=response.text))

            if response.stop_reason == "error":
                yield LoopEvent.error("LLM returned error stop_reason", response.text)
                break

            if not response.tool_calls:
                if response.stop_reason == "end_turn":
                    break
                yield LoopEvent.error("No tool calls and not end_turn")
                break

            self._governance.transition(
                GovernanceState.ACT, f"executing_{len(response.tool_calls)}_tools"
            )
            yield LoopEvent.governance_transition(
                "ANALYZE", "ACT", f"tool_dispatch_{state.turn_count}"
            )

            governance_check = self._run_governance_check(response, proposal)
            if not governance_check.get("allowed", True):
                yield LoopEvent.error("Governance check blocked execution", governance_check)
                self._governance.force_halt("governance_block")
                pipeline.finish("FAILED_GOVERNANCE")
                return

            tool_call_list: list[tuple[str, Any]] = []
            for tool_name, tool_input in response.tool_calls:
                try:
                    inp_obj = self._build_tool_input(tool_name, tool_input)
                    tool_call_list.append((tool_name, inp_obj))
                except Exception as e:
                    yield LoopEvent.error(f"Failed to build input for {tool_name}: {e}")

            if tool_call_list:
                call_results: list[tuple[int, ToolResult[Any]]] = []
                async for idx, result in self._tool_executor.execute_all(
                    [(name, inp, ctx) for name, inp in tool_call_list]
                ):
                    call_results.append((idx, result))

                call_results.sort(key=lambda x: x[0])
                for idx, result in call_results:
                    name, inp = tool_call_list[idx]
                    yield LoopEvent.tool_call(name, inp)
                    yield LoopEvent.tool_result(name, result)

                    self._audit_append(name, result, pipeline, round_num)

                    result_msg = Message(
                        role="tool_result",
                        content=(result.data.model_dump_json() if result.data else result.error),
                        name=name,
                        metadata={
                            "status": result.status.value,
                            "duration_ms": result.duration_ms,
                            "truncated": result.truncated,
                        },
                    )
                    state.messages.append(result_msg)

                    cost_estimate = result.duration_ms * 0.0001
                    state.accumulated_cost += cost_estimate
                    if state.accumulated_cost > state.max_cost_usd:
                        yield LoopEvent.max_cost()

                    if not result.is_success:
                        yield LoopEvent.error(f"Tool {name} failed: {result.error}")

            self._governance.transition(GovernanceState.VERIFY, f"turn_{state.turn_count}_complete")
            yield LoopEvent.governance_transition("ACT", "VERIFY", f"turn_{state.turn_count}")

            state.turn_count += 1

            ctx_compact = self._context_manager.token_count(state.messages)
            if ctx_compact > self._context_manager.compact_threshold:
                yield LoopEvent.compact_boundary("context_threshold_exceeded")

        if state.turn_count >= state.max_turns:
            yield LoopEvent.max_turns()

        self._governance.transition(GovernanceState.REPORT, "codegen_loop_end")
        yield LoopEvent.governance_transition(
            self._governance.current_state.name, "REPORT", "codegen_loop_end"
        )

    async def _loop(
        self,
        state: LoopState,
        tool_calls: list[tuple[str, Any]],
        ctx: ToolContext,
    ) -> AsyncGenerator[LoopEvent, None]:
        remaining_calls = list(tool_calls)
        self._governance.transition(GovernanceState.INIT, "codegen_loop_start")
        yield LoopEvent.governance_transition("NONE", "INIT", "codegen_loop_start")

        while state.turn_count < state.max_turns:
            if not remaining_calls:
                break

            state.messages, metrics = await self._context_manager.prepare(state.messages)
            state.context_metrics = metrics

            batch = remaining_calls[:5]
            remaining_calls = remaining_calls[5:]

            self._governance.transition(GovernanceState.ACT, f"tool_batch_{state.turn_count}")
            yield LoopEvent.governance_transition(
                self._governance.current_state.name, "ACT", f"batch_{state.turn_count}"
            )

            call_results: list[tuple[int, ToolResult[Any]]] = []
            async for idx, result in self._tool_executor.execute_all(
                [(name, inp, ctx) for name, inp in batch]
            ):
                call_results.append((idx, result))

            call_results.sort(key=lambda x: x[0])
            for idx, result in call_results:
                name, inp = batch[idx]
                yield LoopEvent.tool_call(name, inp)
                yield LoopEvent.tool_result(name, result)

                self._audit_append(name, result, None, 31)

                result_msg = Message(
                    role="tool_result",
                    content=(result.data.model_dump_json() if result.data else result.error),
                    name=name,
                    metadata={
                        "status": result.status.value,
                        "duration_ms": result.duration_ms,
                        "truncated": result.truncated,
                    },
                )
                state.messages.append(result_msg)

                cost_estimate = result.duration_ms * 0.0001
                state.accumulated_cost += cost_estimate
                if state.accumulated_cost > state.max_cost_usd:
                    yield LoopEvent.max_cost()

                if not remaining_calls and not result.is_success:
                    yield LoopEvent.error(
                        f"Tool {name} failed: {result.error}",
                        result.to_dict(),
                    )

            self._governance.transition(GovernanceState.VERIFY, f"turn_{state.turn_count}_complete")
            yield LoopEvent.governance_transition("ACT", "VERIFY", f"turn_{state.turn_count}")

            state.turn_count += 1

            ctx_compact = self._context_manager.token_count(state.messages)
            if ctx_compact > self._context_manager.compact_threshold:
                yield LoopEvent.compact_boundary("context_threshold_exceeded")

        if state.turn_count >= state.max_turns:
            yield LoopEvent.max_turns()

        self._governance.transition(GovernanceState.REPORT, "codegen_loop_end")
        yield LoopEvent.governance_transition(
            self._governance.current_state.name, "REPORT", "codegen_loop_end"
        )

    def _audit_append(
        self,
        tool_name: str,
        result: ToolResult[Any],
        pipeline: Any,
        round_num: int = 31,
    ) -> None:
        record = UnifiedAuditRecord(
            record_id=make_record_id("codegen", hash((tool_name, time.time_ns())) % 100000),
            timestamp=time.time(),
            layer="evolution",
            round=round_num,
            event_type=f"codegen_tool_{tool_name}",
            source_module="CodeGenLoop",
            target_module=tool_name,
            decision=result.status.value,
            justification=f"Tool {tool_name}: {result.error if result.error else 'ok'}",
            outcome="success" if result.is_success else "failure",
            context_refs=[tool_name],
        )
        self._audit_store.append(record)

    def _run_governance_check(
        self,
        response: LLMResponse,
        proposal: Any,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"allowed": True}

        if proposal is not None:
            change = EvolutionChange(
                change_id=getattr(proposal, "proposal_id", "codegen"),
                files=[],
                description=getattr(proposal, "rationale", ""),
                actor="codegen_loop",
                audit_planned=True,
            )
            constitution_result = self._constitution.check_change(change)
            if not constitution_result.allowed:
                result["allowed"] = False
                result["violations"] = constitution_result.violations
                result["reasons"] = constitution_result.reasons

        return result

    def _build_tool_defs(self) -> list[LLMToolDef]:
        defs: list[LLMToolDef] = []
        for name in self._registry.list_tools():
            tool = self._registry.get(name)
            schema = {}
            if tool.input_schema is not None:
                s = tool.input_schema
                schema = {
                    k: {"type": v.__name__ if hasattr(v, "__name__") else str(v)}
                    for k, v in (getattr(s, "model_fields", {})).items()
                }
            defs.append(
                LLMToolDef(
                    name=tool.name,
                    description=getattr(tool, "description", ""),
                    input_schema=schema,
                )
            )
        return defs

    def _build_tool_input(self, tool_name: str, raw_input: dict[str, Any]) -> Any:
        tool = self._registry.get(tool_name)
        if tool.input_schema is not None:
            return tool.input_schema(**raw_input)
        return raw_input

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from maref.execution.harness.base import BaseHarness
from maref.execution.harness.exceptions import HarnessAbortedError, HarnessExecutionError
from maref.execution.harness.lifecycle import HarnessLifecycleState, _VALID_TRANSITIONS
from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus


class UnifiedHarness(BaseHarness):
    """完整生命周期管理的统一 Harness。

    生命周期: INIT → PREFLIGHT → READY → RUNNING → VALIDATING → REPORTING → DONE
    异常时 -> FAILED (吸收态)。

    可选集成:
    - governance_bridge: 每个阶段检查治理状态机和 CircuitBreaker
    - orchestration_bridge: 任务分解和执行
    - hook_registry: HarnessHookRegistry 实例，各阶段触发 topic 事件
    - audit_logger: HarnessAuditLogger 实例，各阶段写入审计日志
    - run_hook: 每步执行后调用的钩子 (已弃用，用 hook_registry 替代)
    """

    def __init__(
        self,
        governance_bridge: Any = None,
        orchestration_bridge: Any = None,
        hook_registry: Any = None,
        audit_logger: Any = None,
        context_loader: Any = None,
        context_compressor: Any = None,
        tool_orchestrator: Any = None,
        run_hook: Callable[[HarnessLifecycleState, HarnessResult], None] | None = None,
        memory_hub: Any = None,
    ) -> None:
        super().__init__()
        self._lifecycle_state = HarnessLifecycleState.INIT
        self._governance_bridge = governance_bridge
        self._orchestration_bridge = orchestration_bridge
        self._hook_registry = hook_registry
        self._audit_logger = audit_logger
        self._context_loader = context_loader
        self._context_compressor = context_compressor
        self._tool_orchestrator = tool_orchestrator
        self._run_hook = run_hook
        self._memory_hub = memory_hub
        self._transition_history: list[HarnessLifecycleState] = [HarnessLifecycleState.INIT]
        self._step_handlers: list[Callable[[], None]] = []
        self._context: dict[str, str] = {}
        self._config: HarnessConfig | None = None

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def lifecycle_state(self) -> HarnessLifecycleState:
        return self._lifecycle_state

    @property
    def transition_history(self) -> list[HarnessLifecycleState]:
        return list(self._transition_history)

    @property
    def is_terminal(self) -> bool:
        return self._lifecycle_state in (HarnessLifecycleState.DONE, HarnessLifecycleState.FAILED)

    # ── Step handlers ───────────────────────────────────────────────────

    def add_step_handler(self, handler: Callable[[], None]) -> None:
        self._step_handlers.append(handler)

    # ── Lifecycle transitions ──────────────────────────────────────────

    def _transition(self, target: HarnessLifecycleState) -> None:
        valid = _VALID_TRANSITIONS.get(self._lifecycle_state, [])
        if target not in valid:
            raise HarnessExecutionError(
                f"invalid lifecycle transition: {self._lifecycle_state.value} -> {target.value}"
            )
        self._lifecycle_state = target
        self._transition_history.append(target)

    def _check_governance(self, stage: str) -> None:
        if self._governance_bridge is None:
            return
        allowed = self._governance_bridge.check(stage)
        self._governance_bridge.record(stage, allowed)
        if not allowed:
            self._lifecycle_state = HarnessLifecycleState.FAILED
            self._transition_history.append(HarnessLifecycleState.FAILED)
            raise HarnessAbortedError(
                f"governance block at lifecycle stage '{stage}', "
                f"governance state={self._governance_bridge.state_name}"
            )

    def _fire_hook(self, topic: str, event_data: dict[str, Any]) -> None:
        """触发 HookRegistry 话题，如果钩子返回 BLOCK 则抛出异常。"""
        if self._hook_registry is None:
            return
        result = self._hook_registry.fire(topic, event_data)
        if not result.passed:
            raise HarnessAbortedError(
                f"hook '{topic}' blocked: {result.verdict} ({result.error or 'no message'})"
            )

    # ── Context management ─────────────────────────────────────────────

    @property
    def context(self) -> dict[str, str]:
        return dict(self._context)

    def _load_context(self) -> None:
        if self._context_loader is None:
            return
        for key in self._context_loader.keys():
            try:
                self._context[key] = self._context_loader.load(key)
            except Exception as e:
                self._context[key] = f"<error: {e}>"

        budget = self._config.token_budget if self._config else 0
        if budget > 0 and self._context_compressor is not None:
            for key, value in self._context.items():
                compressed = self._context_compressor.compress(value, budget)
                self._context[key] = compressed

    # ── BaseHarness interface ──────────────────────────────────────────

    def configure(self, config: HarnessConfig) -> None:
        self._config = config
        if self._governance_bridge:
            self._governance_bridge.configure(config)

    def preflight(self) -> list[str]:
        warnings: list[str] = []
        self._transition(HarnessLifecycleState.PREFLIGHT)
        self._check_governance("preflight")
        self._fire_hook("harness.preflight", {"stage": "preflight"})

        if self._config is None:
            warnings.append("no configuration set")

        if self._audit_logger:
            self._audit_logger.log_preflight(warnings)

        self._transition(HarnessLifecycleState.READY)
        return warnings

    def run(self, round_id: str = "") -> HarnessResult:
        self._transition(HarnessLifecycleState.RUNNING)
        self._check_governance("running")
        self._fire_hook("harness.start", {"round_id": round_id})

        if self._audit_logger:
            harness_type = self._config.harness_type if self._config else "unified"
            self._audit_logger.start_round(harness_type, round_id)

        if self._config is None:
            self._lifecycle_state = HarnessLifecycleState.FAILED
            self._transition_history.append(HarnessLifecycleState.FAILED)
            result = HarnessResult(
                harness_type="unified",
                round_id=round_id,
                status=HarnessStatus.FAILED,
                errors=["no configuration set"],
            )
            if self._audit_logger:
                self._audit_logger.log_fail("no configuration set")
            return result

        start = time.time()
        errors: list[str] = []
        metrics: dict[str, Any] = {}

        self._load_context()

        try:
            for i, handler in enumerate(self._step_handlers):
                self._check_governance("step")
                self._fire_hook("harness.step", {"step_index": i})
                handler()
                if self._memory_hub is not None and self._config is not None:
                    recording_enabled = self._config.extra.get("memory_recording_enabled", True)
                    if recording_enabled:
                        self._memory_hub.record_decision(
                            agent_id="harness",
                            decision_type=f"step_{i}",
                            input_summary=f"harness step {i}",
                            output_summary=f"completed step {i}",
                        )
                if self._audit_logger:
                    self._audit_logger.log_step(f"step_{i}", "ok")
        except HarnessAbortedError:
            if self._audit_logger:
                self._audit_logger.log_fail("governance_abort")
            raise
        except Exception as e:
            errors.append(str(e))
            if self._audit_logger:
                self._audit_logger.log_step("error", str(e))

        if errors:
            self._lifecycle_state = HarnessLifecycleState.FAILED
            self._transition_history.append(HarnessLifecycleState.FAILED)
            self._fire_hook("harness.fail", {"errors": errors})
            duration = time.time() - start
            result = HarnessResult(
                harness_type="unified",
                round_id=round_id,
                status=HarnessStatus.FAILED,
                duration_s=duration,
                errors=errors,
                metrics=metrics,
            )
            if self._audit_logger:
                self._audit_logger.log_fail("; ".join(errors[:3]))
            if self._run_hook:
                self._run_hook(HarnessLifecycleState.FAILED, result)
            return result

        # VALIDATING
        self._transition(HarnessLifecycleState.VALIDATING)
        self._check_governance("validating")
        self._fire_hook("harness.validate", {"step_count": len(self._step_handlers)})
        duration = time.time() - start
        result = HarnessResult(
            harness_type=self._config.harness_type if self._config else "unified",
            round_id=round_id,
            status=HarnessStatus.SUCCEEDED,
            duration_s=duration,
            metrics=metrics,
        )

        if not self.validate(result):
            result.status = HarnessStatus.FAILED
            result.errors.append("validation failed")
            if self._audit_logger:
                self._audit_logger.log_validate(False)

        if self._audit_logger:
            self._audit_logger.log_validate(result.passed)

        # REPORTING
        self._transition(HarnessLifecycleState.REPORTING)
        self._check_governance("reporting")

        # DONE
        self._transition(HarnessLifecycleState.DONE)
        result.status = HarnessStatus.SUCCEEDED if not result.errors else HarnessStatus.FAILED

        self._fire_hook("harness.stop", {"status": result.status.value, "duration_s": duration})

        if self._audit_logger:
            self._audit_logger.log_stop(result)

        if self._run_hook:
            self._run_hook(HarnessLifecycleState.DONE, result)

        return result

    def validate(self, result: HarnessResult) -> bool:
        return result.passed

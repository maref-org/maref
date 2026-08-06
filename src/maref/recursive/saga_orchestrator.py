from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.recursive.blast_radius import BlastRadiusController


class SagaState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPENSATING = "compensating"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"
    TIMED_OUT = "timed_out"


@dataclass
class StepResult:
    step_id: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0

    @property
    def is_failure(self) -> bool:
        return not self.success


@dataclass
class RetryPolicy:
    max_retries: int = 0
    backoff_factor: float = 1.0
    retry_on: list[str] = field(default_factory=list)

    def should_retry(self, error: str, attempt: int) -> bool:
        if attempt >= self.max_retries:
            return False
        if not self.retry_on:
            return True
        return any(pattern in error.lower() for pattern in self.retry_on)


@dataclass
class SagaStep:
    step_id: str
    description: str
    execute_fn: Callable[[dict[str, Any]], StepResult]
    compensate_fn: Callable[[dict[str, Any]], StepResult] | None = None
    timeout_seconds: float = 30.0
    retry_policy: RetryPolicy | None = None
    required_capabilities: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)

    def execute(self, context: dict[str, Any]) -> StepResult:
        return self.execute_fn(context)

    def compensate(self, context: dict[str, Any]) -> StepResult | None:
        if self.compensate_fn is None:
            return None
        return self.compensate_fn(context)


@dataclass
class SagaExecutionRecord:
    step_id: str
    status: StepStatus
    result: StepResult | None = None
    compensation_result: StepResult | None = None
    started_at: float = 0.0
    completed_at: float = 0.0
    retries: int = 0


@dataclass
class SagaResult:
    saga_id: str
    state: SagaState
    steps_executed: int = 0
    steps_compensated: int = 0
    step_records: list[SagaExecutionRecord] = field(default_factory=list)
    error: str = ""
    duration_ms: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0

    def __post_init__(self) -> None:
        if self.started_at > 0 and self.completed_at > 0:
            self.duration_ms = (self.completed_at - self.started_at) * 1000

    @property
    def is_success(self) -> bool:
        return self.state == SagaState.COMPLETED

    def failed_step(self) -> SagaExecutionRecord | None:
        for rec in self.step_records:
            if rec.status == StepStatus.FAILED:
                return rec
        return None


@dataclass
class BackpressureConfig:
    max_concurrent_sagas: int = 10
    max_concurrent_steps: int = 50
    throttle_delay_ms: float = 0.0
    circuit_breaker_open: bool = False


class SagaOrchestrator:
    def __init__(
        self,
        backpressure: BackpressureConfig | None = None,
        blast_radius: BlastRadiusController | None = None,
    ) -> None:
        self._active_sagas: dict[str, Saga] = {}
        self._history: list[SagaResult] = []
        self._backpressure = backpressure or BackpressureConfig()
        self._blast_radius = blast_radius
        self._active_step_count: int = 0
        self._on_throttle: Callable[[str], None] | None = None

    def register_backpressure_callback(self, callback: Callable[[str], None]) -> None:
        self._on_throttle = callback

    def execute(self, saga: Saga, initial_context: dict[str, Any] | None = None) -> SagaResult:
        if self._backpressure.circuit_breaker_open:
            return SagaResult(
                saga_id=saga.saga_id,
                state=SagaState.FAILED,
                error="Circuit breaker open, saga execution blocked",
                started_at=time.time(),
                completed_at=time.time(),
            )

        if len(self._active_sagas) >= self._backpressure.max_concurrent_sagas:
            if self._on_throttle:
                self._on_throttle(saga.saga_id)
            return SagaResult(
                saga_id=saga.saga_id,
                state=SagaState.FAILED,
                error=f"Backpressure: max concurrent sagas ({self._backpressure.max_concurrent_sagas}) reached",
                started_at=time.time(),
                completed_at=time.time(),
            )

        result = SagaResult(
            saga_id=saga.saga_id,
            state=SagaState.RUNNING,
            started_at=time.time(),
        )

        self._active_sagas[saga.saga_id] = saga
        context = dict(initial_context) if initial_context else {}

        try:
            saga.state = SagaState.RUNNING
            completed_steps: list[SagaExecutionRecord] = []

            for step in saga.steps:
                if step.step_id in saga._completed:
                    continue

                rec = self._execute_step(step, context)
                result.step_records.append(rec)

                if rec.status == StepStatus.COMPLETED:
                    completed_steps.append(rec)
                    saga._completed.add(step.step_id)
                    context.update(rec.result.data if rec.result else {})
                else:
                    result.error = rec.result.error if rec.result else f"Step {step.step_id} failed"
                    result.steps_executed = len(completed_steps)

                    saga.state = SagaState.COMPENSATING
                    compensated = self._compensate_steps(
                        saga, completed_steps, context, failed_step_id=step.step_id
                    )
                    result.steps_compensated = compensated
                    result.state = SagaState.FAILED
                    result.completed_at = time.time()
                    result.duration_ms = (result.completed_at - result.started_at) * 1000
                    saga.state = SagaState.FAILED
                    self._history.append(result)
                    self._active_sagas.pop(saga.saga_id, None)
                    return result

            result.steps_executed = len(completed_steps)
            result.state = SagaState.COMPLETED
            result.completed_at = time.time()
            result.duration_ms = (result.completed_at - result.started_at) * 1000
            saga.state = SagaState.COMPLETED
            self._history.append(result)

        except Exception as e:
            result.state = SagaState.FAILED
            result.error = str(e)
            result.completed_at = time.time()
            result.duration_ms = (result.completed_at - result.started_at) * 1000
            saga.state = SagaState.FAILED
        finally:
            self._active_sagas.pop(saga.saga_id, None)

        return result

    def execute_parallel_group(
        self, saga: Saga, group_step_ids: list[str], initial_context: dict[str, Any] | None = None
    ) -> SagaResult:
        group_steps = [s for s in saga.steps if s.step_id in group_step_ids]
        if not group_steps:
            return SagaResult(
                saga_id=saga.saga_id,
                state=SagaState.FAILED,
                error="No steps found in parallel group",
                started_at=time.time(),
                completed_at=time.time(),
            )
        non_group = [s for s in saga.steps if s.step_id not in group_step_ids]
        parallel_saga = Saga(
            saga_id=f"{saga.saga_id}_parallel",
            steps=group_steps,
        )
        if non_group:
            before_group = Saga(
                saga_id=f"{saga.saga_id}_pre",
                steps=[
                    s for s in non_group if saga.steps.index(s) < saga.steps.index(group_steps[0])
                ],
            )
            after_group = Saga(
                saga_id=f"{saga.saga_id}_post",
                steps=[
                    s for s in non_group if saga.steps.index(s) > saga.steps.index(group_steps[-1])
                ],
            )
            if before_group.steps:
                pre_result = self.execute(before_group, initial_context)
                if not pre_result.is_success:
                    return pre_result
            parallel_result = self.execute(parallel_saga, initial_context)
            if not parallel_result.is_success:
                return parallel_result
            if after_group.steps:
                return self.execute(after_group, initial_context)
            return parallel_result
        return self.execute(parallel_saga, initial_context)

    def _execute_step(self, step: SagaStep, context: dict[str, Any]) -> SagaExecutionRecord:
        rec = SagaExecutionRecord(
            step_id=step.step_id,
            status=StepStatus.RUNNING,
            started_at=time.time(),
        )

        if self._backpressure.throttle_delay_ms > 0:
            time.sleep(self._backpressure.throttle_delay_ms / 1000.0)

        attempt = 0
        while True:
            try:
                result = step.execute(context)
                rec.retries = attempt
                rec.result = result
                rec.completed_at = time.time()

                if result.success:
                    rec.status = StepStatus.COMPLETED
                else:
                    retryable = step.retry_policy and step.retry_policy.should_retry(
                        result.error, attempt
                    )
                    if retryable:
                        attempt += 1
                        if step.retry_policy:
                            delay = step.retry_policy.backoff_factor * (2 ** (attempt - 1))
                            time.sleep(delay)
                        continue
                    rec.status = StepStatus.FAILED
                return rec
            except Exception as e:
                result = StepResult(step_id=step.step_id, success=False, error=str(e))
                rec.result = result
                retryable = step.retry_policy and step.retry_policy.should_retry(str(e), attempt)
                if retryable:
                    attempt += 1
                    if step.retry_policy:
                        delay = step.retry_policy.backoff_factor * (2 ** (attempt - 1))
                        time.sleep(delay)
                    continue
                rec.status = StepStatus.FAILED
                rec.completed_at = time.time()
                return rec

    def _compensate_steps(
        self,
        saga: Saga,
        completed_steps: list[SagaExecutionRecord],
        context: dict[str, Any],
        failed_step_id: str = "",
    ) -> int:
        step_map = {s.step_id: s for s in saga.steps}
        completed_ids = [rec.step_id for rec in completed_steps]

        # Blast-radius control: decide which steps to compensate
        if self._blast_radius is not None:
            decision = self._blast_radius.decide(
                failed_step_id=failed_step_id,
                completed_step_ids=completed_ids,
            )
            ids_to_compensate = set(decision.steps_to_compensate)
        else:
            ids_to_compensate = set(completed_ids)

        compensated = 0
        for rec in reversed(completed_steps):
            if rec.step_id not in ids_to_compensate:
                continue
            step = step_map.get(rec.step_id)
            if step is None or step.compensate_fn is None:
                continue
            try:
                comp_result = step.compensate(context)
                rec.compensation_result = comp_result
                rec.status = StepStatus.COMPENSATED
                compensated += 1
            except Exception:
                rec.status = StepStatus.COMPENSATED
                compensated += 1
        return compensated

    def history(self) -> list[SagaResult]:
        return list(self._history)

    def active_saga_count(self) -> int:
        return len(self._active_sagas)


@dataclass
class Saga:
    saga_id: str = ""
    description: str = ""
    steps: list[SagaStep] = field(default_factory=list)
    state: SagaState = SagaState.PENDING
    _completed: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.saga_id:
            self.saga_id = f"saga_{uuid.uuid4().hex[:12]}"

    def add_step(
        self,
        step_or_fn,
        compensation=None,
        description: str = "",
        timeout_seconds: float = 30.0,
        retry_policy: RetryPolicy | None = None,
    ) -> Saga:
        if callable(step_or_fn) and not isinstance(step_or_fn, SagaStep):
            step = SagaStep(
                step_id=f"{self.saga_id}_step_{len(self.steps) + 1}",
                description=description or f"step_{len(self.steps) + 1}",
                execute_fn=step_or_fn,
                compensate_fn=compensation,
                timeout_seconds=timeout_seconds,
                retry_policy=retry_policy,
            )
        else:
            step = step_or_fn
        self.steps.append(step)
        return self

    def add_parallel_group(
        self,
        steps: list[SagaStep],
        compensation_group: Callable[[dict[str, Any]], StepResult] | None = None,
    ) -> Saga:
        group_id = f"{self.saga_id}_parallel_{len(self.steps)}"
        for step in steps:
            step.step_id = f"{group_id}_{step.step_id}"
            if compensation_group and step.compensate_fn is None:
                step.compensate_fn = compensation_group
            self.steps.append(step)
        return self

    def step_count(self) -> int:
        return len(self.steps)


def transaction_boundary(saga: Saga, before_id: str, after_id: str) -> Saga:
    boundary_step = SagaStep(
        step_id=f"{saga.saga_id}_tx_boundary_{before_id}_{after_id}",
        description=f"Transaction boundary: {before_id} → {after_id}",
        execute_fn=lambda ctx: StepResult(
            step_id="tx_boundary",
            success=True,
            data={"boundary": f"{before_id}_{after_id}"},
        ),
    )
    before_idx = next((i for i, s in enumerate(saga.steps) if s.step_id == before_id), None)
    after_idx = next((i for i, s in enumerate(saga.steps) if s.step_id == after_id), None)
    if before_idx is not None and after_idx is not None:
        insert_at = max(before_idx, after_idx)
        saga.steps.insert(insert_at, boundary_step)
    return saga

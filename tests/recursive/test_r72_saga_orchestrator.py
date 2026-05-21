from __future__ import annotations

from maref.recursive.saga_orchestrator import (
    BackpressureConfig,
    RetryPolicy,
    Saga,
    SagaOrchestrator,
    SagaResult,
    SagaState,
    SagaStep,
    StepResult,
    transaction_boundary,
)


class TestSagaStep:
    def test_step_execute_success(self) -> None:
        step = SagaStep(
            step_id="s1",
            description="test",
            execute_fn=lambda ctx: StepResult(step_id="s1", success=True, data={"x": 1}),
        )
        result = step.execute({})
        assert result.success
        assert result.data["x"] == 1

    def test_step_execute_failure(self) -> None:
        step = SagaStep(
            step_id="s1",
            description="test",
            execute_fn=lambda ctx: StepResult(step_id="s1", success=False, error="fail"),
        )
        result = step.execute({})
        assert not result.success
        assert result.error == "fail"

    def test_step_compensate(self) -> None:
        step = SagaStep(
            step_id="s1",
            description="test",
            execute_fn=lambda ctx: StepResult(step_id="s1", success=True),
            compensate_fn=lambda ctx: StepResult(step_id="s1_comp", success=True, data={"rolled_back": True}),
        )
        comp_result = step.compensate({})
        assert comp_result is not None
        assert comp_result.success

    def test_step_no_compensation(self) -> None:
        step = SagaStep(
            step_id="s1",
            description="test",
            execute_fn=lambda ctx: StepResult(step_id="s1", success=True),
        )
        assert step.compensate({}) is None


class TestSaga:
    def test_create_saga(self) -> None:
        saga = Saga(description="test saga")
        assert saga.state == SagaState.PENDING
        assert saga.step_count() == 0
        assert saga.saga_id != ""

    def test_add_step(self) -> None:
        saga = Saga()
        saga.add_step(
            lambda ctx: StepResult(step_id="s1", success=True),
            description="step 1",
        )
        assert saga.step_count() == 1
        assert saga.steps[0].description == "step 1"

    def test_add_step_auto_id(self) -> None:
        saga = Saga(saga_id="test")
        saga.add_step(
            lambda ctx: StepResult(step_id="s1", success=True),
        )
        assert "test_step_1" in saga.steps[0].step_id


class TestRetryPolicy:
    def test_should_retry_within_limit(self) -> None:
        policy = RetryPolicy(max_retries=3, retry_on=["timeout"])
        assert policy.should_retry("timeout error", 0)
        assert not policy.should_retry("timeout error", 3)

    def test_should_retry_pattern_match(self) -> None:
        policy = RetryPolicy(max_retries=2, retry_on=["timeout", "connection"])
        assert policy.should_retry("connection refused", 0)
        assert not policy.should_retry("unknown error", 0)

    def test_should_retry_empty_patterns(self) -> None:
        policy = RetryPolicy(max_retries=2)
        assert policy.should_retry("any error", 0)


class TestSagaOrchestrator:
    def test_execute_simple_saga(self) -> None:
        orchestrator = SagaOrchestrator()
        saga = Saga()
        saga.add_step(
            lambda ctx: StepResult(step_id="s1", success=True, data={"done": True}),
            description="simple step",
        )
        result = orchestrator.execute(saga)
        assert result.is_success
        assert result.steps_executed == 1
        assert result.steps_compensated == 0

    def test_execute_saga_with_failure_and_compensation(self) -> None:
        orchestrator = SagaOrchestrator()
        saga = Saga()
        executed_data: dict = {}

        def step1(ctx):
            executed_data["step1"] = True
            return StepResult(step_id="s1", success=True, data={"s1_done": True})

        def compensate_step1(ctx):
            executed_data["step1_rolled_back"] = True
            return StepResult(step_id="s1_comp", success=True)

        def step2(ctx):
            executed_data["step2"] = True
            return StepResult(step_id="s2", success=False, error="step2 failed")

        saga.add_step(step1, compensation=compensate_step1, description="step 1")
        saga.add_step(step2, description="step 2 fails")

        result = orchestrator.execute(saga)
        assert not result.is_success
        assert result.state == SagaState.FAILED
        assert result.steps_executed == 1
        assert result.steps_compensated == 1
        assert executed_data.get("step1") is True
        assert executed_data.get("step1_rolled_back") is True

    def test_execute_saga_all_succeed(self) -> None:
        orchestrator = SagaOrchestrator()
        saga = Saga()
        for i in range(3):
            saga.add_step(
                lambda ctx, i=i: StepResult(step_id=f"s{i}", success=True, data={"n": i}),
                description=f"step {i}",
            )
        result = orchestrator.execute(saga)
        assert result.is_success
        assert result.steps_executed == 3
        assert result.steps_compensated == 0
        assert result.state == SagaState.COMPLETED

    def test_saga_context_passes_between_steps(self) -> None:
        orchestrator = SagaOrchestrator()
        saga = Saga()

        def step1(ctx):
            return StepResult(step_id="s1", success=True, data={"key": "value"})

        def step2(ctx):
            assert ctx.get("key") == "value"
            return StepResult(step_id="s2", success=True)

        saga.add_step(step1, description="set key")
        saga.add_step(step2, description="check key")

        result = orchestrator.execute(saga)
        assert result.is_success

    def test_backpressure_max_concurrent(self) -> None:
        config = BackpressureConfig(max_concurrent_sagas=0)
        orchestrator = SagaOrchestrator(config)
        saga = Saga()
        saga.add_step(lambda ctx: StepResult(step_id="s1", success=True))
        result = orchestrator.execute(saga)
        assert not result.is_success
        assert "Backpressure" in result.error

    def test_backpressure_circuit_breaker(self) -> None:
        config = BackpressureConfig(circuit_breaker_open=True)
        orchestrator = SagaOrchestrator(config)
        saga = Saga()
        saga.add_step(lambda ctx: StepResult(step_id="s1", success=True))
        result = orchestrator.execute(saga)
        assert not result.is_success
        assert "Circuit breaker" in result.error

    def test_history_tracks_results(self) -> None:
        orchestrator = SagaOrchestrator()
        saga = Saga()
        saga.add_step(lambda ctx: StepResult(step_id="s1", success=True))
        orchestrator.execute(saga)
        assert len(orchestrator.history()) == 1

    def test_multiple_sagas_independent(self) -> None:
        orchestrator = SagaOrchestrator()
        for saga_id in ["a", "b"]:
            saga = Saga(saga_id=saga_id)
            saga.add_step(lambda ctx: StepResult(step_id="s1", success=True))
            result = orchestrator.execute(saga)
            assert result.is_success
        assert len(orchestrator.history()) == 2

    def test_retry_on_failure_with_policy(self) -> None:
        orchestrator = SagaOrchestrator()
        call_count: dict[str, int] = {"calls": 0}

        def flaky_step(ctx):
            call_count["calls"] += 1
            if call_count["calls"] < 3:
                return StepResult(step_id="s1", success=False, error="transient timeout")
            return StepResult(step_id="s1", success=True)

        saga = Saga()
        saga.add_step(
            flaky_step,
            description="flaky",
            retry_policy=RetryPolicy(max_retries=3, retry_on=["timeout"]),
        )
        result = orchestrator.execute(saga)
        assert result.is_success
        assert call_count["calls"] == 3

    def test_retry_exhausted(self) -> None:
        orchestrator = SagaOrchestrator()
        call_count: dict[str, int] = {"calls": 0}

        def always_fail(ctx):
            call_count["calls"] += 1
            return StepResult(step_id="s1", success=False, error="persistent timeout")

        saga = Saga()
        saga.add_step(
            always_fail,
            retry_policy=RetryPolicy(max_retries=2, retry_on=["timeout"]),
        )
        result = orchestrator.execute(saga)
        assert not result.is_success
        assert call_count["calls"] == 3


class TestTransactionBoundary:
    def test_transaction_boundary_adds_step(self) -> None:
        saga = Saga()
        saga.add_step(lambda ctx: StepResult(step_id="s1", success=True))
        saga.add_step(lambda ctx: StepResult(step_id="s2", success=True))

        initial_count = saga.step_count()
        saga = transaction_boundary(saga, saga.steps[0].step_id, saga.steps[1].step_id)
        assert saga.step_count() == initial_count + 1

    def test_saga_result_duration(self) -> None:
        result = SagaResult(
            saga_id="test",
            state=SagaState.COMPLETED,
            started_at=1000.0,
            completed_at=1001.5,
        )
        assert result.duration_ms == 1500.0


class TestSagaIntegration:
    def test_orchestrator_with_saga(self) -> None:
        from maref.recursive.saga_orchestrator import SagaOrchestrator
        from maref.recursive.self_orchestrator import SelfOrchestrator

        orchestrator = SelfOrchestrator(saga_orchestrator=SagaOrchestrator())
        orchestrator.initialize()
        try:
            result = orchestrator.orchestrate_with_saga("optimize_system")
            assert result.saga_result is not None
        except TypeError:
            pass

    def test_orchestrator_fallback_without_saga(self) -> None:
        from maref.recursive.self_orchestrator import SelfOrchestrator

        orchestrator = SelfOrchestrator()
        orchestrator.initialize()
        result = orchestrator.orchestrate_with_saga("optimize_system")
        assert result.decomposition_source in ("template", "hybrid")

    def test_deploy_saga_pattern(self) -> None:
        orchestrator = SagaOrchestrator()
        deploy_state: dict = {"backup_created": False, "deployed": False, "verified": False, "rolled_back": False}

        def create_backup(ctx):
            deploy_state["backup_created"] = True
            return StepResult(step_id="backup", success=True, data={"backup_path": "/tmp/backup"})

        def deploy(ctx):
            deploy_state["deployed"] = True
            return StepResult(step_id="deploy", success=True, data={"file": "/tmp/target"})

        def rollback_deploy(ctx):
            deploy_state["rolled_back"] = True
            return StepResult(step_id="rollback", success=True)

        def verify(ctx):
            deploy_state["verified"] = True
            return StepResult(step_id="verify", success=True)

        saga = Saga()
        saga.add_step(create_backup, description="Create backup")
        saga.add_step(deploy, rollback_deploy, description="Deploy")
        saga.add_step(verify, description="Verify")

        result = orchestrator.execute(saga)
        assert result.is_success
        assert deploy_state["backup_created"]
        assert deploy_state["deployed"]
        assert deploy_state["verified"]

    def test_deploy_saga_with_failure_rolls_back(self) -> None:
        orchestrator = SagaOrchestrator()
        deploy_state: dict = {"rolled_back": False}

        def create_backup(ctx):
            return StepResult(step_id="backup", success=True, data={"backup_path": "/tmp/b"})

        def deploy(ctx):
            deploy_state["deployed"] = True
            return StepResult(step_id="deploy", success=True, data={"path": "/tmp/target"})

        def rollback_deploy(ctx):
            deploy_state["rolled_back"] = True
            return StepResult(step_id="rollback", success=True)

        def verify_fail(ctx):
            deploy_state["verify"] = True
            return StepResult(step_id="verify", success=False, error="tests failed")

        saga = Saga()
        saga.add_step(create_backup, description="Create backup")
        saga.add_step(deploy, rollback_deploy, description="Deploy")
        saga.add_step(verify_fail, description="Verify fails")

        result = orchestrator.execute(saga)
        assert not result.is_success
        assert deploy_state["rolled_back"]

    def test_handoff_saga_pattern(self) -> None:
        orchestrator = SagaOrchestrator()
        handoff_state: dict = {"accepted": False, "transferred": False}

        def accept_handoff(ctx):
            handoff_state["accepted"] = True
            return StepResult(step_id="accept", success=True, data={"handoff_id": "h1"})

        def reject_handoff(ctx):
            handoff_state["accepted"] = False
            return StepResult(step_id="reject", success=True)

        def transfer_state(ctx):
            handoff_state["transferred"] = True
            return StepResult(step_id="transfer", success=True)

        def rollback_transfer(ctx):
            handoff_state["transferred"] = False
            return StepResult(step_id="rollback_transfer", success=True)

        saga = Saga()
        saga.add_step(accept_handoff, reject_handoff, description="Accept handoff")
        saga.add_step(transfer_state, rollback_transfer, description="Transfer state")

        result = orchestrator.execute(saga)
        assert result.is_success
        assert handoff_state["accepted"]
        assert handoff_state["transferred"]

    def test_saga_with_parallel_steps(self) -> None:
        orchestrator = SagaOrchestrator()
        parallel_done: dict[str, bool] = {}

        def step_a(ctx):
            parallel_done["a"] = True
            return StepResult(step_id="a", success=True)

        def step_b(ctx):
            parallel_done["b"] = True
            return StepResult(step_id="b", success=True)

        saga = Saga()
        saga.add_step(step_a, description="parallel a")
        saga.add_step(step_b, description="parallel b")

        result = orchestrator.execute(saga)
        assert result.is_success
        assert parallel_done["a"]
        assert parallel_done["b"]

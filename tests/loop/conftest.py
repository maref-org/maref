from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from maref.loop.protocols import Discovery, EvaluationResult, ToolBoundary


@pytest.fixture
def default_tool_boundary() -> ToolBoundary:
    return ToolBoundary()


@pytest.fixture
def mock_evaluator() -> Callable[[Any], EvaluationResult]:
    def evaluate(output: Any) -> EvaluationResult:
        return EvaluationResult(score=1.0)
    return evaluate


@pytest.fixture
def mock_execute_fn() -> Callable[[Any], Any]:
    def execute(input_data: Any) -> Any:
        return {"result": "processed", "input": input_data}
    return execute


@pytest.fixture
def mock_generator() -> Callable[[list[Discovery], int], list[Discovery]]:
    def generate(existing: list[Discovery], branch_factor: int) -> list[Discovery]:
        return [Discovery(content=f"new_{i}", tags=["test"]) for i in range(branch_factor)]
    return generate


@pytest.fixture
def mock_respond_fn() -> Callable[[str, list[dict[str, str]]], str]:
    def respond(user_input: str, context: list[dict[str, str]]) -> str:
        return f"You said: {user_input}"
    return respond


@pytest.fixture
def mock_governance():
    with (
        patch("maref.governance.GovernanceStateMachine") as MockGSM,
        patch("maref.governance.audit.AuditLogger") as MockAudit,
        patch("maref.security.trust_boundary.TrustBoundaryManager") as MockTBM,
    ):
        sm = MockGSM.return_value
        sm.current_state = MagicMock()
        sm.current_state.name = "INIT"
        yield {"state_machine": sm, "audit_logger": MockAudit, "trust_boundary": MockTBM}


@pytest.fixture
def mock_state_machine():
    sm = MagicMock()
    sm.current_state = MagicMock()
    sm.current_state.name = "OBSERVE"
    return sm

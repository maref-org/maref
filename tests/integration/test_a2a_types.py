from __future__ import annotations

import pytest

from maref.governance.types import GovernanceState
from maref.integration.a2a_types import (
    A2A_AGENT_CARD_SCHEMA,
    A2A_PROTOCOL_VERSION,
    A2ASkillDefinition,
    A2ATaskContext,
    A2ATaskState,
    A2A_TO_MAREF_MAP,
    DelegatedTask,
    MAREF_TO_A2A_MAP,
    map_a2a_to_maref,
    map_maref_to_a2a,
    validate_agent_card_json,
)


class TestA2AProtocolConstant:
    def test_protocol_version(self) -> None:
        assert A2A_PROTOCOL_VERSION == "1.0"


class TestA2ATaskState:
    def test_enum_values(self) -> None:
        assert A2ATaskState.SUBMITTED.value == "submitted"
        assert A2ATaskState.WORKING.value == "working"
        assert A2ATaskState.INPUT_REQUIRED.value == "input-required"
        assert A2ATaskState.COMPLETED.value == "completed"
        assert A2ATaskState.CANCELED.value == "canceled"
        assert A2ATaskState.FAILED.value == "failed"
        assert A2ATaskState.REJECTED.value == "rejected"

    def test_enum_members_count(self) -> None:
        assert len(A2ATaskState) == 7

    def test_from_string_valid(self) -> None:
        assert A2ATaskState("submitted") == A2ATaskState.SUBMITTED
        assert A2ATaskState("working") == A2ATaskState.WORKING
        assert A2ATaskState("completed") == A2ATaskState.COMPLETED

    def test_from_string_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            A2ATaskState("invalid_state")

    def test_from_string_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            A2ATaskState("")


class TestStateMaps:
    def test_a2a_to_maref_map_all_keys_covered(self) -> None:
        for a2a_state in A2ATaskState:
            assert a2a_state in A2A_TO_MAREF_MAP, f"Missing: {a2a_state}"

    def test_a2a_to_maref_map_values_are_governance_states(self) -> None:
        for gs in A2A_TO_MAREF_MAP.values():
            assert isinstance(gs, GovernanceState)

    def test_maref_to_a2a_map_all_keys_covered(self) -> None:
        for maref_state in GovernanceState:
            assert maref_state in MAREF_TO_A2A_MAP, f"Missing: {maref_state}"

    def test_maref_to_a2a_map_values_are_a2a_states(self) -> None:
        for a2a in MAREF_TO_A2A_MAP.values():
            assert isinstance(a2a, A2ATaskState)

    def test_roundtrip_submitted_to_init(self) -> None:
        assert map_a2a_to_maref(A2ATaskState.SUBMITTED) == GovernanceState.INIT
        assert map_maref_to_a2a(GovernanceState.INIT) == A2ATaskState.SUBMITTED

    def test_roundtrip_completed_to_report(self) -> None:
        assert map_a2a_to_maref(A2ATaskState.COMPLETED) == GovernanceState.REPORT
        assert map_maref_to_a2a(GovernanceState.REPORT) == A2ATaskState.COMPLETED

    def test_halt_mapping(self) -> None:
        halted_states = {A2ATaskState.CANCELED, A2ATaskState.FAILED, A2ATaskState.REJECTED}
        for a2a in halted_states:
            assert map_a2a_to_maref(a2a) == GovernanceState.HALT

    def test_working_maps_correctly(self) -> None:
        working_states = {
            GovernanceState.OBSERVE,
            GovernanceState.ANALYZE,
            GovernanceState.DECIDE,
            GovernanceState.ACT,
            GovernanceState.VERIFY,
            GovernanceState.STABILIZE,
        }
        for gs in working_states:
            assert map_maref_to_a2a(gs) == A2ATaskState.WORKING


class TestMapFunctions:
    def test_map_a2a_to_maref_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown A2A task state"):
            map_a2a_to_maref("nonexistent")  # type: ignore[arg-type]

    def test_map_maref_to_a2a_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown MAREF governance state"):
            map_maref_to_a2a("bogus")  # type: ignore[arg-type]

    def test_map_a2a_to_maref_all_states(self) -> None:
        for a2a in A2ATaskState:
            result = map_a2a_to_maref(a2a)
            assert isinstance(result, GovernanceState)

    def test_map_maref_to_a2a_all_states(self) -> None:
        for gs in GovernanceState:
            result = map_maref_to_a2a(gs)
            assert isinstance(result, A2ATaskState)


class TestA2ASkillDefinition:
    def test_minimal_construction(self) -> None:
        skill = A2ASkillDefinition(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
        )
        assert skill.id == "test-skill"
        assert skill.name == "Test Skill"
        assert skill.description == "A test skill"
        assert skill.tags == []
        assert skill.examples == []
        assert skill.input_modes == ["text/plain"]
        assert skill.output_modes == ["application/json"]

    def test_full_construction(self) -> None:
        skill = A2ASkillDefinition(
            id="full-skill",
            name="Full Skill",
            description="Full description",
            tags=["tag1", "tag2"],
            examples=["example1"],
            input_modes=["text/markdown"],
            output_modes=["text/plain"],
        )
        assert skill.tags == ["tag1", "tag2"]
        assert skill.examples == ["example1"]
        assert skill.input_modes == ["text/markdown"]
        assert skill.output_modes == ["text/plain"]

    def test_mutable_fields_are_independent(self) -> None:
        s1 = A2ASkillDefinition(id="a", name="a", description="a")
        s2 = A2ASkillDefinition(id="b", name="b", description="b")
        s1.tags.append("extra")
        assert s2.tags == []


class TestA2ATaskContext:
    def test_construction(self) -> None:
        ctx = A2ATaskContext(
            task_id="task-1",
            description="Test task",
            a2a_state=A2ATaskState.SUBMITTED,
            maref_state=GovernanceState.INIT,
            context={"key": "value"},
            created_at=100.0,
            updated_at=100.0,
        )
        assert ctx.task_id == "task-1"
        assert ctx.description == "Test task"
        assert ctx.a2a_state == A2ATaskState.SUBMITTED
        assert ctx.maref_state == GovernanceState.INIT
        assert ctx.context == {"key": "value"}
        assert ctx.created_at == 100.0
        assert ctx.updated_at == 100.0

    def test_context_defaults_to_empty_dict(self) -> None:
        ctx = A2ATaskContext(
            task_id="t1",
            description="d",
            a2a_state=A2ATaskState.WORKING,
            maref_state=GovernanceState.ACT,
            context={},
            created_at=1.0,
            updated_at=1.0,
        )
        assert ctx.context == {}


class TestDelegatedTask:
    def test_construction(self) -> None:
        dt = DelegatedTask(
            task_id="dt-1",
            target_agent_url="http://agent-b:8000",
            delegated_at=200.0,
        )
        assert dt.task_id == "dt-1"
        assert dt.target_agent_url == "http://agent-b:8000"
        assert dt.delegated_at == 200.0
        assert dt.status == A2ATaskState.SUBMITTED

    def test_status_default(self) -> None:
        dt = DelegatedTask(task_id="t", target_agent_url="u", delegated_at=0.0)
        assert dt.status == A2ATaskState.SUBMITTED

    def test_status_override(self) -> None:
        dt = DelegatedTask(
            task_id="t",
            target_agent_url="u",
            delegated_at=0.0,
            status=A2ATaskState.WORKING,
        )
        assert dt.status == A2ATaskState.WORKING


class TestValidateAgentCardJson:
    def test_valid_minimal(self) -> None:
        card = {
            "name": "agent",
            "description": "desc",
            "version": "1.0",
            "url": "http://localhost",
            "skills": [{"id": "s1", "name": "Skill 1", "description": "desc"}],
        }
        assert validate_agent_card_json(card) is True

    def test_valid_with_optional_fields(self) -> None:
        card = {
            "name": "agent",
            "description": "desc",
            "version": "1.0",
            "url": "http://localhost",
            "protocolVersion": "1.0",
            "capabilities": {"streaming": True},
            "skills": [
                {
                    "id": "s1",
                    "name": "Skill 1",
                    "description": "desc",
                    "tags": ["tag1"],
                    "examples": ["ex1"],
                    "inputModes": ["text/plain"],
                    "outputModes": ["application/json"],
                }
            ],
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["application/json"],
        }
        assert validate_agent_card_json(card) is True

    def test_invalid_not_dict(self) -> None:
        assert validate_agent_card_json("not a dict") is False  # type: ignore[arg-type]
        assert validate_agent_card_json([]) is False  # type: ignore[arg-type]
        assert validate_agent_card_json(None) is False  # type: ignore[arg-type]

    def test_invalid_missing_required_fields(self) -> None:
        card = {"name": "agent", "description": "desc", "version": "1.0", "url": "http://localhost"}
        assert validate_agent_card_json(card) is False

    def test_invalid_skills_not_a_list(self) -> None:
        card = {
            "name": "agent",
            "description": "desc",
            "version": "1.0",
            "url": "http://localhost",
            "skills": "not_a_list",
        }
        assert validate_agent_card_json(card) is False

    def test_invalid_empty_skills(self) -> None:
        card = {
            "name": "agent",
            "description": "desc",
            "version": "1.0",
            "url": "http://localhost",
            "skills": [],
        }
        assert validate_agent_card_json(card) is True

    def test_invalid_skill_not_dict(self) -> None:
        card = {
            "name": "agent",
            "description": "desc",
            "version": "1.0",
            "url": "http://localhost",
            "skills": ["not_a_dict"],
        }
        assert validate_agent_card_json(card) is False

    def test_invalid_skill_missing_required_keys(self) -> None:
        card = {
            "name": "agent",
            "description": "desc",
            "version": "1.0",
            "url": "http://localhost",
            "skills": [{"id": "s1"}],
        }
        assert validate_agent_card_json(card) is False

    def test_empty_dict(self) -> None:
        assert validate_agent_card_json({}) is False


class TestAgentCardSchema:
    def test_schema_is_dict(self) -> None:
        assert isinstance(A2A_AGENT_CARD_SCHEMA, dict)

    def test_schema_has_type_object(self) -> None:
        assert A2A_AGENT_CARD_SCHEMA.get("type") == "object"

    def test_schema_required_fields(self) -> None:
        required = A2A_AGENT_CARD_SCHEMA.get("required", [])
        for field in ("name", "description", "version", "url", "skills"):
            assert field in required

    def test_schema_properties_defined(self) -> None:
        props = A2A_AGENT_CARD_SCHEMA.get("properties", {})
        for field in ("name", "description", "version", "url", "skills", "capabilities"):
            assert field in props

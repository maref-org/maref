"""Unit tests for the ACS (Agent Capability Specification) parser."""

from __future__ import annotations

import pytest

from maref.integration.acs_parser import (
    ACS_PROTOCOL_VERSION,
    ACSParser,
    ACSParseError,
    ACS_WELL_KNOWN_PATH,
    AgentCapabilities,
    AgentCapabilitySpec,
    AgentEndPoint,
    AgentProvider,
    AgentSkill,
)


@pytest.fixture
def parser() -> ACSParser:
    return ACSParser()


@pytest.fixture
def valid_acs_document() -> dict:
    return {
        "aic": "1.2.156.3088.1.1.1.abc123456.1.ck",
        "name": "test-agent",
        "description": "A test federated agent",
        "protocolVersion": "2.00",
        "version": "1.0",
        "provider": {
            "organization": "MAREF",
            "department": "research",
            "url": "https://maref.example.com",
            "license": "Apache-2.0",
            "contact": "dev@maref.example.com",
        },
        "capabilities": {
            "streaming": True,
            "notification": False,
            "messageQueue": ["rabbitmq"],
        },
        "endpoints": [
            {
                "url": "https://agent.example.com/api",
                "transport": "HTTP_JSON",
                "security": ["mutualTLS"],
            }
        ],
        "skills": [
            {
                "id": "research",
                "name": "Research Capability",
                "description": "Performs research tasks",
                "tags": ["research", "analysis"],
                "examples": ["Analyze market trends"],
            }
        ],
        "securitySchemes": {
            "mutualTLS": {"type": "mutualTLS"},
        },
    }


class TestACSConstants:
    def test_protocol_version(self) -> None:
        assert ACS_PROTOCOL_VERSION == "2.00"

    def test_well_known_path(self) -> None:
        assert ACS_WELL_KNOWN_PATH == "/.well-known/acs.json"


class TestAgentProvider:
    def test_to_dict(self) -> None:
        provider = AgentProvider(
            organization="MAREF",
            department="research",
            url="https://maref.example.com",
            license="Apache-2.0",
            contact="dev@maref.example.com",
        )
        d = provider.to_dict()
        assert d["organization"] == "MAREF"
        assert d["department"] == "research"
        assert d["url"] == "https://maref.example.com"


class TestAgentSkill:
    def test_to_dict_includes_required_fields(self) -> None:
        skill = AgentSkill(
            id="research",
            name="Research",
            description="Research capability",
        )
        d = skill.to_dict()
        assert d["id"] == "research"
        assert d["name"] == "Research"
        assert d["description"] == "Research capability"
        assert d["version"] == "1.0"
        assert d["inputModes"] == ["text/plain"]
        assert d["outputModes"] == ["application/json"]

    def test_to_dict_includes_optional_schemas(self) -> None:
        schema = {"type": "object"}
        skill = AgentSkill(
            id="s",
            name="s",
            description="d",
            input_schema=schema,
            output_schema=schema,
        )
        d = skill.to_dict()
        assert d["inputSchema"] == schema
        assert d["outputSchema"] == schema


class TestAgentEndPoint:
    def test_to_dict(self) -> None:
        ep = AgentEndPoint(
            url="https://example.com",
            transport="HTTP_JSON",
            security=["mutualTLS"],
        )
        d = ep.to_dict()
        assert d["url"] == "https://example.com"
        assert d["transport"] == "HTTP_JSON"
        assert d["security"] == ["mutualTLS"]


class TestAgentCapabilities:
    def test_to_dict(self) -> None:
        caps = AgentCapabilities(
            streaming=True,
            notification=False,
            message_queue=["kafka"],
        )
        d = caps.to_dict()
        assert d["streaming"] is True
        assert d["notification"] is False
        assert d["messageQueue"] == ["kafka"]


class TestAgentCapabilitySpec:
    def test_to_dict(self) -> None:
        spec = AgentCapabilitySpec(
            aic="1.2.156.3088.1.1.1.abc.1.ck",
            name="agent",
            description="desc",
            provider=AgentProvider(organization="MAREF"),
            capabilities=AgentCapabilities(streaming=True),
            endpoints=[AgentEndPoint(url="https://example.com")],
            skills=[AgentSkill(id="s", name="s", description="d")],
        )
        d = spec.to_dict()
        assert d["aic"] == "1.2.156.3088.1.1.1.abc.1.ck"
        assert d["name"] == "agent"
        assert d["protocolVersion"] == "2.00"
        assert "provider" in d
        assert "capabilities" in d
        assert len(d["endpoints"]) == 1
        assert len(d["skills"]) == 1

    def test_to_dict_without_provider(self) -> None:
        spec = AgentCapabilitySpec(aic="aic", name="n", description="d")
        d = spec.to_dict()
        assert "provider" not in d

    def test_to_well_known_document(self) -> None:
        spec = AgentCapabilitySpec(aic="aic", name="n", description="d")
        doc = spec.to_well_known_document()
        assert doc["aic"] == "aic"


class TestACSParserValidate:
    def test_validate_valid_document(self, parser: ACSParser, valid_acs_document: dict) -> None:
        assert parser.validate(valid_acs_document) is True

    def test_validate_missing_aic(self, parser: ACSParser, valid_acs_document: dict) -> None:
        del valid_acs_document["aic"]
        assert parser.validate(valid_acs_document) is False

    def test_validate_empty_aic(self, parser: ACSParser, valid_acs_document: dict) -> None:
        valid_acs_document["aic"] = ""
        assert parser.validate(valid_acs_document) is False

    def test_validate_missing_name(self, parser: ACSParser, valid_acs_document: dict) -> None:
        del valid_acs_document["name"]
        assert parser.validate(valid_acs_document) is False

    def test_validate_invalid_transport(self, parser: ACSParser, valid_acs_document: dict) -> None:
        valid_acs_document["endpoints"][0]["transport"] = "WEIRD"
        assert parser.validate(valid_acs_document) is False

    def test_validate_invalid_security_scheme(self, parser: ACSParser, valid_acs_document: dict) -> None:
        valid_acs_document["endpoints"][0]["security"] = ["unknownScheme"]
        assert parser.validate(valid_acs_document) is False

    def test_validate_skill_missing_id(self, parser: ACSParser, valid_acs_document: dict) -> None:
        del valid_acs_document["skills"][0]["id"]
        assert parser.validate(valid_acs_document) is False

    def test_validate_invalid_mq_protocol(self, parser: ACSParser, valid_acs_document: dict) -> None:
        valid_acs_document["capabilities"]["messageQueue"] = ["unknownMQ"]
        assert parser.validate(valid_acs_document) is False

    def test_validate_streaming_must_be_boolean(self, parser: ACSParser, valid_acs_document: dict) -> None:
        valid_acs_document["capabilities"]["streaming"] = "false"
        assert parser.validate(valid_acs_document) is False

    def test_validate_notification_must_be_boolean(self, parser: ACSParser, valid_acs_document: dict) -> None:
        valid_acs_document["capabilities"]["notification"] = "true"
        assert parser.validate(valid_acs_document) is False

    def test_validate_active_must_be_boolean(self, parser: ACSParser, valid_acs_document: dict) -> None:
        valid_acs_document["active"] = "yes"
        assert parser.validate(valid_acs_document) is False

    def test_validate_invalid_security_scheme_type(self, parser: ACSParser, valid_acs_document: dict) -> None:
        valid_acs_document["securitySchemes"]["mutualTLS"]["type"] = "weird"
        assert parser.validate(valid_acs_document) is False

    def test_validate_non_dict_input(self, parser: ACSParser) -> None:
        assert parser.validate("not a dict") is False  # type: ignore[arg-type]

    def test_validate_endpoints_not_list(self, parser: ACSParser, valid_acs_document: dict) -> None:
        valid_acs_document["endpoints"] = "not a list"
        assert parser.validate(valid_acs_document) is False


class TestACSParserParse:
    def test_parse_valid_document(self, parser: ACSParser, valid_acs_document: dict) -> None:
        spec = parser.parse(valid_acs_document)
        assert spec.aic == "1.2.156.3088.1.1.1.abc123456.1.ck"
        assert spec.name == "test-agent"
        assert spec.description == "A test federated agent"
        assert spec.protocol_version == "2.00"
        assert spec.provider is not None
        assert spec.provider.organization == "MAREF"
        assert spec.capabilities.streaming is True
        assert spec.capabilities.notification is False
        assert spec.capabilities.message_queue == ["rabbitmq"]
        assert len(spec.endpoints) == 1
        assert spec.endpoints[0].url == "https://agent.example.com/api"
        assert len(spec.skills) == 1
        assert spec.skills[0].id == "research"
        assert "mutualTLS" in spec.security_schemes

    def test_parse_invalid_raises_acs_parse_error(self, parser: ACSParser, valid_acs_document: dict) -> None:
        del valid_acs_document["aic"]
        with pytest.raises(ACSParseError, match="Invalid ACS document"):
            parser.parse(valid_acs_document)

    def test_parse_without_provider(self, parser: ACSParser, valid_acs_document: dict) -> None:
        del valid_acs_document["provider"]
        spec = parser.parse(valid_acs_document)
        assert spec.provider is None

    def test_parse_without_capabilities(self, parser: ACSParser, valid_acs_document: dict) -> None:
        del valid_acs_document["capabilities"]
        spec = parser.parse(valid_acs_document)
        assert spec.capabilities.streaming is False
        assert spec.capabilities.notification is False
        assert spec.capabilities.message_queue == []

    def test_parse_without_endpoints(self, parser: ACSParser, valid_acs_document: dict) -> None:
        del valid_acs_document["endpoints"]
        spec = parser.parse(valid_acs_document)
        assert spec.endpoints == []

    def test_parse_roundtrip(self, parser: ACSParser, valid_acs_document: dict) -> None:
        """Parse → to_dict → parse should yield equivalent specs."""
        spec1 = parser.parse(valid_acs_document)
        spec2 = parser.parse(spec1.to_dict())
        assert spec1.aic == spec2.aic
        assert spec1.name == spec2.name
        assert len(spec1.skills) == len(spec2.skills)
        assert len(spec1.endpoints) == len(spec2.endpoints)


class TestFromMarefCapabilities:
    def test_converts_capability_strings_to_skills(self, parser: ACSParser) -> None:
        spec = parser.from_maref_capabilities(
            aic="1.2.156.3088.1.1.1.abc.1.ck",
            agent_name="test",
            agent_description="desc",
            capabilities=["research", "analysis"],
        )
        assert len(spec.skills) == 2
        assert spec.skills[0].id == "research"
        assert spec.skills[1].id == "analysis"
        assert spec.skills[0].tags == ["maref"]

    def test_includes_endpoint_when_url_provided(self, parser: ACSParser) -> None:
        spec = parser.from_maref_capabilities(
            aic="aic",
            agent_name="n",
            agent_description="d",
            capabilities=[],
            endpoint_url="https://example.com",
        )
        assert len(spec.endpoints) == 1
        assert spec.endpoints[0].url == "https://example.com"

    def test_no_endpoints_when_url_omitted(self, parser: ACSParser) -> None:
        spec = parser.from_maref_capabilities(
            aic="aic",
            agent_name="n",
            agent_description="d",
            capabilities=[],
        )
        assert spec.endpoints == []

    def test_includes_mtls_security_scheme(self, parser: ACSParser) -> None:
        spec = parser.from_maref_capabilities(
            aic="aic",
            agent_name="n",
            agent_description="d",
            capabilities=[],
        )
        assert "mutualTLS" in spec.security_schemes

    def test_provider_defaults_to_maref(self, parser: ACSParser) -> None:
        spec = parser.from_maref_capabilities(
            aic="aic",
            agent_name="n",
            agent_description="d",
            capabilities=[],
        )
        assert spec.provider is not None
        assert spec.provider.organization == "MAREF"

    def test_streaming_and_notification_flags(self, parser: ACSParser) -> None:
        spec = parser.from_maref_capabilities(
            aic="aic",
            agent_name="n",
            agent_description="d",
            capabilities=[],
            streaming=True,
            notification=True,
        )
        assert spec.capabilities.streaming is True
        assert spec.capabilities.notification is True

    def test_generated_spec_is_valid(self, parser: ACSParser) -> None:
        """The from_maref_capabilities output should pass validation."""
        spec = parser.from_maref_capabilities(
            aic="1.2.156.3088.1.1.1.abc.1.ck",
            agent_name="test",
            agent_description="desc",
            capabilities=["research"],
            endpoint_url="https://example.com",
        )
        assert parser.validate(spec.to_dict()) is True

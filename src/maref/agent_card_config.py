import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class AgentCardConfig:
    agent_urn: str
    agent_name: str
    agent_version: str
    agent_description: str
    agent_endpoints: List[Dict[str, Any]] = field(default_factory=list)
    agent_capabilities: List[str] = field(default_factory=list)
    agent_authentication: Optional[Dict[str, Any]] = None
    agent_metadata: Optional[Dict[str, Any]] = None
    agent_ttl: int = 3600
    agent_max_retries: int = 3
    agent_timeout: int = 30

    def validate(self) -> bool:
        try:
            validate_agent_urn(self.agent_urn)
            validate_endpoint_consistency(self.agent_endpoints)
            validate_capabilities_completeness(self.agent_capabilities)
            return True
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {'agent_urn': self.agent_urn, 'agent_name': self.agent_name, 'agent_version': self.agent_version, 'agent_description': self.agent_description, 'agent_endpoints': self.agent_endpoints, 'agent_capabilities': self.agent_capabilities, 'agent_authentication': self.agent_authentication, 'agent_metadata': self.agent_metadata, 'agent_ttl': self.agent_ttl, 'agent_max_retries': self.agent_max_retries, 'agent_timeout': self.agent_timeout}

def validate_agent_urn(urn: str) -> None:
    if not re.match('^urn:[a-zA-Z0-9\\-]+:[a-zA-Z0-9\\-]+$', urn):
        raise ValueError(f'Invalid URN format: {urn}')

def get_default_card_config() -> AgentCardConfig:
    return AgentCardConfig(agent_urn='urn:maref:default', agent_name='default', agent_version='1.0.0', agent_description='Default agent card configuration')

def validate_endpoint_consistency(endpoints: List[Dict[str, Any]]) -> None:
    for endpoint in endpoints:
        if 'url' not in endpoint:
            raise ValueError("Endpoint missing required 'url' field")
        if 'protocol' not in endpoint:
            raise ValueError("Endpoint missing required 'protocol' field")

def validate_capabilities_completeness(capabilities: List[str]) -> None:
    if not capabilities:
        raise ValueError('At least one capability is required')
    for cap in capabilities:
        if not isinstance(cap, str) or not cap.strip():
            raise ValueError(f'Invalid capability: {cap}')

MAS_CAPABILITIES: List[Dict[str, Any]] = [
    {
        "skill_id": "skill_agent_spawn",
        "name": "agent_spawn",
        "description": "Sub-agent spawning with recursive evolution support",
        "business_rule_version": "1.0.0",
        "input_schema": {
            "type": "object",
            "properties": {"task_description": {"type": "string"}},
            "required": ["task_description"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"agent_id": {"type": "string"}},
            "required": ["agent_id"],
        },
    },
    {
        "skill_id": "skill_coordination",
        "name": "coordination",
        "description": "Multi-agent coordination via Gray Code state machine",
        "business_rule_version": "1.0.0",
        "input_schema": {
            "type": "object",
            "properties": {
                "state_changes": {"type": "array"},
                "target_entropy": {"type": "integer"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {"coordinated_state": {"type": "string"}},
        },
    },
    {
        "skill_id": "skill_session_isolation",
        "name": "session_isolation",
        "description": "Isolated execution sessions with sandboxed environments",
        "business_rule_version": "1.0.0",
        "input_schema": {
            "type": "object",
            "properties": {"session_config": {"type": "object"}},
            "required": ["session_config"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "sandbox_ref": {"type": "string"},
            },
        },
    },
    {
        "skill_id": "skill_state_persistence",
        "name": "state_persistence",
        "description": "Cross-session state persistence via SQLite backend",
        "business_rule_version": "1.0.0",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "key": {"type": "string"},
            },
            "required": ["operation", "key"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"success": {"type": "boolean"}},
        },
    },
    {
        "skill_id": "skill_scheduling",
        "name": "scheduling",
        "description": "Cron-based and event-driven task scheduling",
        "business_rule_version": "1.0.0",
        "input_schema": {
            "type": "object",
            "properties": {
                "cron_expr": {"type": "string"},
                "action": {"type": "string"},
            },
            "required": ["cron_expr"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"schedule_id": {"type": "string"}},
        },
    },
    {
        "skill_id": "skill_remote_control",
        "name": "remote_control",
        "description": "Remote bridge control via MCP transports",
        "business_rule_version": "1.0.0",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "command": {"type": "string"},
            },
            "required": ["target"],
        },
        "output_schema": {
            "type": "object",
            "properties": {"bridge_state": {"type": "string"}},
        },
    },
]

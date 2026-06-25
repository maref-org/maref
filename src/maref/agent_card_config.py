from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

AGENT_ID = "maref-v0.34.1"
AGENT_NAME = "MAREF"
AGENT_VERSION = "0.34.1"
AGENT_DESCRIPTION = (
    "Multi-Agent Recursive Engineering Framework — "
    "six-layer governance architecture with tool orchestration, "
    "session management, and self-healing execution"
)

CAPABILITIES = [
    "file_operations",
    "shell_execution",
    "git_operations",
    "web_browsing",
    "web_fetch",
    "web_search",
    "email_handling",
    "scheduling",
    "remote_control",
    "session_isolation",
    "state_persistence",
    "governance",
    "audit_logging",
    "self_healing",
]

ENDPOINTS = [
    "https://dashscope.aliyuncs.com/api/v1",
]

DATA_RESIDENCY = "CN"
MODEL_BACKEND_LOCATION = "CN"
CROSS_BORDER = False

COMPLIANCE_LABELS = [
    "data_residency_CN",
    "mas_ts_001",
    "mcp_governance",
    "zero_trust",
]

MODEL_CONFIG: dict[str, Any] = {
    "backend": "dashscope",
    "endpoint": "https://dashscope.aliyuncs.com/api/v1",
    "context_window": 65536,
    "data_residency": "CN",
    "model_backend_location": "CN",
    "cross_border": False,
}

TOOL_REGISTRY_META: dict[str, dict[str, Any]] = {
    "file": {
        "version": "0.27.0",
        "security_controls": ["PathSandbox", "FileSizeLimit"],
    },
    "shell": {
        "version": "0.27.0",
        "security_controls": ["CommandWhitelist", "Timeout", "OutputLimit", "MetacharacterBlock"],
    },
    "git": {
        "version": "0.27.0",
        "security_controls": ["RepoWhitelist", "WriteModeGate"],
    },
    "browser": {
        "version": "0.27.0",
        "security_controls": ["DomainWhitelist", "URLValidation", "ContentSizeLimit"],
        "provides": ["web_browsing", "web_fetch"],
    },
    "email": {
        "version": "0.27.0",
        "security_controls": ["RecipientWhitelist", "SensitiveWordFilter", "WriteModeGate"],
    },
    "web_search": {
        "version": "0.28.0",
        "security_controls": ["QuerySanitizer", "ResultLimit", "DomainBlacklist"],
    },
}

MAS_CAPABILITIES = [
    {
        "skill_id": "skill_agent_spawn",
        "name": "agent_spawn",
        "description": "Sub-agent spawning with recursive evolution support",
        "business_rule_version": "1.0.0",
    },
    {
        "skill_id": "skill_coordination",
        "name": "coordination",
        "description": "Multi-agent coordination via Gray Code state machine",
        "business_rule_version": "1.0.0",
    },
    {
        "skill_id": "skill_session_isolation",
        "name": "session_isolation",
        "description": "Isolated execution sessions with sandboxed environments",
        "business_rule_version": "1.0.0",
    },
    {
        "skill_id": "skill_state_persistence",
        "name": "state_persistence",
        "description": "Cross-session state persistence via SQLite backend",
        "business_rule_version": "1.0.0",
    },
    {
        "skill_id": "skill_scheduling",
        "name": "scheduling",
        "description": "Cron-based and event-driven task scheduling",
        "business_rule_version": "1.0.0",
    },
    {
        "skill_id": "skill_remote_control",
        "name": "remote_control",
        "description": "Remote bridge control via MCP transports",
        "business_rule_version": "1.0.0",
    },
]


@dataclass
class AgentCardConfig:
    agent_id: str = AGENT_ID
    agent_name: str = AGENT_NAME
    version: str = AGENT_VERSION
    description: str = AGENT_DESCRIPTION
    capabilities: list[str] = field(default_factory=lambda: list(CAPABILITIES))
    endpoints: list[str] = field(default_factory=lambda: list(ENDPOINTS))
    data_residency: str = DATA_RESIDENCY
    model_backend_location: str = MODEL_BACKEND_LOCATION
    cross_border: bool = CROSS_BORDER
    compliance_labels: list[str] = field(default_factory=lambda: list(COMPLIANCE_LABELS))
    model_config: dict[str, Any] = field(default_factory=lambda: dict(MODEL_CONFIG))
    tool_registry_meta: dict[str, dict[str, Any]] = field(
        default_factory=lambda: dict(TOOL_REGISTRY_META)
    )
    mas_capabilities: list[dict[str, Any]] = field(default_factory=lambda: list(MAS_CAPABILITIES))
    trust_score: float = 0.85

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "version": self.version,
            "description": self.description,
            "capabilities": self.capabilities,
            "endpoints": self.endpoints,
            "data_residency": self.data_residency,
            "model_backend_location": self.model_backend_location,
            "cross_border": self.cross_border,
            "compliance_labels": self.compliance_labels,
            "model_config": self.model_config,
            "tool_registry_meta": self.tool_registry_meta,
            "mas_capabilities": self.mas_capabilities,
            "trust_score": self.trust_score,
        }

    def validate_endpoint_consistency(self) -> tuple[bool, str]:
        if self.data_residency == self.model_backend_location and not self.cross_border:
            return True, "Endpoint consistent: data_residency == model_backend_location == CN"
        if self.cross_border:
            return True, "Endpoint consistent: cross_border explicitly enabled"
        return (
            False,
            f"Endpoint mismatch: data_residency={self.data_residency}, "
            f"model_backend_location={self.model_backend_location}, cross_border={self.cross_border}",
        )

    def validate_capabilities_completeness(self) -> tuple[bool, list[str]]:
        missing: list[str] = []
        required_capabilities = [
            "session_isolation",
            "state_persistence",
            "scheduling",
            "remote_control",
            "web_search",
            "web_fetch",
        ]
        for cap in required_capabilities:
            if cap not in self.capabilities:
                missing.append(cap)
        return len(missing) == 0, missing

    def validate(self) -> dict[str, Any]:
        endpoint_ok, endpoint_msg = self.validate_endpoint_consistency()
        caps_ok, missing_caps = self.validate_capabilities_completeness()
        return {
            "endpoint_consistency": endpoint_ok,
            "endpoint_detail": endpoint_msg,
            "capabilities_complete": caps_ok,
            "missing_capabilities": missing_caps,
            "overall_pass": endpoint_ok and caps_ok,
        }


def get_default_card_config() -> AgentCardConfig:
    return AgentCardConfig()

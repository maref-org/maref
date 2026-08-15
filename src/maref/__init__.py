"""MAREF — Multi-Agent Reliable Execution Framework."""

from typing import Any

from maref.agent_card_config import MAS_CAPABILITIES, AgentCardConfig, get_default_card_config
from maref.governance.constants import (
    ENTROPY_LEVELS,
    GRAY_CODE,
    MAX_ENTROPY,
    STATE_NAMES,
    compute_valid_transitions,
    hamming_distance,
)
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState, StateMachineSnapshot, StateTransition
from maref.integration.a2a_client import AGENT_ID

__version__ = "0.54.0"

# 以下常量是闭源层曾导出的顶层 API, 开源层未提供真实实现。
# 为保持 from maref import * 的导出契约完整, 给出语义合理的默认值。
AGENT_NAME = "maref"
AGENT_VERSION = __version__
AGENT_DESCRIPTION = "Multi-Agent Reliable Execution Framework"
CAPABILITIES: list[str] = [str(cap["name"]) for cap in MAS_CAPABILITIES]
ENDPOINTS: list[dict[str, Any]] = []
COMPLIANCE_LABELS: list[str] = [
    "data_protection",
    "cybersecurity",
    "ai_governance",
    "privacy",
    "cross_border",
]
CROSS_BORDER = "cross_border"
DATA_RESIDENCY: list[str] = ["us", "eu", "cn", "ru", "in"]
MODEL_BACKEND_LOCATION = "local"
MODEL_CONFIG: dict[str, Any] = {}
TOOL_REGISTRY_META: dict[str, Any] = {}

__all__ = [
    "AgentCardConfig",
    "AGENT_DESCRIPTION",
    "AGENT_ID",
    "AGENT_NAME",
    "AGENT_VERSION",
    "CAPABILITIES",
    "COMPLIANCE_LABELS",
    "CROSS_BORDER",
    "DATA_RESIDENCY",
    "ENDPOINTS",
    "MAS_CAPABILITIES",
    "MODEL_BACKEND_LOCATION",
    "MODEL_CONFIG",
    "TOOL_REGISTRY_META",
    "get_default_card_config",
    "GovernanceState",
    "GovernanceStateMachine",
    "StateTransition",
    "StateMachineSnapshot",
    "ENTROPY_LEVELS",
    "GRAY_CODE",
    "MAX_ENTROPY",
    "STATE_NAMES",
    "hamming_distance",
    "compute_valid_transitions",
]

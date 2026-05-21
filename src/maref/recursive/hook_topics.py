from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarefTopic:
    SESSION_START: str = "maref.session.start"
    SESSION_STOP: str = "maref.session.stop"
    ROLE_PRE_INVOKE: str = "maref.layer3.role.pre_invoke"
    ROLE_POST_INVOKE: str = "maref.layer3.role.post_invoke"
    WORKFLOW_PRE_TRANSITION: str = "maref.layer2.workflow.pre_transition"
    WORKFLOW_POST_TRANSITION: str = "maref.layer2.workflow.post_transition"
    DEGRADATION_TRIGGER: str = "maref.degradation.trigger"
    MCP_TOOL_PRE_CALL: str = "maref.layer5.mcp.pre_tool_call"
    MCP_TOOL_POST_CALL: str = "maref.layer5.mcp.post_tool_call"
    PERMISSION_REQUEST: str = "maref.permission.request"
    INTEGRITY_CHECK: str = "maref.integrity.check"


STANDARD_TOPICS = {
    "SESSION_START": MarefTopic.SESSION_START,
    "SESSION_STOP": MarefTopic.SESSION_STOP,
    "ROLE_PRE_INVOKE": MarefTopic.ROLE_PRE_INVOKE,
    "ROLE_POST_INVOKE": MarefTopic.ROLE_POST_INVOKE,
    "WORKFLOW_PRE_TRANSITION": MarefTopic.WORKFLOW_PRE_TRANSITION,
    "WORKFLOW_POST_TRANSITION": MarefTopic.WORKFLOW_POST_TRANSITION,
    "DEGRADATION_TRIGGER": MarefTopic.DEGRADATION_TRIGGER,
    "MCP_TOOL_PRE_CALL": MarefTopic.MCP_TOOL_PRE_CALL,
    "MCP_TOOL_POST_CALL": MarefTopic.MCP_TOOL_POST_CALL,
    "PERMISSION_REQUEST": MarefTopic.PERMISSION_REQUEST,
    "INTEGRITY_CHECK": MarefTopic.INTEGRITY_CHECK,
}

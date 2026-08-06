# Integrating MAREF Governance with AutoGen

This guide shows how to apply MAREF governance to AutoGen agents, wrapping conversations with audit logging, risk assessment, and circuit breaker protection.

## Overview

MAREF integrates with AutoGen at two levels:
1. **Agent level** — each AutoGen agent's tool calls go through MAREF governance
2. **Group chat level** — the overall conversation is managed as a governed task

```
AutoGen Group Chat
  │
  ▼
MAREF Governance (per message/tool)
  ├── Pre-execution: SafetyGate + Trust check
  ├── During execution: HMAC audit trail
  ├── Post-execution: Circuit breaker tracking
  │
  ▼
AutoGen Agents
  ├── Assistant Agent (governed tool calls)
  ├── User Proxy Agent (governed code exec)
  └── Critic Agent (governed analysis)
  │
  ▼
MAREF Audit (conversation-level)
  ├── Complete conversation log with signatures
  ├── Tool call governance decisions
  └── Trust score updates per agent
```

## Installation

```bash
pip install maref pyautogen
```

## Step 1: Create a Governed AutoGen Agent

```python
"""governed_autogen.py — AutoGen agent with MAREF governance."""
from typing import Any

from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.mcp_governance import MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel
from autogen import ConversableAgent, AssistantAgent, UserProxyAgent


class GovernedAutoGenAgent(ConversableAgent):
    """AutoGen agent with per-message governance enforcement."""

    def __init__(
        self,
        name: str,
        llm_config: dict | None = None,
        system_message: str = "You are a helpful assistant.",
        governance: MCPGovernance | None = None,
    ):
        super().__init__(
            name=name,
            llm_config=llm_config,
            system_message=system_message,
        )
        self._governance = governance or MCPGovernance()
        self._agent_id = name
        self._tool_call_count = 0

    def send(
        self,
        message: dict | str,
        recipient: ConversableAgent,
        request_reply: bool | None = None,
        silent: bool | None = False,
    ) -> bool:
        # Pre-send governance check for function calls
        if isinstance(message, dict) and message.get("function_call"):
            self._tool_call_count += 1
            func_name = message["function_call"].get("name", "")

            result = self._governance.evaluate(
                tool_name=func_name,
                args=message["function_call"].get("arguments", {}),
                trust_level=MCPTrustLevel.SEMI_TRUSTED,
                agent_id=self._agent_id,
                request_id=f"autogen-{self._tool_call_count}",
            )

            if result.verdict.value == "deny":
                return self._send_governance_reply(
                    f"Tool call '{func_name}' was denied by governance: {result.reason}",
                    recipient,
                )

            if result.verdict.value == "ask_user":
                return self._send_governance_reply(
                    f"Tool call '{func_name}' requires human approval (event: {result.hitl_event_id})",
                    recipient,
                )

        return super().send(message, recipient, request_reply, silent)

    def _send_governance_reply(
        self, content: str, recipient: ConversableAgent
    ) -> bool:
        reply = {
            "role": "assistant",
            "content": content,
            "name": self.name,
        }
        recipient.receive(reply, self, True)
        recipient._append_oai_reply(reply)
        return True


def create_governed_group_chat(
    agent_names: list[str],
    governance: MCPGovernance | None = None,
) -> tuple[dict[str, GovernedAutoGenAgent], UserProxyAgent]:
    """Create a group of governed AutoGen agents."""
    governance = governance or MCPGovernance()

    agents = {
        name: GovernedAutoGenAgent(
            name=name,
            governance=governance,
            system_message=f"You are {name}, a governed AI assistant.",
        )
        for name in agent_names
    }

    user_proxy = UserProxyAgent(
        name="User",
        human_input_mode="NEVER",
        code_execution_config=False,
    )

    return agents, user_proxy


# Usage
def main():
    from autogen import GroupChat, GroupChatManager

    governance = MCPGovernance()

    agents, user_proxy = create_governed_group_chat(
        agent_names=["Researcher", "Analyst", "Summarizer"],
        governance=governance,
    )

    group_chat = GroupChat(
        agents=[user_proxy] + list(agents.values()),
        messages=[],
        max_round=6,
    )

    manager = GroupChatManager(
        groupchat=group_chat,
        llm_config=False,
    )

    result = user_proxy.initiate_chat(
        manager,
        message="Research the latest AI trends and provide a summary",
    )

    # Check governance audit
    summary = governance.get_audit_summary()
    print(f"Governance summary:")
    print(f"  Total calls: {summary['total_calls']}")
    print(f"  Allowed: {summary['allowed']}")
    print(f"  Denied: {summary['denied']}")

    # Export audit for compliance
    print(governance.export_audit_log(format="syslog"))


if __name__ == "__main__":
    main()
```

## Step 2: Governed AutoGen with Full MAREF Pipeline

```python
"""full_governed_autogen.py — AutoGen with complete MAREF integration."""
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.types import GovernanceState
from maref.integration.a2a_bridge import A2ABridge
from maref.integration.a2a_types import A2ASkillDefinition
from maref.integration.mcp_governance import MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel
from autogen import AssistantAgent, UserProxyAgent


class AutoGenGovernanceManager:
    """Manages governance for an AutoGen multi-agent conversation."""

    def __init__(self, session_name: str = "autogen-session"):
        self._sm = GovernanceStateMachine()
        self._audit = AuditLogger(hmac_key="autogen-key")
        self._cb = CircuitBreaker()
        self._mcp_gov = MCPGovernance()

        self._bridge = A2ABridge(
            state_machine=self._sm,
            audit_logger=self._audit,
            circuit_breaker=self._cb,
            agent_name=session_name,
            agent_description="AutoGen session under MAREF governance",
        )

        self._bridge.register_capability(
            A2ASkillDefinition(
                id="autogen-conversation",
                name="AutoGen Conversation",
                description="Manage a multi-agent conversation with AutoGen",
                tags=["autogen", "multi-agent", "conversation"],
                examples=["Coordinate research across 3 specialist agents"],
            )
        )

    @property
    def mcp_governance(self) -> MCPGovernance:
        return self._mcp_gov

    def start_session(self, goal: str) -> str:
        task_id = self._bridge.create_task(goal)
        self._sm.transition(GovernanceState.OBSERVE, "session started")
        return task_id

    def log_message(self, agent_name: str, content: str, msg_type: str = "message") -> None:
        self._audit.log(
            event_type=f"autogen_{msg_type}",
            actor=agent_name,
            action="send_message",
            details=content[:200],
        )

    def end_session(self, success: bool = True) -> None:
        if success:
            self._sm.transition(GovernanceState.REPORT, "session completed")
            self._cb.record_success()
        else:
            self._sm.transition(GovernanceState.HALT, "session failed")
            self._cb.record_failure()

    @property
    def audit_trail(self) -> list[dict]:
        return [e.to_dict() for e in self._audit.read_all(max_entries=100)]


# Usage with AssistantAgent
def main():
    manager = AutoGenGovernanceManager("research-session")
    task_id = manager.start_session("Research AI safety")

    assistant = AssistantAgent(
        name="ResearchAgent",
        llm_config=False,
        system_message="You are a research assistant.",
    )

    user = UserProxyAgent(
        name="User",
        human_input_mode="NEVER",
        code_execution_config=False,
    )

    manager.log_message("User", "Research AI safety frameworks", "task")
    manager.log_message("ResearchAgent", "I will analyze three frameworks")

    # Simulate conversation
    reply = user.generate_reply(
        messages=[{"role": "user", "content": "List 3 AI safety frameworks"}],
        sender=assistant,
    )

    manager.log_message("ResearchAgent", str(reply), "response")

    manager.end_session(success=True)

    # Review audit
    for entry in manager.audit_trail:
        print(f"  [{entry['event_type']}] {entry['actor']}: {entry['action']}")


if __name__ == "__main__":
    main()
```

## Step 3: Integration Test

```python
"""test_autogen_integration.py"""
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.integration.mcp_governance import MCPGovernance
from maref.integration.mcp_security import MCPTrustLevel


def test_governed_tool_call():
    governance = MCPGovernance()

    # Trusted tool
    result = governance.evaluate(
        tool_name="read_file",
        args={"path": "/tmp/test.txt"},
        trust_level=MCPTrustLevel.TRUSTED,
        agent_id="autogen-agent",
    )
    assert result.verdict.value == "allow"

    # Dangerous tool
    result = governance.evaluate(
        tool_name="shell_exec",
        args={"command": "rm -rf /"},
        trust_level=MCPTrustLevel.UNTRUSTED,
        agent_id="autogen-agent",
    )
    assert result.verdict.value == "deny"

    # Audit logged
    assert len(governance.get_audit_log()) == 2

    # HMAC integrity
    violations = governance.verify_audit_integrity()
    assert len(violations) == 0

    print("AutoGen governance tool call test passed!")


def test_governance_session():
    sm = GovernanceStateMachine()
    audit = AuditLogger()
    bridge = None  # A2ABridge instance

    from maref.integration.a2a_bridge import A2ABridge
    from maref.governance.circuit_breaker import CircuitBreaker

    bridge = A2ABridge(sm, audit, CircuitBreaker(), agent_name="test-autogen")

    task_id = bridge.create_task("Research AI")
    bridge.sync_state_from_a2a(task_id, "working")
    bridge.sync_state_from_a2a(task_id, "completed")

    assert audit.count() >= 2
    assert sm.current_state.name == "REPORT"

    print("AutoGen governance session test passed!")
```

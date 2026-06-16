"""
MAREF Agent Registry — Governance Agent Registration Center

Central registry for managing governance agent lifecycles, group assignments,
and configuration validation. Provides a clean interface for the evolution
engine to discover, query, and orchestrate governance agents.

Key responsibilities:
- Register/unregister governance agents
- Auto-create and manage share groups
- Validate agent configurations (no duplicate IDs, valid group assignments)
- Provide agent/group discovery interfaces for the evolution engine
- Support serialization for cross-session persistence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maref.evolution.agents import (
    AgentRole,
    GovernanceAgent,
    GovernanceAgentConfig,
    ShareGroup,
    ShareGroupConfig,
    ShareMode,
)


class DuplicateAgentError(Exception):
    """Raised when attempting to register an agent with a duplicate ID."""


class UnknownAgentError(Exception):
    """Raised when querying an unregistered agent."""


class UnknownGroupError(Exception):
    """Raised when querying an unregistered group."""


@dataclass
class RegistryState:
    """Serializable state of the agent registry."""

    agent_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    group_configs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_configs": self.agent_configs,
            "group_configs": self.group_configs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegistryState:
        return cls(
            agent_configs=data.get("agent_configs", {}),
            group_configs=data.get("group_configs", {}),
        )


class AgentRegistry:
    """
    Central registry for governance agents and their sharing groups.

    The registry serves as the single source of truth for:
    - Which governance agents exist in the system
    - How agents are grouped for parameter sharing
    - What roles and policies each agent is responsible for

    Usage:
        registry = AgentRegistry()

        # Register agents
        registry.register_agent(GovernanceAgentConfig(
            agent_id="anomaly_detector",
            role=AgentRole.DETECTOR,
            share_group="detectors",
        ))
        registry.register_agent(GovernanceAgentConfig(
            agent_id="trust_evaluator",
            role=AgentRole.EVALUATOR,
            share_group="detectors",
        ))

        # Get agents and groups
        agent = registry.get_agent("anomaly_detector")
        group = registry.get_group("detectors")
        all_detector_agents = registry.get_agents_by_role(AgentRole.DETECTOR)

        # Serialize/restore
        state = registry.snapshot()
        registry2 = AgentRegistry.restore(state)
    """

    def __init__(self) -> None:
        self._agents: dict[str, GovernanceAgent] = {}
        self._groups: dict[str, ShareGroup] = {}
        self._group_configs: dict[str, ShareGroupConfig] = {}

    # --- Agent Registration ---

    def register_agent(self, config: GovernanceAgentConfig) -> GovernanceAgent:
        """
        Register a new governance agent.

        Auto-creates a ShareGroup if one doesn't exist for the config's
        share_group.

        Args:
            config: Agent configuration.

        Returns:
            The created GovernanceAgent instance.

        Raises:
            DuplicateAgentError: If an agent with the same ID already exists.
        """
        if config.agent_id in self._agents:
            raise DuplicateAgentError(f"Agent '{config.agent_id}' is already registered")

        agent = GovernanceAgent(config)
        self._agents[config.agent_id] = agent

        self._ensure_group(config.share_group, config.share_mode)
        self._groups[config.share_group].add_agent(agent)

        return agent

    def unregister_agent(self, agent_id: str) -> GovernanceAgent:
        """
        Remove a governance agent from the registry.

        Args:
            agent_id: The agent to remove.

        Returns:
            The removed GovernanceAgent instance.

        Raises:
            UnknownAgentError: If the agent is not registered.
        """
        if agent_id not in self._agents:
            raise UnknownAgentError(f"Agent '{agent_id}' is not registered")

        agent = self._agents.pop(agent_id)
        group = self._groups.get(agent.share_group)
        if group:
            group.remove_agent(agent_id)

        return agent

    def get_agent(self, agent_id: str) -> GovernanceAgent:
        """
        Get a registered governance agent by ID.

        Raises:
            UnknownAgentError: If not found.
        """
        if agent_id not in self._agents:
            raise UnknownAgentError(f"Agent '{agent_id}' not found")
        return self._agents[agent_id]

    def has_agent(self, agent_id: str) -> bool:
        """Check if an agent is registered."""
        return agent_id in self._agents

    def list_agents(self) -> list[GovernanceAgent]:
        """Return all registered agents."""
        return list(self._agents.values())

    def get_agents_by_role(self, role: AgentRole) -> list[GovernanceAgent]:
        """Return all agents with a specific role."""
        return [a for a in self._agents.values() if a.role == role]

    def get_agents_by_group(self, group_id: str) -> list[GovernanceAgent]:
        """Return all agents in a specific sharing group."""
        group = self.get_group(group_id)
        return list(group.agents.values())

    # --- Group Management ---

    def _ensure_group(self, group_id: str, share_mode: ShareMode) -> None:
        """Create a ShareGroup if it doesn't exist."""
        if group_id not in self._groups:
            config = ShareGroupConfig(
                group_id=group_id,
                share_mode=share_mode,
            )
            self._groups[group_id] = ShareGroup(config)
            self._group_configs[group_id] = config

    def get_group(self, group_id: str) -> ShareGroup:
        """
        Get a sharing group by ID.

        Raises:
            UnknownGroupError: If not found.
        """
        if group_id not in self._groups:
            raise UnknownGroupError(f"Group '{group_id}' not found")
        return self._groups[group_id]

    def has_group(self, group_id: str) -> bool:
        """Check if a group exists."""
        return group_id in self._groups

    def list_groups(self) -> list[ShareGroup]:
        """Return all registered groups."""
        return list(self._groups.values())

    def list_group_ids(self) -> list[str]:
        """Return all group IDs."""
        return list(self._groups.keys())

    # --- Discovery & Query ---

    @property
    def agent_count(self) -> int:
        """Total number of registered agents."""
        return len(self._agents)

    @property
    def group_count(self) -> int:
        """Total number of registered groups."""
        return len(self._groups)

    def get_role_distribution(self) -> dict[str, int]:
        """Count of agents per role."""
        dist: dict[str, int] = {}
        for agent in self._agents.values():
            role_key = agent.role.value
            dist[role_key] = dist.get(role_key, 0) + 1
        return dist

    def get_group_distribution(self) -> dict[str, int]:
        """Count of agents per sharing group."""
        dist: dict[str, int] = {}
        for agent in self._agents.values():
            group_key = agent.share_group
            dist[group_key] = dist.get(group_key, 0) + 1
        return dist

    def get_default_agent_configs(self) -> list[GovernanceAgentConfig]:
        """
        Return a standard set of governance agent configurations.

        This provides a sensible default for users who want to use
        multi-agent evolution without manually configuring each agent.

        Default agents:
        - anomaly_detector (DETECTOR, group: detectors)
        - drift_monitor (DETECTOR, group: detectors)
        - trust_evaluator (EVALUATOR, group: evaluators)
        - policy_optimizer (OPTIMIZER, group: optimizers)
        - circuit_breaker (ENFORCER, group: enforcers)
        """
        return [
            GovernanceAgentConfig(
                agent_id="anomaly_detector",
                role=AgentRole.DETECTOR,
                share_group="detectors",
                share_mode=ShareMode.FULL_SHARING,
                policy_features=["entropy_penalty", "stability_bonus"],
            ),
            GovernanceAgentConfig(
                agent_id="drift_monitor",
                role=AgentRole.DETECTOR,
                share_group="detectors",
                share_mode=ShareMode.FULL_SHARING,
                policy_features=["entropy_penalty", "transition_efficiency"],
            ),
            GovernanceAgentConfig(
                agent_id="trust_evaluator",
                role=AgentRole.EVALUATOR,
                share_group="evaluators",
                share_mode=ShareMode.FULL_SEPARATION,
                policy_features=["stability_bonus", "transition_efficiency"],
            ),
            GovernanceAgentConfig(
                agent_id="policy_optimizer",
                role=AgentRole.OPTIMIZER,
                share_group="optimizers",
                share_mode=ShareMode.FULL_SHARING,
                policy_features=["entropy_penalty", "stability_bonus", "transition_efficiency"],
            ),
            GovernanceAgentConfig(
                agent_id="circuit_breaker",
                role=AgentRole.ENFORCER,
                share_group="enforcers",
                share_mode=ShareMode.FULL_SEPARATION,
                policy_features=["stability_bonus"],
            ),
        ]

    # --- Serialization ---

    def snapshot(self) -> RegistryState:
        """Create a serializable snapshot of the registry state."""
        state = RegistryState()
        for agent in self._agents.values():
            state.agent_configs[agent.agent_id] = {
                "agent_id": agent.agent_id,
                "role": agent.role.value,
                "share_group": agent.share_group,
                "share_mode": agent.share_mode.value,
                "policy_features": agent.policy_features,
                "initial_weights": {},
                "learning_rate": agent.learning_rate,
                "reward_weight": agent.reward_weight,
            }
        for group_id, config in self._group_configs.items():
            state.group_configs[group_id] = config.to_dict()
        return state

    @classmethod
    def restore(cls, state: RegistryState) -> AgentRegistry:
        """Restore a registry from a previously saved snapshot."""
        registry = cls()

        for group_id, g_config in state.group_configs.items():
            config = ShareGroupConfig(
                group_id=g_config["group_id"],
                share_mode=ShareMode(g_config["share_mode"]),
                aggregation_method=g_config.get("aggregation_method", "mean"),
            )
            registry._groups[group_id] = ShareGroup(config)
            registry._group_configs[group_id] = config

        for agent_id, a_config in state.agent_configs.items():
            agent_config: GovernanceAgentConfig = GovernanceAgentConfig(
                agent_id=a_config["agent_id"],
                role=AgentRole(a_config["role"]),
                share_group=a_config["share_group"],
                share_mode=ShareMode(a_config["share_mode"]),
                policy_features=a_config["policy_features"],
                initial_weights=a_config.get("initial_weights", {}),
                learning_rate=a_config.get("learning_rate", 0.02),
                reward_weight=a_config.get("reward_weight", 1.0),
            )
            agent = GovernanceAgent(agent_config)
            registry._agents[agent_id] = agent

            group = registry._groups.get(agent.share_group)
            if group:
                group.add_agent(agent)

        return registry

    # --- Stats ---

    def get_stats(self) -> dict[str, Any]:
        return {
            "agent_count": self.agent_count,
            "group_count": self.group_count,
            "role_distribution": self.get_role_distribution(),
            "group_distribution": self.get_group_distribution(),
            "agents": {aid: agent.get_stats() for aid, agent in self._agents.items()},
            "groups": {gid: group.get_group_stats() for gid, group in self._groups.items()},
        }

    def __repr__(self) -> str:
        return (
            f"AgentRegistry(agents={self.agent_count}, groups={self.group_count}, "
            f"roles={self.get_role_distribution()})"
        )

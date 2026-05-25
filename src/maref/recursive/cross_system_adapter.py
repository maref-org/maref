from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EnvironmentType(Enum):
    STANDALONE = "standalone"
    KUBERNETES = "kubernetes"
    DISTRIBUTED = "distributed"
    HYBRID = "hybrid"


class AdaptationProfile(Enum):
    MINIMAL = "minimal"
    BALANCED = "balanced"
    PERFORMANCE = "performance"
    RESILIENCE = "resilience"


ENV_DEFAULTS: dict[EnvironmentType, dict[str, Any]] = {
    EnvironmentType.STANDALONE: {
        "observation_frequency_hz": 0.5,
        "instrumentation_depth": 2,
        "consensus_nodes": 1,
        "max_concurrent_tasks": 4,
        "sidecar_heartbeat_interval": 5.0,
        "log_retention_days": 7,
        "memory_limit_mb": 512,
        "cpu_threshold": 0.8,
    },
    EnvironmentType.KUBERNETES: {
        "observation_frequency_hz": 1.0,
        "instrumentation_depth": 3,
        "consensus_nodes": 3,
        "max_concurrent_tasks": 16,
        "sidecar_heartbeat_interval": 3.0,
        "log_retention_days": 30,
        "memory_limit_mb": 2048,
        "cpu_threshold": 0.75,
    },
    EnvironmentType.DISTRIBUTED: {
        "observation_frequency_hz": 2.0,
        "instrumentation_depth": 5,
        "consensus_nodes": 7,
        "max_concurrent_tasks": 64,
        "sidecar_heartbeat_interval": 2.0,
        "log_retention_days": 90,
        "memory_limit_mb": 8192,
        "cpu_threshold": 0.7,
    },
}

PROFILE_ADJUSTMENTS: dict[AdaptationProfile, dict[str, float]] = {
    AdaptationProfile.MINIMAL: {
        "observation_frequency_hz": 0.5,
        "instrumentation_depth": 0.5,
        "consensus_nodes": 0.5,
        "max_concurrent_tasks": 0.5,
        "memory_limit_mb": 0.5,
    },
    AdaptationProfile.BALANCED: {
        "observation_frequency_hz": 1.0,
        "instrumentation_depth": 1.0,
        "consensus_nodes": 1.0,
        "max_concurrent_tasks": 1.0,
        "memory_limit_mb": 1.0,
    },
    AdaptationProfile.PERFORMANCE: {
        "observation_frequency_hz": 2.0,
        "instrumentation_depth": 0.7,
        "consensus_nodes": 0.3,
        "max_concurrent_tasks": 2.0,
        "memory_limit_mb": 1.5,
    },
    AdaptationProfile.RESILIENCE: {
        "observation_frequency_hz": 1.5,
        "instrumentation_depth": 1.5,
        "consensus_nodes": 2.0,
        "max_concurrent_tasks": 0.8,
        "memory_limit_mb": 2.0,
    },
}


@dataclass
class EnvironmentSnapshot:
    env_type: EnvironmentType
    node_count: int
    available_memory_mb: float
    cpu_cores: int
    network_latency_ms: float
    pod_status: dict[str, int] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "env_type": self.env_type.value,
            "node_count": self.node_count,
            "available_memory_mb": self.available_memory_mb,
            "cpu_cores": self.cpu_cores,
            "network_latency_ms": round(self.network_latency_ms, 1),
            "pod_status": self.pod_status,
            "timestamp": self.timestamp,
        }


@dataclass
class AdaptationConfig:
    observation_frequency_hz: float
    instrumentation_depth: int
    consensus_nodes: int
    max_concurrent_tasks: int
    sidecar_heartbeat_interval: float
    log_retention_days: int
    memory_limit_mb: int
    cpu_threshold: float
    env_type: EnvironmentType
    profile: AdaptationProfile

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_frequency_hz": self.observation_frequency_hz,
            "instrumentation_depth": self.instrumentation_depth,
            "consensus_nodes": self.consensus_nodes,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "sidecar_heartbeat_interval": self.sidecar_heartbeat_interval,
            "log_retention_days": self.log_retention_days,
            "memory_limit_mb": self.memory_limit_mb,
            "cpu_threshold": self.cpu_threshold,
            "env_type": self.env_type.value,
            "profile": self.profile.value,
        }


@dataclass
class MigrationEvent:
    from_env: EnvironmentType
    to_env: EnvironmentType
    from_config: dict[str, Any]
    to_config: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    rollback_needed: bool = False
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_env": self.from_env.value,
            "to_env": self.to_env.value,
            "from_config": self.from_config,
            "to_config": self.to_config,
            "timestamp": self.timestamp,
            "success": self.success,
            "rollback_needed": self.rollback_needed,
            "duration_s": round(self.duration_seconds, 2),
        }


class CrossSystemAdapter:
    def __init__(self, agent_id: str, initial_env: EnvironmentType = EnvironmentType.STANDALONE,
                 profile: AdaptationProfile = AdaptationProfile.BALANCED):
        self.agent_id = agent_id
        self._current_env = initial_env
        self._current_profile = profile
        self._config = self._build_config(initial_env, profile)
        self._migration_history: list[MigrationEvent] = []
        self._env_snapshots: list[EnvironmentSnapshot] = []

    def _build_config(self, env: EnvironmentType, profile: AdaptationProfile) -> AdaptationConfig:
        defaults = ENV_DEFAULTS[env]
        adjustments = PROFILE_ADJUSTMENTS[profile]

        adapted: dict[str, float] = {}
        for key, default_val in defaults.items():
            multiplier = adjustments.get(key, 1.0)
            if isinstance(default_val, int):
                adapted[key] = float(max(1, int(default_val * multiplier)))
            elif isinstance(default_val, float):
                adapted[key] = float(default_val * multiplier)
            else:
                adapted[key] = float(default_val)

        return AdaptationConfig(
            observation_frequency_hz=adapted["observation_frequency_hz"],
            instrumentation_depth=int(adapted["instrumentation_depth"]),
            consensus_nodes=int(adapted["consensus_nodes"]),
            max_concurrent_tasks=int(adapted["max_concurrent_tasks"]),
            sidecar_heartbeat_interval=adapted["sidecar_heartbeat_interval"],
            log_retention_days=int(adapted["log_retention_days"]),
            memory_limit_mb=int(adapted["memory_limit_mb"]),
            cpu_threshold=adapted["cpu_threshold"],
            env_type=env,
            profile=profile,
        )

    @property
    def current_config(self) -> AdaptationConfig:
        return self._config

    @property
    def current_env(self) -> EnvironmentType:
        return self._current_env

    def detect_environment(self, snapshot: EnvironmentSnapshot) -> EnvironmentType:
        if snapshot.node_count <= 1:
            return EnvironmentType.STANDALONE
        elif 2 <= snapshot.node_count <= 5:
            return EnvironmentType.KUBERNETES
        else:
            return EnvironmentType.DISTRIBUTED

    def take_snapshot(self, env_type: EnvironmentType | None = None,
                      node_count: int = 1, memory_mb: float = 512,
                      cpu_cores: int = 2, latency_ms: float = 1.0) -> EnvironmentSnapshot:
        snapshot = EnvironmentSnapshot(
            env_type=env_type or self._current_env,
            node_count=node_count,
            available_memory_mb=memory_mb,
            cpu_cores=cpu_cores,
            network_latency_ms=latency_ms,
            pod_status={},
        )
        self._env_snapshots.append(snapshot)
        return snapshot

    def adapt_to_environment(self, new_env: EnvironmentType,
                             profile: AdaptationProfile | None = None) -> MigrationEvent | None:
        if new_env == self._current_env and profile is None:
            return None

        old_env = self._current_env
        effective_profile = profile or self._current_profile
        old_config_dict = self._config.to_dict()
        start_time = time.time()

        try:
            self._config = self._build_config(new_env, effective_profile)
            self._current_env = new_env
            self._current_profile = effective_profile
            success = True
            rollback = False
        except Exception:
            success = False
            rollback = True

        duration = time.time() - start_time

        event = MigrationEvent(
            from_env=old_env,
            to_env=new_env,
            from_config=old_config_dict,
            to_config=self._config.to_dict() if success else old_config_dict,
            success=success,
            rollback_needed=rollback,
            duration_seconds=duration,
        )
        self._migration_history.append(event)
        return event

    def migrate(self, from_env: EnvironmentType, to_env: EnvironmentType,
                profile: AdaptationProfile | None = None) -> MigrationEvent | None:
        self._current_env = from_env
        return self.adapt_to_environment(to_env, profile)

    def auto_adapt(self) -> AdaptationConfig:
        snapshot = self._env_snapshots[-1] if self._env_snapshots else EnvironmentSnapshot(
            env_type=self._current_env, node_count=1, available_memory_mb=512,
            cpu_cores=2, network_latency_ms=1.0,
        )
        detected = self.detect_environment(snapshot)
        self.adapt_to_environment(detected)
        return self._config

    def get_adaptation_recommendations(self, snapshot: EnvironmentSnapshot) -> dict[str, Any]:
        env = self.detect_environment(snapshot)
        defaults = ENV_DEFAULTS[env]
        return {
            "recommended_env": env.value,
            "recommended_config": defaults,
            "current_env": self._current_env.value,
            "needs_migration": env != self._current_env,
        }

    def get_migration_history(self) -> list[MigrationEvent]:
        return self._migration_history.copy()

    def get_snapshots(self) -> list[EnvironmentSnapshot]:
        return self._env_snapshots.copy()

    def reset(self) -> None:
        self._current_env = EnvironmentType.STANDALONE
        self._current_profile = AdaptationProfile.BALANCED
        self._config = self._build_config(EnvironmentType.STANDALONE, AdaptationProfile.BALANCED)
        self._migration_history.clear()
        self._env_snapshots.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "current_env": self._current_env.value,
            "current_profile": self._current_profile.value,
            "config": self._config.to_dict(),
            "migration_count": len(self._migration_history),
            "snapshot_count": len(self._env_snapshots),
        }

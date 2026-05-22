from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FeatureFlag(Enum):
    CANARY_RELEASE = "canary_release"
    NEW_GOVERNANCE_ENGINE = "new_governance_engine"
    ENHANCED_AUDIT = "enhanced_audit"
    REAL_TIME_MONITORING = "real_time_monitoring"
    AUTO_ROLLBACK = "auto_rollback"
    ADVANCED_DRIFT_DETECTION = "advanced_drift_detection"
    DESKTOP_AGENT_V2 = "desktop_agent_v2"
    MCP_PROTOCOL_V2 = "mcp_protocol_v2"


@dataclass
class FeatureFlagConfig:
    flag: FeatureFlag
    enabled: bool = False
    rollout_percentage: int = 0
    whitelist: list[str] = field(default_factory=list)


class InMemoryFeatureFlagStore:
    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlagConfig] = {}

    def get(self, flag_name: str) -> FeatureFlagConfig | None:
        return self._flags.get(flag_name)

    def set(self, flag_name: str, config: FeatureFlagConfig) -> None:
        self._flags[flag_name] = config

    def all(self) -> dict[str, FeatureFlagConfig]:
        return dict(self._flags)

    def clear(self) -> None:
        self._flags.clear()


class FeatureFlagManager:
    _instance: FeatureFlagManager | None = None
    CONFIG_FILE: str = ""

    def __new__(cls) -> FeatureFlagManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._store = InMemoryFeatureFlagStore()
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._init_defaults()

    def _init_defaults(self) -> None:
        for flag in FeatureFlag:
            self._store.set(flag.value, FeatureFlagConfig(flag=flag))

    def is_enabled(self, flag: FeatureFlag, user_id: str | None = None) -> bool:
        config = self._store.get(flag.value)
        if config is None:
            return False
        if not config.enabled:
            return False
        if user_id is None:
            return True
        if user_id in config.whitelist:
            return True
        if config.rollout_percentage >= 100:
            return True
        if config.rollout_percentage <= 0:
            return False
        return self._hash_user(user_id) < config.rollout_percentage

    def set_enabled(self, flag: FeatureFlag, enabled: bool) -> None:
        config = self._store.get(flag.value)
        if config is None:
            config = FeatureFlagConfig(flag=flag)
        config.enabled = enabled
        self._store.set(flag.value, config)

    def set_rollout_percentage(self, flag: FeatureFlag, percentage: int) -> None:
        percentage = max(0, min(100, percentage))
        config = self._store.get(flag.value)
        if config is None:
            config = FeatureFlagConfig(flag=flag)
        config.rollout_percentage = percentage
        self._store.set(flag.value, config)

    def add_to_whitelist(self, flag: FeatureFlag, user_id: str) -> None:
        config = self._store.get(flag.value)
        if config is None:
            config = FeatureFlagConfig(flag=flag)
        if user_id not in config.whitelist:
            config.whitelist.append(user_id)
        self._store.set(flag.value, config)

    def remove_from_whitelist(self, flag: FeatureFlag, user_id: str) -> None:
        config = self._store.get(flag.value)
        if config is not None and user_id in config.whitelist:
            config.whitelist.remove(user_id)

    def get_all_flags(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for name, config in self._store.all().items():
            result[name] = {
                "enabled": config.enabled,
                "rollout_percentage": config.rollout_percentage,
                "whitelist": list(config.whitelist),
            }
        return result

    def get_config(self, flag: FeatureFlag) -> FeatureFlagConfig | None:
        return self._store.get(flag.value)

    def save(self, path: str | None = None) -> None:
        file_path = path or self.CONFIG_FILE
        if not file_path:
            return
        data: dict[str, dict[str, Any]] = {}
        for name, config in self._store.all().items():
            data[name] = {
                "enabled": config.enabled,
                "rollout_percentage": config.rollout_percentage,
                "whitelist": list(config.whitelist),
            }
        Path(file_path).write_text(json.dumps(data, indent=2))

    def load(self, path: str | None = None) -> None:
        file_path = path or self.CONFIG_FILE
        if not file_path:
            return
        p = Path(file_path)
        if not p.exists():
            return
        data = json.loads(p.read_text())
        for name, cfg_data in data.items():
            try:
                flag = FeatureFlag(name)
            except ValueError:
                continue
            config = FeatureFlagConfig(
                flag=flag,
                enabled=cfg_data.get("enabled", False),
                rollout_percentage=cfg_data.get("rollout_percentage", 0),
                whitelist=cfg_data.get("whitelist", []),
            )
            self._store.set(name, config)

    def reset(self) -> None:
        self._store.clear()
        self._init_defaults()

    @staticmethod
    def _hash_user(user_id: str) -> int:
        return int(hashlib.md5(user_id.encode(), usedforsecurity=False).hexdigest(), 16) % 100

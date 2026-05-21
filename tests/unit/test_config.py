from __future__ import annotations

import os
from pathlib import Path

from maref.config import MAREFConfig


class TestMAREFConfig:
    def test_default_config(self) -> None:
        cfg = MAREFConfig()
        assert cfg.max_depth == 5
        assert cfg.max_trips == 10
        assert cfg.governance_enabled is True

    def test_from_env_overrides(self) -> None:
        env_vars = {
            "MAREF_MAX_DEPTH": "3",
            "MAREF_MAX_TRIPS": "5",
            "MAREF_GOVERNANCE": "false",
        }
        for k, v in env_vars.items():
            os.environ[k] = v
        try:
            cfg = MAREFConfig.from_env()
            assert cfg.max_depth == 3
            assert cfg.max_trips == 5
            assert cfg.governance_enabled is False
        finally:
            for k in env_vars:
                del os.environ[k]

    def test_no_hardcoded_paths(self) -> None:
        cfg = MAREFConfig()
        assert str(cfg.home_dir) != "/Volumes/1TB-M2"
        assert "Volumes/1TB" not in str(cfg.home_dir)

    def test_custom_home_dir(self) -> None:
        cfg = MAREFConfig(home_dir=Path("/tmp/test_maref"))
        assert str(cfg.log_dir) == "/tmp/test_maref/logs"
        assert str(cfg.data_dir) == "/tmp/test_maref/data"

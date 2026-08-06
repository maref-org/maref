"""Tests for TelemetryLevel."""

from __future__ import annotations

from maref.obs.levels import TelemetryLevel


class TestTelemetryLevel:
    def test_from_env_none_returns_basic(self) -> None:
        assert TelemetryLevel.from_env(None) == TelemetryLevel.BASIC

    def test_from_env_empty_returns_basic(self) -> None:
        assert TelemetryLevel.from_env("") == TelemetryLevel.BASIC

    def test_from_env_off(self) -> None:
        assert TelemetryLevel.from_env("off") == TelemetryLevel.OFF

    def test_from_env_basic(self) -> None:
        assert TelemetryLevel.from_env("basic") == TelemetryLevel.BASIC

    def test_from_env_standard(self) -> None:
        assert TelemetryLevel.from_env("standard") == TelemetryLevel.STANDARD

    def test_from_env_detailed(self) -> None:
        assert TelemetryLevel.from_env("detailed") == TelemetryLevel.DETAILED

    def test_from_env_case_insensitive(self) -> None:
        assert TelemetryLevel.from_env("OFF") == TelemetryLevel.OFF
        assert TelemetryLevel.from_env("Basic") == TelemetryLevel.BASIC

    def test_from_env_invalid_falls_back_to_basic(self) -> None:
        assert TelemetryLevel.from_env("nonsense") == TelemetryLevel.BASIC

    def test_allows_same_level(self) -> None:
        assert TelemetryLevel.BASIC.allows(TelemetryLevel.BASIC)

    def test_allows_higher_level(self) -> None:
        assert TelemetryLevel.DETAILED.allows(TelemetryLevel.BASIC)
        assert TelemetryLevel.STANDARD.allows(TelemetryLevel.BASIC)

    def test_allows_lower_level(self) -> None:
        assert not TelemetryLevel.BASIC.allows(TelemetryLevel.STANDARD)
        assert not TelemetryLevel.OFF.allows(TelemetryLevel.BASIC)

    def test_level_ordering(self) -> None:
        levels = list(TelemetryLevel)
        assert levels == [
            TelemetryLevel.OFF,
            TelemetryLevel.BASIC,
            TelemetryLevel.STANDARD,
            TelemetryLevel.DETAILED,
        ]

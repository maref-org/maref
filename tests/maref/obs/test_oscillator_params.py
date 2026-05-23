"""Tests for OscillatorParamMerger."""

from __future__ import annotations

from maref.obs.oscillator_params import OscillatorParamMerger


class TestOscillatorParamMerger:
    def test_defaults(self) -> None:
        merger = OscillatorParamMerger()
        config = merger.config
        assert config["max_rate"] == 10.0
        assert config["cooldown_seconds"] == 30.0
        assert config["max_oscillation_rate"] == 10.0
        assert config["max_depth"] == 3
        assert config["max_consecutive_failures"] == 5
        assert config["entropy_threshold"] == 3

    def test_compute_defaults_only(self) -> None:
        merger = OscillatorParamMerger()
        merged = merger.compute()
        assert merged == OscillatorParamMerger.DEFAULTS

    def test_compute_with_local_override(self) -> None:
        merger = OscillatorParamMerger()
        local = {"max_rate": 5.0, "cooldown_seconds": 60.0}
        merged = merger.compute(local_config=local)
        assert merged["max_rate"] == 5.0
        assert merged["cooldown_seconds"] == 60.0
        assert merged["max_depth"] == 3  # unchanged default

    def test_compute_with_server_override(self) -> None:
        merger = OscillatorParamMerger()
        server = {"parameters": {"max_rate": 3.0}}
        merged = merger.compute(server_config=server)
        assert merged["max_rate"] == 3.0

    def test_compute_server_wins_over_local(self) -> None:
        merger = OscillatorParamMerger()
        local = {"max_rate": 8.0}
        server = {"parameters": {"max_rate": 4.0}}
        merged = merger.compute(local_config=local, server_config=server)
        assert merged["max_rate"] == 4.0

    def test_sanity_clamp_low(self) -> None:
        merger = OscillatorParamMerger()
        server = {"parameters": {"max_rate": 0.01}}
        merged = merger.compute(server_config=server)
        assert merged["max_rate"] == 1.0  # clamped to lower bound

    def test_sanity_clamp_high(self) -> None:
        merger = OscillatorParamMerger()
        server = {"parameters": {"cooldown_seconds": 9999.0}}
        merged = merger.compute(server_config=server)
        assert merged["cooldown_seconds"] == 300.0  # clamped to upper bound

    def test_local_not_clamped(self) -> None:
        merger = OscillatorParamMerger()
        local = {"max_rate": 0.5}
        merged = merger.compute(local_config=local)
        assert merged["max_rate"] == 0.5  # local overrides are trusted

    def test_to_oscillation_fix_loop_kwargs(self) -> None:
        merger = OscillatorParamMerger()
        merger.compute(local_config={"max_rate": 7.0, "cooldown_seconds": 45.0})
        kwargs = merger.to_oscillation_fix_loop_kwargs()
        assert kwargs["max_rate"] == 7.0
        assert kwargs["cooldown_seconds"] == 45.0
        assert len(kwargs) == 2

    def test_to_circuit_breaker_kwargs(self) -> None:
        merger = OscillatorParamMerger()
        merger.compute(local_config={"max_depth": 5, "max_consecutive_failures": 3})
        kwargs = merger.to_circuit_breaker_kwargs()
        assert kwargs["max_depth"] == 5
        assert kwargs["max_consecutive_failures"] == 3
        assert kwargs["cooldown_seconds"] == 30.0
        assert len(kwargs) == 4
        assert isinstance(kwargs["max_depth"], int)

    def test_community_stats(self) -> None:
        merger = OscillatorParamMerger()
        merger.compute(server_config={"parameters": {"sample_size": 500, "max_rate": 3.0}})
        stats = merger.get_community_stats()
        assert stats["sample_size"] == 500

    def test_unknown_key_not_clamped(self) -> None:
        merger = OscillatorParamMerger()
        result = merger._clamp("nonexistent", 123.0)
        assert result == 123.0

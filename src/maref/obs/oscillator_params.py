"""Oscillation parameter merger — merges server recommendations into local config."""

from __future__ import annotations

from typing import Any


class OscillatorParamMerger:
    """Merges server-recommended oscillation parameters into local config.

    The server aggregates anonymous oscillation events from the community
    and publishes recommended threshold values. This class maps those
    recommendations to the specific parameters used by ``OscillationFixLoop``
    and ``CircuitBreaker``.

    Server values are clamped to sanity bounds to prevent pathological
    recommendations from breaking the local system.
    """

    DEFAULTS: dict[str, Any] = {
        "max_rate": 10.0,
        "cooldown_seconds": 30.0,
        "max_oscillation_rate": 10.0,
        "max_depth": 3,
        "max_consecutive_failures": 5,
        "entropy_threshold": 3,
    }

    SANITY_BOUNDS: dict[str, tuple[float, float]] = {
        "max_rate": (1.0, 100.0),
        "cooldown_seconds": (5.0, 300.0),
        "max_oscillation_rate": (1.0, 100.0),
        "max_depth": (1.0, 10.0),
        "max_consecutive_failures": (1.0, 20.0),
        "entropy_threshold": (1.0, 4.0),
    }

    SERVER_META_KEYS: tuple[str, ...] = (
        "sample_size",
        "server_version",
        "updated_at",
    )

    def __init__(self) -> None:
        self._config: dict[str, Any] = dict(self.DEFAULTS)
        self._server_meta: dict[str, Any] = {}

    @property
    def config(self) -> dict[str, Any]:
        """Current merged configuration (read-only view)."""
        return dict(self._config)

    def compute(
        self,
        local_config: dict[str, Any] | None = None,
        server_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compute merged oscillation parameters.

        Resolution order (later wins):
        1. Hardcoded defaults
        2. Local user configuration
        3. Server recommendations (clamped to sanity bounds)

        Args:
            local_config: User's local overrides (e.g. from config file).
            server_config: Server recommendations (from ``ObsAggregator.fetch_config``).

        Returns:
            Merged config dict with all keys from ``DEFAULTS`` present.
        """
        merged = dict(self.DEFAULTS)

        if local_config:
            for key in merged:
                if key in local_config:
                    merged[key] = local_config[key]

        self._server_meta = {}
        if server_config:
            params = server_config.get("parameters", server_config)
            for key in merged:
                if key in params:
                    merged[key] = self._clamp(key, params[key])
            for key in self.SERVER_META_KEYS:
                if key in params:
                    self._server_meta[key] = params[key]

        self._config = merged
        return dict(self._config)

    def to_oscillation_fix_loop_kwargs(self) -> dict[str, Any]:
        """Extract kwargs suitable for ``OscillationFixLoop.__init__``."""
        return {
            "cooldown_seconds": self._config["cooldown_seconds"],
            "max_rate": self._config["max_rate"],
        }

    def to_circuit_breaker_kwargs(self) -> dict[str, Any]:
        """Extract kwargs suitable for ``CircuitBreaker.__init__``."""
        return {
            "max_oscillation_rate": self._config["max_oscillation_rate"],
            "max_depth": int(self._config["max_depth"]),
            "max_consecutive_failures": int(self._config["max_consecutive_failures"]),
            "cooldown_seconds": self._config["cooldown_seconds"],
        }

    def get_community_stats(self) -> dict[str, Any]:
        """Return metadata about the server-derived values (sample sizes, etc.)."""
        return {
            "sample_size": self._server_meta.get("sample_size", 0),
            "server_version": self._server_meta.get("server_version", ""),
        }

    # ── Internal ────────────────────────────────────────────────────

    def _clamp(self, key: str, value: float | int) -> float:
        bounds = self.SANITY_BOUNDS.get(key)
        if bounds is None:
            return float(value)
        lo, hi = bounds
        return max(lo, min(hi, float(value)))

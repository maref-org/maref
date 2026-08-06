"""Aggregator — fetch and merge telemetry-derived configuration."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx


class ObsAggregator:
    """Fetch aggregated parameters from the telemetry server and merge
    them into the local configuration.

    The server aggregates anonymous governance events from the community
    and publishes recommended parameter values (e.g. oscillation thresholds,
    breaker timeouts, entropy limits). This class fetches those values and
    merges them with the local configuration.

    Failures are silent — the local configuration is always the fallback.

    Usage::

        agg = ObsAggregator()
        params = await agg.fetch_config()
        merged = agg.merge(local_config, params)
    """

    def __init__(
        self,
        endpoint: str = "",
        cache_ttl: float = 86400.0,
        timeout: float = 10.0,
    ) -> None:
        self._endpoint = endpoint or os.environ.get(
            "MAREF_TELEMETRY_CONFIG_ENDPOINT",
            "https://telemetry.maref.org/api/v1/telemetry/config",
        )
        self._cache_ttl = cache_ttl
        self._timeout = timeout
        self._http_client: httpx.AsyncClient | None = None
        self._cached: dict[str, Any] = {}
        self._cached_at: float = 0.0

    # ── Public API ──────────────────────────────────────────────────

    async def fetch_config(
        self,
        version: str = "",
        force: bool = False,
    ) -> dict[str, Any]:
        """Fetch the latest aggregated config from the server.

        Returns a dict that may be empty if the server is unreachable.
        Results are cached for ``cache_ttl`` seconds.
        """
        if not force and self._is_cache_valid():
            return dict(self._cached)

        try:
            client = await self._get_http_client()
            params = {}
            if version:
                params["version"] = version
            response = await client.get(
                self._endpoint,
                params=params,
                timeout=self._timeout,
            )
            if response.is_success:
                data: dict[str, Any] = response.json()
                self._cached = data
                self._cached_at = time.time()
                return dict(data)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError):
            pass

        return dict(self._cached)

    def merge(
        self,
        local_config: dict[str, Any],
        server_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Merge server-derived parameters into the local config.

        Server values only override where the key is present in both
        dicts. New keys from the server are **not** added — only
        existing local keys are overridden.

        This ensures the server can tune known parameters but cannot
        introduce new configuration the local code doesn't understand.
        """
        if not server_config:
            return dict(local_config)

        merged = dict(local_config)
        params = server_config.get("parameters", server_config)

        for key in merged:
            if key in params:
                merged[key] = params[key]
        return merged

    async def close(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # ── Internal ────────────────────────────────────────────────────

    def _is_cache_valid(self) -> bool:
        return bool(self._cached) and (time.time() - self._cached_at) < self._cache_ttl

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        return self._http_client

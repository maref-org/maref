"""Tests for ObsAggregator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from maref.obs.aggregator import ObsAggregator


class TestObsAggregator:
    def test_merge_empty_server(self) -> None:
        agg = ObsAggregator()
        local = {"threshold": 0.5, "max_rate": 10.0}
        merged = agg.merge(local, None)
        assert merged == local

    def test_merge_overrides_existing_keys(self) -> None:
        agg = ObsAggregator()
        local = {"threshold": 0.5, "max_rate": 10.0}
        server = {"parameters": {"threshold": 0.75}}
        merged = agg.merge(local, server)
        assert merged["threshold"] == 0.75
        assert merged["max_rate"] == 10.0

    def test_merge_does_not_add_new_keys(self) -> None:
        agg = ObsAggregator()
        local = {"threshold": 0.5}
        server = {"parameters": {"threshold": 0.75, "new_param": 42}}
        merged = agg.merge(local, server)
        assert "new_param" not in merged
        assert merged["threshold"] == 0.75

    def test_merge_uses_direct_params(self) -> None:
        agg = ObsAggregator()
        local = {"threshold": 0.5}
        server = {"threshold": 0.9}
        merged = agg.merge(local, server)
        assert merged["threshold"] == 0.9

    def test_fetch_config_network_error_returns_cached(self) -> None:
        agg = ObsAggregator(timeout=0.1)
        agg._cached = {"parameters": {"threshold": 0.5}}
        agg._cached_at = 1.0
        agg._cache_ttl = 9999

        with patch.object(agg, "_get_http_client") as mock_get:
            mock_client = AsyncMock(spec=httpx.AsyncClient)
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("fail"))
            mock_get.return_value = mock_client
            result = asyncio.run(agg.fetch_config())
            assert result == {"parameters": {"threshold": 0.5}}

    def test_cache_valid(self) -> None:
        agg = ObsAggregator(cache_ttl=3600)
        agg._cached = {"parameters": {"threshold": 0.5}}
        agg._cached_at = __import__("time").time()
        assert agg._is_cache_valid()

    def test_cache_expired(self) -> None:
        agg = ObsAggregator(cache_ttl=0)
        agg._cached = {"parameters": {"threshold": 0.5}}
        agg._cached_at = 0
        assert not agg._is_cache_valid()

    def test_empty_cache(self) -> None:
        agg = ObsAggregator()
        assert not agg._is_cache_valid()

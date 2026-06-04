from __future__ import annotations

from collections.abc import Callable
from typing import Any


class LazyContextLoader:
    """按需加载上下文项。注册时只存 loader 函数，首次 load() 时才执行。"""

    def __init__(self) -> None:
        self._loaders: dict[str, Callable[[], str]] = {}
        self._cache: dict[str, str] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._access_count = 0
        self._load_count = 0

    def register(self, key: str, loader: Callable[[], str], metadata: dict[str, Any] | None = None) -> None:
        self._loaders[key] = loader
        self._metadata[key] = metadata or {}

    def load(self, key: str) -> str:
        self._access_count += 1
        if key in self._cache:
            return self._cache[key]
        loader = self._loaders.get(key)
        if loader is None:
            raise KeyError(f"context key not registered: {key}")
        content = loader()
        self._cache[key] = content
        self._load_count += 1
        return content

    def prefetch(self, keys: list[str]) -> None:
        for key in keys:
            if key not in self._cache and key in self._loaders:
                content = self._loaders[key]()
                self._cache[key] = content
                self._load_count += 1

    def purge(self, key: str) -> None:
        self._cache.pop(key, None)

    def loaded(self, key: str) -> bool:
        return key in self._cache

    @property
    def loaded_count(self) -> int:
        return len(self._cache)

    @property
    def total_count(self) -> int:
        return len(self._loaders)

    def keys(self) -> list[str]:
        return list(self._loaders.keys())

    @property
    def access_count(self) -> int:
        return self._access_count

    @property
    def load_count(self) -> int:
        return self._load_count

    def stats(self) -> dict[str, Any]:
        return {
            "total_registered": self.total_count,
            "loaded": self.loaded_count,
            "accesses": self.access_count,
            "loads": self.load_count,
            "efficiency": f"{(self.load_count / max(self.total_count, 1)) * 100:.1f}%",
        }

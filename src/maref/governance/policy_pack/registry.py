from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from maref.governance.policy_pack.loader import load_policy_pack_sources
from maref.governance.policy_pack.schema import PolicyPack

_PackList = list[PolicyPack]
_CompiledRules = list[tuple[int, Any]]


class PolicyPackRegistry:
    """Active policy packs, keyed by (pack_id, version)."""

    def __init__(self, packs: Iterable[PolicyPack] = ()) -> None:
        self._packs: dict[tuple[str, str], PolicyPack] = {}
        for pack in packs:
            self.register(pack)

    def register(self, pack: PolicyPack) -> None:
        key = (pack.pack_id, pack.version)
        if key in self._packs:
            raise ValueError(f"duplicate policy pack: {pack.pack_id}@{pack.version}")
        self._packs[key] = pack

    def get(self, pack_id: str, version: str | None = None) -> PolicyPack:
        if version is not None:
            return self._packs[(pack_id, version)]
        matches = [pack for (pid, _), pack in self._packs.items() if pid == pack_id]
        if len(matches) != 1:
            raise KeyError(f"expected exactly one version for {pack_id}, got {len(matches)}")
        return matches[0]

    def list(self) -> _PackList:
        return sorted(self._packs.values(), key=lambda pack: (pack.pack_id, pack.version))

    def active_for(self, jurisdiction: str) -> _PackList:
        return [
            pack
            for pack in self.list()
            if pack.jurisdiction == "*" or pack.jurisdiction == jurisdiction
        ]

    def compile_rules(self) -> _CompiledRules:
        from maref.governance.policy_pack.compiler import compile_registry

        return compile_registry(self)

    @classmethod
    def from_sources(
        cls,
        paths: Iterable[str | Path] = (),
        pack_ids: Iterable[str] = (),
    ) -> PolicyPackRegistry:
        registry = cls()
        requested = list(pack_ids)
        if requested:
            from maref.governance.policy_pack.builtin import load_builtin_pack

            for spec in requested:
                registry.register(load_builtin_pack(spec))
        for pack in load_policy_pack_sources(paths):
            registry.register(pack)
        return registry

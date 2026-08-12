from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from maref.marketplace.adapter import ManifestAdapter
from maref.marketplace.registry import SkillManifest, SkillRegistry, SkillStatus
from maref.recursive.skill_loader import SkillLoader
from maref.recursive.skill_schema import MarefSkill, SkillSource


class MarketplaceSkillLoader:
    def __init__(
        self,
        registry: SkillRegistry | None = None,
        loader: SkillLoader | None = None,
    ) -> None:
        self._registry = registry or SkillRegistry()
        self._loader = loader or SkillLoader()
        self._manifest_cache: dict[str, SkillManifest] = {}

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    @property
    def loader(self) -> SkillLoader:
        return self._loader

    def register_manifest(
        self,
        manifest: SkillManifest,
        source: SkillSource = SkillSource.PROJECT,
    ) -> tuple[SkillManifest, MarefSkill]:
        self._registry.register(manifest)
        maref = ManifestAdapter.to_maref(manifest, source=source)
        self._loader.load_from_dict(self._maref_to_loader_dict(maref), source=source)
        self._manifest_cache[manifest.skill_id] = manifest
        self._manifest_cache[maref.skill_id] = manifest
        return manifest, maref

    def load_from_yaml(
        self,
        path: str | Path,
        source: SkillSource = SkillSource.PROJECT,
    ) -> MarefSkill | None:
        path_obj = Path(path)
        if not path_obj.exists():
            return None
        raw = path_obj.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return None
        from maref.recursive.skill_schema import parse_skill_from_dict

        maref = parse_skill_from_dict(data, source=source)
        self._loader.load_from_dict(data, source=source)
        manifest = ManifestAdapter.to_manifest(maref)
        self._registry.register(manifest)
        self._manifest_cache[manifest.skill_id] = manifest
        self._manifest_cache[maref.skill_id] = manifest
        return maref

    def register_and_approve(
        self,
        manifest: SkillManifest,
        source: SkillSource = SkillSource.PROJECT,
    ) -> tuple[SkillManifest, MarefSkill]:
        manifest, maref = self.register_manifest(manifest, source=source)
        sid = manifest.skill_id
        self._registry.run_static_scan(sid)
        self._registry.run_sandbox_test(sid)
        self._registry.approve(sid)
        return manifest, maref

    def get_skill(self, identifier: str) -> MarefSkill | None:
        manifest = self._manifest_cache.get(identifier)
        if manifest is not None:
            return ManifestAdapter.to_maref(manifest)
        return self._loader.get(identifier)

    def get_manifest(self, identifier: str) -> SkillManifest | None:
        cached = self._manifest_cache.get(identifier)
        if cached is not None:
            return cached
        maref = self._loader.get(identifier)
        if maref is not None:
            return ManifestAdapter.to_manifest(maref)
        return None

    def search(self, keywords: list[str]) -> list[SkillManifest]:
        return self._registry.search(keywords)

    def list_approved(self) -> list[SkillManifest]:
        return self._registry.list_approved()

    def list_all(self) -> list[SkillManifest]:
        return self._registry.list_all()

    def get_status(self, skill_id: str) -> SkillStatus | None:
        return self._registry.get_status(skill_id)

    def approve(self, skill_id: str) -> None:
        reg_result = self._registry.get_validation(skill_id)
        if reg_result is None:
            self._registry.run_static_scan(skill_id)
            self._registry.run_sandbox_test(skill_id)
        else:
            if not reg_result.static_scan_passed:
                self._registry.run_static_scan(skill_id)
            if not reg_result.sandbox_test_passed:
                self._registry.run_sandbox_test(skill_id)
        self._registry.approve(skill_id)

    @staticmethod
    def _maref_to_loader_dict(maref: MarefSkill) -> dict[str, Any]:
        return maref.to_dict()

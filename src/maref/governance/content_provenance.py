"""Content provenance, license checks, and data lineage (P1-B).

The enterprise roadmap requires every generated or curated asset to carry
where it came from, under which license it may be used, and which parent
assets it derives from.  :class:`ProvenanceLedger` records that information
in an append-only JSONL ledger with a SHA-256 hash chain so lineage cannot be
silently rewritten.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_ALLOWED_LICENSES = frozenset(
    {
        "CC0-1.0",
        "CC-BY-4.0",
        "CC-BY-SA-4.0",
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "proprietary",
    }
)


@dataclass
class SourceRef:
    """One upstream source used to produce an asset."""

    uri: str
    source_type: str = "document"
    license: str = "unknown"
    author: str = ""
    retrieved_at: float = field(default_factory=time.time)
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssetProvenance:
    """Provenance record for one asset."""

    asset_id: str
    content_hash: str
    license: str
    sources: list[SourceRef] = field(default_factory=list)
    ai_generated: bool = False
    model: str = ""
    prompt_hash: str = ""
    parent_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    record_hash: str = ""

    def payload(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("record_hash", None)
        return data

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LicenseDecision:
    allowed: bool
    reason: str
    asset_id: str = ""
    license: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProvenanceLedger:
    """Append-only provenance ledger with lineage and license enforcement."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        allowed_licenses: Iterable[str] | None = None,
        strict_lineage: bool = True,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self.allowed_licenses = (
            frozenset(allowed_licenses)
            if allowed_licenses is not None
            else DEFAULT_ALLOWED_LICENSES
        )
        self.strict_lineage = strict_lineage
        self._assets: dict[str, AssetProvenance] = {}
        self._last_hash = ""
        self._lock = threading.RLock()
        if self.path is not None and self.path.exists():
            self._load()

    def register(
        self,
        asset_id: str,
        *,
        content: bytes | str | None = None,
        content_hash: str = "",
        license: str = "",
        sources: Iterable[SourceRef | dict[str, Any]] = (),
        ai_generated: bool = False,
        model: str = "",
        prompt_hash: str = "",
        parent_ids: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> AssetProvenance:
        if not asset_id:
            raise ValueError("asset_id is required")
        normalized_sources = [
            source if isinstance(source, SourceRef) else SourceRef(**source) for source in sources
        ]
        parents = list(parent_ids)
        resolved_hash = content_hash or _hash_content(content)
        if not resolved_hash:
            raise ValueError("content or content_hash is required")

        with self._lock:
            if asset_id in self._assets:
                raise ValueError(f"asset already registered: {asset_id}")
            if self.strict_lineage:
                missing = [parent for parent in parents if parent not in self._assets]
                if missing:
                    raise ValueError(f"unknown parent asset(s): {', '.join(missing)}")

            asset = AssetProvenance(
                asset_id=asset_id,
                content_hash=resolved_hash,
                license=license or "unknown",
                sources=normalized_sources,
                ai_generated=ai_generated,
                model=model,
                prompt_hash=prompt_hash,
                parent_ids=parents,
                metadata=metadata or {},
                previous_hash=self._last_hash,
            )
            asset.record_hash = _record_hash(asset)
            self._assets[asset_id] = asset
            self._last_hash = asset.record_hash
            if self.path is not None:
                self._append(asset)
            return asset

    def get(self, asset_id: str) -> AssetProvenance | None:
        with self._lock:
            return self._assets.get(asset_id)

    def lineage(self, asset_id: str) -> list[AssetProvenance]:
        """Return the ancestor chain, deepest-first, excluding the asset itself."""
        with self._lock:
            asset = self._assets.get(asset_id)
            if asset is None:
                raise KeyError(asset_id)
            ordered: list[AssetProvenance] = []
            seen: set[str] = set()

            def visit(current: AssetProvenance) -> None:
                for parent_id in current.parent_ids:
                    if parent_id in seen:
                        continue
                    seen.add(parent_id)
                    parent = self._assets.get(parent_id)
                    if parent is not None:
                        visit(parent)
                        ordered.append(parent)

            visit(asset)
            return ordered

    def check_publishable(
        self,
        asset_id: str,
        *,
        allowed_licenses: Iterable[str] | None = None,
    ) -> LicenseDecision:
        with self._lock:
            asset = self._assets.get(asset_id)
            if asset is None:
                return LicenseDecision(False, "asset not registered", asset_id)
            allowed = (
                frozenset(allowed_licenses)
                if allowed_licenses is not None
                else self.allowed_licenses
            )
            if asset.license not in allowed:
                return LicenseDecision(
                    False,
                    f"license '{asset.license}' is not allowed",
                    asset_id,
                    asset.license,
                )
            for source in asset.sources:
                if source.license and source.license != "unknown" and source.license not in allowed:
                    return LicenseDecision(
                        False,
                        f"source '{source.uri}' license '{source.license}' is not allowed",
                        asset_id,
                        asset.license,
                    )
            if asset.ai_generated and (not asset.model or not asset.prompt_hash):
                return LicenseDecision(
                    False,
                    "AI-generated asset requires model and prompt_hash",
                    asset_id,
                    asset.license,
                )
            for parent in self.lineage(asset_id):
                if parent.license not in allowed:
                    return LicenseDecision(
                        False,
                        f"parent asset '{parent.asset_id}' license '{parent.license}' is not allowed",
                        asset_id,
                        asset.license,
                    )
            if not self.verify_integrity():
                return LicenseDecision(
                    False, "provenance hash chain is invalid", asset_id, asset.license
                )
            return LicenseDecision(
                True, "provenance and license checks passed", asset_id, asset.license
            )

    def verify_integrity(self) -> bool:
        with self._lock:
            previous = ""
            for asset in self._assets.values():
                if asset.previous_hash != previous:
                    return False
                if asset.record_hash != _record_hash(asset):
                    return False
                previous = asset.record_hash
            return True

    def export_manifest(self, asset_ids: Iterable[str] | None = None) -> dict[str, Any]:
        with self._lock:
            ids = list(asset_ids) if asset_ids is not None else list(self._assets)
            assets = [
                self._assets[asset_id].to_dict() for asset_id in ids if asset_id in self._assets
            ]
            return {
                "version": 1,
                "generated_at": time.time(),
                "asset_count": len(assets),
                "assets": assets,
                "integrity": self.verify_integrity(),
            }

    def _append(self, asset: AssetProvenance) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asset.to_dict(), sort_keys=True) + "\n")

    def _load(self) -> None:
        assert self.path is not None
        with self._lock:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                sources = [SourceRef(**source) for source in data.pop("sources", [])]
                asset = AssetProvenance(sources=sources, **data)
                self._assets[asset.asset_id] = asset
                self._last_hash = asset.record_hash


def _hash_content(content: bytes | str | None) -> str:
    if content is None:
        return ""
    encoded = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(encoded).hexdigest()


def _record_hash(asset: AssetProvenance) -> str:
    payload = json.dumps(asset.payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

"""TruthStore — JSON file-backed persistence for TruthPages.

Each TruthPage is stored as one JSON file under ~/.maref/truth_pages/.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from maref.knowledge.compiled_truth import TruthPage


class TruthStore:
    """JSON file-backed store for TruthPages.

    Each entity_id → one JSON file in the storage directory.
    """

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        if storage_dir is None:
            storage_dir = Path.home() / ".maref" / "truth_pages"
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, entity_id: str) -> Path:
        safe = entity_id.replace("/", "_").replace("\\", "_")[:64]
        return self._dir / f"{safe}.json"

    def save(self, page: TruthPage) -> None:
        """Save a TruthPage to disk."""
        data = page.to_dict()
        with open(self._path(page.entity_id), "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load(self, entity_id: str) -> TruthPage | None:
        """Load a TruthPage by entity_id."""
        path = self._path(entity_id)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            return TruthPage.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def list_all(self) -> list[dict[str, Any]]:
        """List all stored TruthPages with summary metadata."""
        pages: list[dict[str, Any]] = []
        for fpath in sorted(self._dir.glob("*.json")):
            try:
                with open(fpath) as f:
                    data = json.load(f)
                pages.append({
                    "entity_id": data.get("entity_id", ""),
                    "confidence": data.get("compiled_truth", {}).get("confidence", 0),
                    "updated_at": data.get("compiled_truth", {}).get("last_updated", 0),
                    "evidence_count": len(data.get("evidence_trail", [])),
                })
            except (json.JSONDecodeError, OSError):
                continue
        return pages

    def find_by_entity(self, entity_name: str) -> list[TruthPage]:
        """Find pages whose entity_id contains the given name."""
        results: list[TruthPage] = []
        name_lower = entity_name.lower().strip()
        for fpath in self._dir.glob("*.json"):
            if name_lower in fpath.stem.lower():
                page = self.load(fpath.stem)
                if page is not None:
                    results.append(page)
        return results

    def delete(self, entity_id: str) -> bool:
        """Delete a TruthPage. Returns True if deleted."""
        path = self._path(entity_id)
        if path.exists():
            path.unlink()
            return True
        return False

    @property
    def count(self) -> int:
        return len(list(self._dir.glob("*.json")))

    @property
    def storage_path(self) -> Path:
        return self._dir

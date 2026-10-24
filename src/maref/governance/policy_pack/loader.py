from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from maref import __version__
from maref.governance.policy_pack.schema import PolicyPack

MAX_PACK_BYTES = 1_000_000
_SUFFIXES = {".yaml", ".yml"}


class PolicyPackLoadError(ValueError):
    """Raised when a policy pack cannot be loaded safely."""


def _read_mapping(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise PolicyPackLoadError(f"policy pack is not a file: {resolved}")
    if resolved.stat().st_size > MAX_PACK_BYTES:
        raise PolicyPackLoadError(f"policy pack too large: {resolved}")
    try:
        data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PolicyPackLoadError(f"cannot read policy pack {resolved}: {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyPackLoadError(f"policy pack root must be a mapping: {resolved}")
    return data


def load_policy_pack(path: str | Path) -> PolicyPack:
    resolved = Path(path).resolve()
    try:
        pack = PolicyPack.model_validate(_read_mapping(resolved))
    except ValidationError as exc:
        raise PolicyPackLoadError(f"invalid policy pack {resolved}: {exc}") from exc
    if not pack.is_compatible(__version__):
        raise PolicyPackLoadError(
            f"policy pack {pack.pack_id}@{pack.version} requires "
            f">={pack.core_min},<{pack.core_max}; current={__version__}"
        )
    return pack


def load_policy_packs(root: str | Path) -> list[PolicyPack]:
    base = Path(root).resolve()
    if not base.is_dir():
        raise PolicyPackLoadError(f"policy pack root is not a directory: {base}")
    packs: list[PolicyPack] = []
    for path in sorted(base.iterdir()):
        if path.is_file() and path.suffix.lower() in _SUFFIXES:
            packs.append(load_policy_pack(path))
    return packs


def load_policy_pack_sources(paths: Iterable[str | Path]) -> list[PolicyPack]:
    packs: list[PolicyPack] = []
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_dir():
            packs.extend(load_policy_packs(path))
        else:
            packs.append(load_policy_pack(path))
    return packs

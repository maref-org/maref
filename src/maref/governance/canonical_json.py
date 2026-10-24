"""Strict canonical JSON hashing for governance evidence.

Evidence must stay verifiable across processes, restarts and languages.  The
legacy ``json.dumps(..., default=str)`` approach did not meet that bar: object
addresses, set iteration order and non-standard ``NaN`` values could change
the digest.  This module accepts only JSON data types and fails closed on
anything else.

Rules:
- only ``None``, ``bool``, ``int``, finite ``float``, ``str``, ``list``,
  ``tuple`` and ``dict`` with string keys are accepted;
- ``NaN``/``Infinity``, bytes, sets, datetimes, Decimals and custom objects
  raise :class:`CanonicalJSONError`;
- tuples are normalised to JSON arrays;
- output is UTF-8 with sorted keys and no insignificant whitespace.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

CANONICAL_JSON_VERSION = "2"


class CanonicalJSONError(ValueError):
    """Raised when a value cannot be represented as strict canonical JSON."""


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalJSONError(f"Non-finite float is not valid JSON: {value!r}")
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJSONError(
                    f"JSON object keys must be strings, got {type(key).__name__}"
                )
            normalized[key] = _normalize(item)
        return normalized
    raise CanonicalJSONError(f"Unsupported type for canonical JSON: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Return strict canonical UTF-8 JSON bytes."""

    try:
        normalized = _normalize(value)
        encoded = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return encoded.encode("utf-8")
    except CanonicalJSONError:
        raise
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise CanonicalJSONError(f"Cannot canonicalise value: {exc}") from exc


def canonical_hash(value: Any) -> str:
    """Return the SHA-256 hex digest of :func:`canonical_bytes`."""

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


__all__ = [
    "CANONICAL_JSON_VERSION",
    "CanonicalJSONError",
    "canonical_bytes",
    "canonical_hash",
]

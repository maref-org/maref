"""Tests for strict canonical JSON hashing (P1)."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from maref.governance.canonical_json import (
    CANONICAL_JSON_VERSION,
    CanonicalJSONError,
    canonical_bytes,
    canonical_hash,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_key_order_does_not_change_hash():
    first = {"b": [1, 2.5, None, True], "a": "中文", "c": {"y": 2, "x": 1}}
    second = {"c": {"x": 1, "y": 2}, "a": "中文", "b": [1, 2.5, None, True]}

    assert canonical_hash(first) == canonical_hash(second)
    assert json.loads(canonical_bytes(first)) == first


def test_tuple_and_list_normalise_to_same_hash():
    assert canonical_hash({"x": (1, 2)}) == canonical_hash({"x": [1, 2]})


def test_canonical_bytes_are_compact_utf8():
    encoded = canonical_bytes({"b": "中文", "a": 1})

    assert encoded == b'{"a":1,"b":"\xe4\xb8\xad\xe6\x96\x87"}'
    assert b" " not in encoded


def test_hash_is_stable_across_processes_and_hash_seeds():
    payload = {"b": "中文", "a": [1, 2.5, None, True], "c": {"y": 2, "x": 1}}
    expected = canonical_hash(payload)
    code = (
        "from maref.governance.canonical_json import canonical_hash;"
        "print(canonical_hash({'b': '中文', 'a': [1, 2.5, None, True],"
        " 'c': {'y': 2, 'x': 1}}))"
    )

    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        output = subprocess.check_output(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            env=env,
            text=True,
        ).strip()
        assert output == expected


@pytest.mark.parametrize(
    "value",
    [
        {"x": {1, 2}},
        {"x": dt.datetime(2026, 1, 1)},
        {"x": Decimal("1.0")},
        {"x": b"bytes"},
        {"x": object()},
        {1: "non-string-key"},
        {"x": float("nan")},
        {"x": float("inf")},
        {"x": float("-inf")},
    ],
)
def test_unsupported_values_fail_closed(value):
    with pytest.raises(CanonicalJSONError):
        canonical_bytes(value)


def test_canonical_version_is_explicit():
    assert CANONICAL_JSON_VERSION == "2"

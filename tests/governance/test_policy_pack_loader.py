from __future__ import annotations

from pathlib import Path

import pytest

from maref.governance.policy_pack.loader import (
    PolicyPackLoadError,
    load_policy_pack,
    load_policy_packs,
)


def test_load_yaml_pack(tmp_path: Path):
    path = tmp_path / "eu.yaml"
    path.write_text(
        """
pack_format: 1
pack_id: eu-ai-act
name: EU AI Act
version: "1.0.0"
jurisdiction: eu
rules:
  - rule_id: eu-payment-deny
    action: "payment.*"
    decision: deny
    regulation_ref: "EU AI Act Art. 6"
""",
        encoding="utf-8",
    )
    pack = load_policy_pack(path)
    assert pack.pack_id == "eu-ai-act"
    assert pack.content_hash()


def test_reject_oversized_file(tmp_path: Path):
    path = tmp_path / "huge.yaml"
    path.write_bytes(b"x" * (1_000_001))
    with pytest.raises(PolicyPackLoadError):
        load_policy_pack(path)


def test_reject_non_mapping_yaml(tmp_path: Path):
    path = tmp_path / "list.yaml"
    path.write_text("- not-a-pack\n", encoding="utf-8")
    with pytest.raises(PolicyPackLoadError):
        load_policy_pack(path)


def test_load_directory_sorted(tmp_path: Path):
    for name in ("b.yaml", "a.yaml"):
        (tmp_path / name).write_text(
            f"""
pack_format: 1
pack_id: {name[0]}-pack
name: {name}
version: "1.0.0"
jurisdiction: "*"
rules:
  - rule_id: {name[0]}-rule
    action: "*"
    decision: defer
    regulation_ref: "internal://test"
""",
            encoding="utf-8",
        )
    packs = load_policy_packs(tmp_path)
    assert [pack.pack_id for pack in packs] == ["a-pack", "b-pack"]


def test_reject_incompatible_core_version(tmp_path: Path):
    path = tmp_path / "future.yaml"
    path.write_text(
        """
pack_format: 1
pack_id: future-pack
name: Future
version: "1.0.0"
core_min: "99.0.0"
core_max: "100.0.0"
rules:
  - rule_id: future-rule
    action: "*"
    decision: defer
    regulation_ref: "internal://test"
""",
        encoding="utf-8",
    )
    with pytest.raises(PolicyPackLoadError):
        load_policy_pack(path)

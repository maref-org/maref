"""Tests for ObsHasher."""

from __future__ import annotations

from maref.obs.hasher import ObsHasher


class TestObsHasher:
    def test_hash_deterministic(self) -> None:
        h = ObsHasher(salt="test-salt")
        assert h.hash("hello") == h.hash("hello")

    def test_hash_length(self) -> None:
        h = ObsHasher(salt="test-salt")
        assert len(h.hash("hello")) == 16

    def test_hash_different_inputs(self) -> None:
        h = ObsHasher(salt="test-salt")
        assert h.hash("hello") != h.hash("world")

    def test_hash_different_salts(self) -> None:
        h1 = ObsHasher(salt="salt-a")
        h2 = ObsHasher(salt="salt-b")
        assert h1.hash("hello") != h2.hash("hello")

    def test_maybe_hash_basic_returns_none(self) -> None:
        h = ObsHasher(salt="test-salt")
        assert h.maybe_hash("hello", level="basic") is None

    def test_maybe_hash_standard_returns_hash(self) -> None:
        h = ObsHasher(salt="test-salt")
        result = h.maybe_hash("hello", level="standard")
        assert result is not None
        assert len(result) == 16

    def test_maybe_hash_none_value(self) -> None:
        h = ObsHasher(salt="test-salt")
        assert h.maybe_hash(None, level="standard") is None

    def test_salt_generated_if_not_provided(self) -> None:
        h = ObsHasher()
        assert len(h.salt) == 16  # 8 bytes = 16 hex chars

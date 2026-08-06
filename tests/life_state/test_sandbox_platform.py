from __future__ import annotations

import sys

from maref.life_state.sandbox import (
    LifeStateSandbox,
    MemorySandboxBackend,
    SandboxExecBackend,
    SeccompFilterBackend,
)


class TestSandboxExecBackend:
    def test_is_available_on_macos(self) -> None:
        backend = SandboxExecBackend()
        if sys.platform == "darwin":
            assert backend.is_available() is True
        else:
            assert backend.is_available() is False

    def test_is_available_false_on_non_macos(self) -> None:
        if sys.platform != "darwin":
            backend = SandboxExecBackend()
            assert backend.is_available() is False

    def test_generate_profile_default(self) -> None:
        backend = SandboxExecBackend()
        profile = backend._generate_profile()
        assert "(deny file-write*)" in profile
        assert "(deny network*)" in profile

    def test_generate_profile_custom(self) -> None:
        backend = SandboxExecBackend()
        custom = "(version 1)(deny default)"
        profile = backend._generate_profile(custom)
        assert profile == custom


class TestSeccompFilterBackend:
    def test_is_available_on_linux(self) -> None:
        backend = SeccompFilterBackend()
        if sys.platform == "linux":
            assert isinstance(backend.is_available(), bool)
        else:
            assert backend.is_available() is False

    def test_is_available_false_on_non_linux(self) -> None:
        if sys.platform != "linux":
            backend = SeccompFilterBackend()
            assert backend.is_available() is False

    def test_generate_filter_default(self) -> None:
        backend = SeccompFilterBackend()
        rules = backend._generate_filter()
        assert "socket" in rules
        assert "unlink" in rules
        assert "connect" in rules

    def test_generate_filter_custom(self) -> None:
        backend = SeccompFilterBackend()
        rules = backend._generate_filter(["open", "read"])
        assert rules == ("open", "read")


class TestBackwardCompatibility:
    def test_default_backend_is_memory(self) -> None:
        sandbox = LifeStateSandbox()
        assert isinstance(sandbox._backend, MemorySandboxBackend)

    def test_execute_without_backend_param(self) -> None:
        sandbox = LifeStateSandbox()
        result = sandbox.execute("s1", "echo hello")
        assert result["status"] == "completed"
        assert result["state_id"] == "s1"

    def test_execute_with_explicit_memory_backend(self) -> None:
        sandbox = LifeStateSandbox(backend=MemorySandboxBackend())
        result = sandbox.execute("s1", "echo hello")
        assert result["status"] == "completed"

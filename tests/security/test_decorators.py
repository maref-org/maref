"""Tests for security-critical function decorator."""

from typing import Any

import pytest

from maref.security.decorators import security_critical


class TestSecurityCritical:
    def test_marker_attribute_set(self) -> None:
        @security_critical
        def dummy() -> Any:
            return 42

        marker: Any = dummy._maref_security_critical  # type: ignore[attr-defined]
        assert marker is True

    def test_function_result(self):
        @security_critical
        def add(a, b):
            return a + b

        assert add(3, 4) == 7

    def test_preserves_name_and_docstring(self):
        @security_critical
        def my_func():
            """My docstring."""
            return 0

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "My docstring."

    def test_exception_propagates(self):
        @security_critical
        def crash():
            msg = "oops"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="oops"):
            crash()

    def test_logging_on_entry_exit(self, caplog):
        caplog.set_level("DEBUG")

        @security_critical
        def greet(name):
            return f"hello {name}"

        greet("world")

        assert len(caplog.records) > 0
        messages = [r.getMessage() for r in caplog.records]
        assert any("SECURITY_ENTER" in msg for msg in messages)
        assert any("SECURITY_EXIT" in msg for msg in messages)

    def test_logging_on_exception(self, caplog):
        caplog.set_level("DEBUG")

        @security_critical
        def fail():
            msg = "fail"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError):
            fail()

        assert len(caplog.records) > 0
        messages = [r.getMessage() for r in caplog.records]
        assert any("SECURITY_EXCEPTION" in msg for msg in messages)

    def test_kwargs_preserved(self):
        @security_critical
        def kw_only(*, x, y):
            return x * y

        assert kw_only(x=3, y=5) == 15

    def test_args_preserved(self):
        @security_critical
        def varargs(*args):
            return sum(args)

        assert varargs(1, 2, 3, 4) == 10

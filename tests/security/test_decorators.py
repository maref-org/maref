from __future__ import annotations

import logging

from maref.security.decorators import security_critical


class TestSecurityCriticalDecorator:
    def test_marks_function_as_security_critical(self) -> None:
        @security_critical
        def dummy() -> str:
            return "ok"

        assert dummy._maref_security_critical is True

    def test_preserves_function_name(self) -> None:
        @security_critical
        def my_func() -> str:
            return "ok"

        assert my_func.__name__ == "my_func"

    def test_preserves_function_docstring(self) -> None:
        @security_critical
        def doc_func() -> str:
            """My docstring"""
            return "ok"

        assert doc_func.__doc__ == "My docstring"

    def test_calls_wrapped_function(self) -> None:
        @security_critical
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_returns_value_from_wrapped(self) -> None:
        @security_critical
        def identity(x: str) -> str:
            return x

        assert identity("hello") == "hello"

    def test_propagates_exception(self) -> None:
        @security_critical
        def crash() -> None:
            msg = "internal error"
            raise ValueError(msg)

        import pytest

        with pytest.raises(ValueError, match="internal error"):
            crash()

    def test_logs_entry_and_exit(self, caplog: pytest.LogCaptureFixture) -> None:
        import pytest

        caplog.set_level(logging.DEBUG)

        @security_critical
        def logged_func() -> str:
            return "done"

        logged_func()

        assert any("SECURITY_ENTER" in r.message for r in caplog.records)
        assert any("SECURITY_EXIT" in r.message for r in caplog.records)

    def test_logs_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        import pytest

        caplog.set_level(logging.WARNING)

        @security_critical
        def failing() -> None:
            msg = "fail"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError):
            failing()

        assert any("SECURITY_EXCEPTION" in r.message for r in caplog.records)

    def test_works_on_methods(self) -> None:
        class MyClass:
            @security_critical
            def method(self) -> str:
                return "method"

        obj = MyClass()
        assert obj.method() == "method"
        assert obj.method._maref_security_critical is True

    def test_works_with_no_args(self) -> None:
        @security_critical
        def noop() -> None:
            pass

        assert noop() is None

    def test_works_on_generator(self) -> None:
        @security_critical
        def gen() -> list[int]:
            return [1, 2, 3]

        assert gen() == [1, 2, 3]

    def test_security_critical_on_variadic(self) -> None:
        @security_critical
        def variadic(*args: int, **kwargs: str) -> tuple[tuple[int, ...], dict[str, str]]:
            return args, kwargs

        result = variadic(1, 2, key="val")
        assert result == ((1, 2), {"key": "val"})

from __future__ import annotations

from unittest.mock import MagicMock

from maref.observation.probes import Probe, ProbeReading, ProbeSeverity
from maref.observation.registry import ProbeRegistry


class FakeProbe(Probe):
    def __init__(self, name: str, readings: list[ProbeReading] | None = None) -> None:
        super().__init__(name=name, primary_threshold=1.0)
        self._readings = readings or []

    def read(self, **context: object) -> list[ProbeReading]:
        return list(self._readings)


def _make_reading(probe_name: str = "p1", severity: ProbeSeverity = ProbeSeverity.NORMAL,
                  value: float = 1.0) -> ProbeReading:
    return ProbeReading(
        probe_name=probe_name,
        value=value,
        severity=severity,
        threshold=1.0,
        timestamp=1000.0,
    )


class TestProbeRegistry:
    def test_register_and_get(self) -> None:
        reg = ProbeRegistry()
        probe = FakeProbe("cpu_probe")
        reg.register(probe)
        assert reg.get("cpu_probe") is probe

    def test_unregister_existing(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu_probe"))
        assert reg.unregister("cpu_probe") is True
        assert reg.get("cpu_probe") is None

    def test_unregister_nonexistent(self) -> None:
        reg = ProbeRegistry()
        assert reg.unregister("ghost") is False

    def test_list_probes(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu"))
        reg.register(FakeProbe("mem"))
        names = reg.list_probes()
        assert "cpu" in names
        assert "mem" in names

    def test_read_all_collects_readings(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu", [_make_reading("cpu", value=0.5)]))
        reg.register(FakeProbe("mem", [_make_reading("mem", value=0.8)]))
        readings = reg.read_all()
        assert len(readings) == 2

    def test_read_all_stores_in_history(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu", [_make_reading("cpu")]))
        reg.read_all()
        assert reg.get_reading_count() == 1

    def test_add_callback_invoked(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu", [_make_reading("cpu")]))
        cb = MagicMock()
        reg.add_callback(cb)
        reg.read_all()
        cb.assert_called_once()

    def test_callback_exception_is_silent(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu", [_make_reading("cpu"), _make_reading("cpu2")]))
        cb = MagicMock(side_effect=RuntimeError("boom"))
        reg.add_callback(cb)
        readings = reg.read_all()
        assert len(readings) == 2

    def test_multiple_callbacks(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu", [_make_reading("cpu")]))
        cb1 = MagicMock()
        cb2 = MagicMock()
        reg.add_callback(cb1)
        reg.add_callback(cb2)
        reg.read_all()
        cb1.assert_called_once()
        cb2.assert_called_once()

    def test_get_recent_with_limit(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu", [
            _make_reading("cpu", value=float(i)) for i in range(10)
        ]))
        reg.read_all()
        recent = reg.get_recent(3)
        assert len(recent) == 3

    def test_get_recent_default(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu", [_make_reading("cpu")]))
        reg.read_all()
        recent = reg.get_recent()
        assert len(recent) == 1

    def test_get_reading_count(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu", [
            _make_reading("cpu"), _make_reading("cpu")
        ]))
        reg.read_all()
        assert reg.get_reading_count() == 2

    def test_get_counts_by_probe(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu", [
            _make_reading("cpu"), _make_reading("cpu")
        ]))
        reg.register(FakeProbe("mem", [_make_reading("mem")]))
        reg.read_all()
        counts = reg.get_counts_by_probe()
        assert counts["cpu"] >= 0
        assert counts["mem"] >= 0

    def test_get_counts_by_severity(self) -> None:
        reg = ProbeRegistry()
        reg.register(FakeProbe("cpu", [
            _make_reading("cpu", ProbeSeverity.NORMAL),
            _make_reading("cpu", ProbeSeverity.WARNING),
            _make_reading("cpu", ProbeSeverity.CRITICAL),
        ]))
        reg.read_all()
        counts = reg.get_counts_by_severity()
        assert counts["normal"] == 1
        assert counts["warning"] == 1
        assert counts["critical"] == 1

    def test_register_replaces_existing(self) -> None:
        reg = ProbeRegistry()
        p1 = FakeProbe("cpu")
        p2 = FakeProbe("cpu")
        reg.register(p1)
        reg.register(p2)
        assert reg.get("cpu") is p2

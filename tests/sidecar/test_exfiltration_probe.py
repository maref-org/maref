from __future__ import annotations

from sidecar.exfiltration_probe import DataExfiltrationProbe


class TestDataExfiltrationProbe:
    def test_check_returns_false(self) -> None:
        probe = DataExfiltrationProbe()
        assert probe.check(b"any data") is False

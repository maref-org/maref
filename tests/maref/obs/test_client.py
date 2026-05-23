"""Tests for MarefObsClient."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from maref.obs import MarefObsClient, TelemetryLevel
from maref.obs.schema import ObsEventType


class TestMarefObsClient:
    def setup_method(self) -> None:
        MarefObsClient.reset_default()
        self._tmpdir = Path(tempfile.mkdtemp(prefix="maref_obs_test_"))

    def teardown_method(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        MarefObsClient.reset_default()

    def test_off_level_creates_no_files(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.OFF, base_dir=self._tmpdir)
        seq = client.log_event(ObsEventType.STATE_TRANSITION)
        assert seq is None
        assert not list(self._tmpdir.iterdir())

    def test_basic_logs_event(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.BASIC, base_dir=self._tmpdir)
        seq = client.log_event(ObsEventType.STATE_TRANSITION, version="0.27.0")
        assert seq is not None
        assert seq >= 0

        events = client.get_all_events()
        assert len(events) == 1
        assert events[0]["event_type"] == "state_transition"
        assert events[0]["version"] == "0.27.0"

    def test_basic_no_metadata(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.BASIC, base_dir=self._tmpdir)
        client.log_event(
            ObsEventType.STATE_TRANSITION,
            metadata={"from": "OBSERVE", "to": "ANALYZE"},
        )
        events = client.get_all_events()
        assert len(events) == 1
        assert events[0]["metadata"] == {}

    def test_standard_includes_hashed_metadata(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.STANDARD, base_dir=self._tmpdir)
        client.log_event(
            ObsEventType.STATE_TRANSITION,
            metadata={"from": "OBSERVE", "to": "ANALYZE"},
        )
        events = client.get_all_events()
        meta = events[0]["metadata"]
        assert "from" in meta
        assert "to" in meta
        assert len(meta["from"]) == 16
        assert len(meta["to"]) == 16

    def test_state_transition_convenience_basic(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.BASIC, base_dir=self._tmpdir)
        seq = client.log_state_transition("OBSERVE", "ANALYZE", entropy=2)
        assert seq is not None
        events = client.get_all_events()
        assert events[0]["event_type"] == "state_transition"
        assert events[0]["metadata"] == {}

    def test_state_transition_convenience_standard(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.STANDARD, base_dir=self._tmpdir)
        client.log_state_transition("OBSERVE", "ANALYZE", entropy=2, reason="test")
        events = client.get_all_events()
        meta = events[0]["metadata"]
        assert "from" in meta
        assert "to" in meta
        assert meta["entropy"] == 2
        assert "reason" in meta

    def test_breaker_trip_convenience(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.STANDARD, base_dir=self._tmpdir)
        seq = client.log_breaker_trip("oscillation_rate:12.5>10.0", depth=3, entropy=4)
        assert seq is not None
        events = client.get_all_events()
        assert events[0]["event_type"] == "breaker_trip"
        meta = events[0]["metadata"]
        assert meta["depth"] == 3
        assert meta["entropy"] == 4

    def test_oscillation_convenience(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.STANDARD, base_dir=self._tmpdir)
        seq = client.log_oscillation(detected=True, rate=12.5, entropy=4)
        assert seq is not None
        events = client.get_all_events()
        assert events[0]["event_type"] == "oscillation_detected"
        meta = events[0]["metadata"]
        assert meta["rate"] == 12.5

    def test_event_sequence_increments(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.BASIC, base_dir=self._tmpdir)
        s1 = client.log_event(ObsEventType.STATE_TRANSITION)
        s2 = client.log_event(ObsEventType.BREAKER_TRIP)
        s3 = client.log_event(ObsEventType.OSCILLATION_DETECTED)
        assert s1 == 0
        assert s2 == 1
        assert s3 == 2

    def test_count_events(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.BASIC, base_dir=self._tmpdir)
        client.log_event(ObsEventType.STATE_TRANSITION)
        client.log_event(ObsEventType.STATE_TRANSITION)
        client.log_event(ObsEventType.BREAKER_TRIP)
        counts = client.count_events()
        assert counts["state_transition"] == 2
        assert counts["breaker_trip"] == 1

    def test_get_buffer_path(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.BASIC, base_dir=self._tmpdir)
        path = client.get_buffer_path()
        assert path is not None
        assert "behavior_" in path.name

    def test_get_buffer_path_off(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.OFF, base_dir=self._tmpdir)
        assert client.get_buffer_path() is None

    def test_session_id_unique(self) -> None:
        client1 = MarefObsClient(base_dir=self._tmpdir)
        client2_dir = Path(tempfile.mkdtemp(prefix="maref_obs_test2_"))
        try:
            client2 = MarefObsClient(base_dir=client2_dir)
            assert client1.session_id != client2.session_id
        finally:
            import shutil
            shutil.rmtree(client2_dir, ignore_errors=True)

    def test_singleton_get_default(self) -> None:
        MarefObsClient.reset_default()
        client1 = MarefObsClient.get_default()
        client2 = MarefObsClient.get_default()
        assert client1 is client2

    def test_reset_default(self) -> None:
        MarefObsClient.reset_default()
        c1 = MarefObsClient.get_default()
        MarefObsClient.reset_default()
        c2 = MarefObsClient.get_default()
        assert c1 is not c2

    def test_salt_persisted_to_disk(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.BASIC, base_dir=self._tmpdir)
        salt_path = self._tmpdir / ".salt"
        assert salt_path.exists()
        with open(salt_path) as f:
            assert len(f.read().strip()) == 16

    def test_log_event_ndjson_format(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.BASIC, base_dir=self._tmpdir)
        client.log_event(ObsEventType.STATE_TRANSITION, version="0.27.0")
        path = client.get_buffer_path()
        assert path and path.exists()
        with open(path) as f:
            line = f.readline().strip()
        parsed = json.loads(line)
        assert parsed["event_type"] == "state_transition"
        assert parsed["version"] == "0.27.0"
        assert "timestamp" in parsed
        assert "event_sequence" in parsed

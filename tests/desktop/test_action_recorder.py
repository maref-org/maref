from __future__ import annotations

import tempfile
from pathlib import Path

from maref.desktop.action_recorder import (
    ActionRecorder,
    ActionRecording,
    RecordedActionType,
    RecordedStep,
)


class TestRecordedStep:
    def test_to_dict(self) -> None:
        step = RecordedStep(
            step_id="step-1",
            action_type=RecordedActionType.MOUSE_CLICK,
            timestamp=1000.0,
            x=100, y=200,
        )
        d = step.to_dict()
        assert d["step_id"] == "step-1"
        assert d["action_type"] == "mouse_click"

    def test_from_dict(self) -> None:
        data = {
            "step_id": "step-1",
            "action_type": "keyboard_type",
            "timestamp": 1000.0,
            "text": "hello",
        }
        step = RecordedStep.from_dict(data)
        assert step.step_id == "step-1"
        assert step.action_type == RecordedActionType.KEYBOARD_TYPE


class TestActionRecording:
    def test_step_count(self) -> None:
        recording = ActionRecording(recording_id="rec-1", name="Test")
        assert recording.step_count == 0
        recording.steps.append(
            RecordedStep(step_id="s1", action_type=RecordedActionType.WAIT, timestamp=100.0)
        )
        assert recording.step_count == 1

    def test_total_duration_with_steps(self) -> None:
        recording = ActionRecording(recording_id="rec-1", name="Test")
        recording.steps.append(
            RecordedStep(step_id="s1", action_type=RecordedActionType.WAIT, timestamp=100.0)
        )
        recording.steps.append(
            RecordedStep(step_id="s2", action_type=RecordedActionType.MOUSE_CLICK, timestamp=105.0)
        )
        assert recording.total_duration == 5.0

    def test_total_duration_empty(self) -> None:
        recording = ActionRecording(recording_id="rec-1", name="Test")
        assert recording.total_duration == 0.0

    def test_to_dict(self) -> None:
        recording = ActionRecording(
            recording_id="rec-1",
            name="Test Recording",
            application="Finder",
            screen_width=1920,
            screen_height=1080,
            tags=["test"],
        )
        d = recording.to_dict()
        assert d["recording_id"] == "rec-1"
        assert d["screen_width"] == 1920

    def test_from_dict(self) -> None:
        data = {
            "recording_id": "rec-1",
            "name": "Test",
            "description": "",
            "application": "Finder",
            "steps": [],
            "created_at": 1000.0,
            "screen_width": 1920,
            "screen_height": 1080,
            "tags": [],
        }
        recording = ActionRecording.from_dict(data)
        assert recording.recording_id == "rec-1"


class TestActionRecorder:
    def test_start_recording(self) -> None:
        recorder = ActionRecorder()
        recording = recorder.start_recording("rec-1", "Test Recording", "Finder")
        assert recording.recording_id == "rec-1"
        assert recording.name == "Test Recording"
        assert recording.application == "Finder"

    def test_double_start_returns_new(self) -> None:
        recorder = ActionRecorder()
        r1 = recorder.start_recording("rec-1", "Test1", "Finder")
        r2 = recorder.start_recording("rec-2", "Test2", "Safari")
        assert r1 is not r2
        assert r2.recording_id == "rec-2"

    def test_stop_recording(self) -> None:
        recorder = ActionRecorder()
        recorder.start_recording("rec-1", "Test", "Finder")
        recording = recorder.stop_recording()
        assert recording is not None
        assert recording.recording_id == "rec-1"

    def test_stop_without_start(self) -> None:
        recorder = ActionRecorder()
        assert recorder.stop_recording() is None

    def test_record_step_without_start(self) -> None:
        recorder = ActionRecorder()
        assert recorder.record_step(RecordedActionType.MOUSE_CLICK, x=100, y=200) is None

    def test_record_step(self) -> None:
        recorder = ActionRecorder()
        recorder.start_recording("rec-1", "Test", "Finder")
        step = recorder.record_step(RecordedActionType.MOUSE_CLICK, x=100, y=200)
        assert step is not None
        assert step.action_type == RecordedActionType.MOUSE_CLICK

    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            recorder = ActionRecorder(storage_dir=td)
            recorder.start_recording("rec-1", "Test", "Finder")
            recorder.record_step(RecordedActionType.MOUSE_CLICK, x=100, y=200)
            recorder.stop_recording()

            recorder2 = ActionRecorder(storage_dir=td)
            loaded = recorder2.load("rec-1")
            assert loaded is not None
            assert loaded.name == "Test"
            assert len(loaded.steps) == 1

    def test_load_nonexistent(self) -> None:
        recorder = ActionRecorder()
        assert recorder.load("nonexistent") is None

    def test_list_recordings(self) -> None:
        recorder = ActionRecorder()
        recorder.start_recording("rec-1", "Test1", "Finder")
        recorder.stop_recording()
        recorder.start_recording("rec-2", "Test2", "Safari")
        recorder.stop_recording()
        recordings = recorder.list_recordings()
        assert len(recordings) == 2

    def test_delete_recording(self) -> None:
        recorder = ActionRecorder()
        recorder.start_recording("rec-1", "Test", "Finder")
        recorder.stop_recording()
        assert recorder.delete("rec-1")

    def test_get_steps_as_plan(self) -> None:
        recorder = ActionRecorder()
        recorder.start_recording("rec-1", "Test", "Finder")
        recorder.record_step(RecordedActionType.MOUSE_CLICK, x=100, y=200)
        recorder.stop_recording()
        steps = recorder.get_steps_as_plan("rec-1")
        assert len(steps) == 1

    def test_save_no_active_recording(self) -> None:
        recorder = ActionRecorder()
        assert not recorder.save()

    def test_save_active_recording(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            recorder = ActionRecorder(storage_dir=td)
            recorder.start_recording("rec-1", "Test", "Finder")
            assert recorder.save()

    def test_load_corrupt_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            Path(td, "bad.json").write_text("not json")
            recorder = ActionRecorder(storage_dir=td)
            assert recorder.load("bad") is None

    def test_load_all_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            recorder = ActionRecorder(storage_dir=td)
            assert recorder.load_all() == []

    def test_load_all_with_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            r1 = ActionRecorder(storage_dir=td)
            r1.start_recording("rec-a", "A", "Finder")
            r1.stop_recording()
            r2 = ActionRecorder(storage_dir=td)
            r2.start_recording("rec-b", "B", "Safari")
            r2.stop_recording()
            r3 = ActionRecorder(storage_dir=td)
            all_recs = r3.load_all()
            assert len(all_recs) == 2

    def test_delete_nonexistent_recording(self) -> None:
        recorder = ActionRecorder()
        assert recorder.delete("nonexistent")

    def test_get_steps_as_plan_missing(self) -> None:
        recorder = ActionRecorder()
        assert recorder.get_steps_as_plan("nonexistent") == []

    def test_get_steps_as_plan_from_disk(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            r1 = ActionRecorder(storage_dir=td)
            r1.start_recording("rec-1", "Test", "Finder")
            r1.record_step(RecordedActionType.MOUSE_CLICK, x=100, y=200)
            r1.stop_recording()
            r2 = ActionRecorder(storage_dir=td)
            steps = r2.get_steps_as_plan("rec-1")
            assert len(steps) == 1

    def test_save_os_error(self) -> None:
        import os
        import stat
        with tempfile.TemporaryDirectory() as td:
            readonly = os.path.join(td, "readonly")
            os.makedirs(readonly)
            os.chmod(readonly, stat.S_IRUSR | stat.S_IXUSR)
            recorder = ActionRecorder(storage_dir=readonly)
            recorder.start_recording("rec-1", "Test", "Finder")
            recorder.record_step(RecordedActionType.MOUSE_CLICK, x=100, y=200)
            assert not recorder.save()
            os.chmod(readonly, stat.S_IRWXU)

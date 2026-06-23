from __future__ import annotations

import tempfile
from pathlib import Path

from maref.desktop.file_watcher import FileEvent, FileEventType, FileWatcher


class TestFileEvent:
    def test_to_dict(self) -> None:
        event = FileEvent(
            event_type=FileEventType.CREATED,
            path="/tmp/test.txt",
            file_size=100,
        )
        d = event.to_dict()
        assert d["event_type"] == "created"
        assert d["path"] == "/tmp/test.txt"


class TestFileWatcher:
    def test_init_with_watch_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            watcher = FileWatcher(watch_dirs=[td])
            assert len(watcher._watch_dirs) >= 1

    def test_add_watch_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            watcher = FileWatcher()
            assert watcher.add_watch_dir(td)
            assert len(watcher._watch_dirs) == 1

    def test_add_watch_dir_blocked(self) -> None:
        watcher = FileWatcher()
        assert not watcher.add_watch_dir("/etc")

    def test_remove_watch_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            watcher = FileWatcher(watch_dirs=[td])
            watcher.remove_watch_dir(td)
            assert len(watcher._watch_dirs) == 0

    def test_start_stop(self) -> None:
        watcher = FileWatcher()
        watcher.start()
        assert watcher._watching
        watcher.stop()
        assert not watcher._watching

    def test_poll_returns_empty_when_not_watching(self) -> None:
        watcher = FileWatcher()
        events = watcher.poll()
        assert events == []

    def test_poll_detects_created_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            watcher = FileWatcher(watch_dirs=[td])
            watcher.start()
            path = Path(td) / "new_file.txt"
            path.write_text("test")
            events = watcher.poll()
            assert len(events) >= 1
            assert events[0].event_type == FileEventType.CREATED

    def test_poll_detects_modified_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.txt"
            path.write_text("initial")
            watcher = FileWatcher(watch_dirs=[td])
            watcher.poll()
            path.write_text("modified")
            watcher.start()
            events = watcher.poll()
            has_modified = any(e.event_type == FileEventType.MODIFIED for e in events)
            assert has_modified

    def test_poll_returns_empty_on_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            watcher = FileWatcher(watch_dirs=[td])
            watcher.start()
            watcher.poll()
            events = watcher.poll()
            assert len(events) == 0

    def test_poll_detects_deleted_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "delete_me.txt"
            path.write_text("test")
            watcher = FileWatcher(watch_dirs=[td])
            watcher.poll()
            path.unlink()
            watcher.start()
            events = watcher.poll()
            has_deleted = any(e.event_type == FileEventType.DELETED for e in events)
            assert has_deleted

    def test_get_events(self) -> None:
        watcher = FileWatcher()
        watcher._events.append(FileEvent(event_type=FileEventType.CREATED, path="/tmp/test.txt"))
        events = watcher.get_events()
        assert len(events) == 1
        assert len(watcher._events) == 0

    def test_get_events_no_clear(self) -> None:
        watcher = FileWatcher()
        watcher._events.append(FileEvent(event_type=FileEventType.CREATED, path="/tmp/test.txt"))
        events = watcher.get_events(clear=False)
        assert len(events) == 1
        assert len(watcher._events) == 1

    def test_get_recent_events(self) -> None:
        import time
        watcher = FileWatcher()
        watcher._events.append(FileEvent(event_type=FileEventType.CREATED, path="/tmp/test.txt"))
        recent = watcher.get_recent_events(seconds=60)
        assert len(recent) == 1

    def test_get_events_by_type(self) -> None:
        watcher = FileWatcher()
        watcher._events.append(FileEvent(event_type=FileEventType.CREATED, path="/tmp/a.txt"))
        watcher._events.append(FileEvent(event_type=FileEventType.MODIFIED, path="/tmp/b.txt"))
        created = watcher.get_events_by_type(FileEventType.CREATED)
        assert len(created) == 1

    def test_get_events_by_path(self) -> None:
        watcher = FileWatcher()
        watcher._events.append(FileEvent(event_type=FileEventType.CREATED, path="/tmp/test.txt"))
        found = watcher.get_events_by_path("/tmp/test.txt")
        assert len(found) == 1

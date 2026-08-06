from __future__ import annotations

import time

from maref.recursive.event_trigger import EventTrigger, RelEvent


class TestEventTrigger:
    def test_initial_state(self) -> None:
        et = EventTrigger(cooldown_seconds=300)
        assert et.cooldown_seconds == 300
        assert et.last_trigger == 0.0

    def test_on_event_first_time(self) -> None:
        et = EventTrigger(cooldown_seconds=300)
        event = et.create_event("git_hook", {"ref": "refs/heads/main"}, priority=1)
        assert et.on_event(event) is True

    def test_on_event_cooldown(self) -> None:
        et = EventTrigger(cooldown_seconds=300)
        event = et.create_event("git_hook")
        assert et.on_event(event) is True
        et.record_trigger()
        assert et.on_event(event) is False

    def test_on_event_different_sources(self) -> None:
        et = EventTrigger(cooldown_seconds=300)
        git_event = et.create_event("git_hook")
        fs_event = et.create_event("fs_watch")
        assert et.on_event(git_event) is True
        et.record_trigger()
        assert et.on_event(fs_event) is False

    def test_debounce_same_source(self) -> None:
        et = EventTrigger(cooldown_seconds=300)
        event = et.create_event("fs_watch")
        assert et.on_event(event) is True
        event2 = et.create_event("fs_watch")
        assert et.on_event(event2) is False

    def test_reset_clears_state(self) -> None:
        et = EventTrigger(cooldown_seconds=300)
        event = et.create_event("git_hook")
        assert et.on_event(event) is True
        et.record_trigger()
        et.reset()
        assert et.on_event(event) is True

    def test_create_event_has_valid_fields(self) -> None:
        et = EventTrigger()
        event = et.create_event("test_watcher", {"failures": 5}, priority=0)
        assert event.source == "test_watcher"
        assert event.payload == {"failures": 5}
        assert event.priority == 0
        assert event.event_id.startswith("evt_")
        assert event.timestamp > 0

    def test_cooldown_expires(self) -> None:
        et = EventTrigger(cooldown_seconds=0)
        event_a = et.create_event("git_hook")
        assert et.on_event(event_a) is True
        et.record_trigger()
        event_b = et.create_event("fs_watch")
        assert et.on_event(event_b) is True

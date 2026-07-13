"""Tests for event_trigger.py — cooldown, debounce, edge cases."""
from __future__ import annotations

import time

import pytest

from maref.recursive.event_trigger import EventTrigger, RelEvent


class TestEventTrigger:
    def test_create_event(self):
        et = EventTrigger()
        event = et.create_event("git_hook", {"branch": "main"}, priority=1)
        assert event.source == "git_hook"
        assert event.payload == {"branch": "main"}
        assert event.priority == 1
        assert event.event_id.startswith("evt_")

    def test_create_event_default_payload(self):
        et = EventTrigger()
        event = et.create_event("fs_watch")
        assert event.payload == {}
        assert event.priority == 3

    @pytest.mark.parametrize("source", ["git_hook", "fs_watch", "test_watcher"])
    def test_create_event_valid_sources(self, source):
        et = EventTrigger()
        event = et.create_event(source)
        assert event.source == source

    def test_on_event_respects_cooldown(self):
        et = EventTrigger(cooldown_seconds=300)
        event = et.create_event("git_hook")
        assert et.on_event(event) is True
        assert et.on_event(event) is False

    def test_on_event_no_cooldown(self):
        et = EventTrigger(cooldown_seconds=0)
        assert et.on_event(et.create_event("git_hook")) is True
        assert et.on_event(et.create_event("fs_watch")) is True

    def test_debounce_per_source(self):
        et = EventTrigger(cooldown_seconds=0)
        e1 = et.create_event("git_hook")
        e2 = et.create_event("fs_watch")
        assert et.on_event(e1) is True
        assert et.on_event(e2) is True

    def test_reset(self):
        et = EventTrigger(cooldown_seconds=300)
        et.on_event(et.create_event("git_hook"))
        assert et.on_event(et.create_event("git_hook")) is False
        et.reset()
        assert et.on_event(et.create_event("git_hook")) is True

    def test_record_trigger(self):
        et = EventTrigger()
        old = et.last_trigger
        time.sleep(0.001)
        et.record_trigger()
        assert et.last_trigger > old

    def test_cooldown_seconds_property(self):
        et = EventTrigger(cooldown_seconds=60)
        assert et.cooldown_seconds == 60

    def test_last_trigger_property(self):
        et = EventTrigger()
        assert et.last_trigger == 0.0

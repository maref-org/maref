from __future__ import annotations

from maref.recursive.dashboard_v3 import DashboardV3


class TestDashboardV3:
    def setup_method(self) -> None:
        self.db = DashboardV3()

    def test_create_panel(self) -> None:
        panel = self.db.create_panel("cpu_usage", "CPU Usage", "gauge")
        assert panel.panel_id == "cpu_usage"
        assert self.db.panel_count == 1

    def test_update_panel(self) -> None:
        self.db.create_panel("memory", "Memory", "percentage")
        event = self.db.update_panel("memory", 85.0)
        assert event is None

    def test_update_panel_with_alert(self) -> None:
        self.db.create_panel("temp", "Temperature", "gauge", alert_threshold=80.0)
        event = self.db.update_panel("temp", 95.0)
        assert event is not None
        assert event.event_type.startswith("alert")

    def test_get_panel(self) -> None:
        self.db.create_panel("disk", "Disk Usage", "percentage")
        panel = self.db.get_panel("disk")
        assert panel is not None
        assert panel.title == "Disk Usage"

    def test_get_snapshot(self) -> None:
        self.db.create_panel("requests", "Request Rate", "counter")
        self.db.update_panel("requests", 150)
        snapshot = self.db.get_snapshot()
        assert "panels" in snapshot

    def test_subscribe(self) -> None:
        self.db.subscribe("alerts", "viewer_1")
        assert "viewer_1" in self.db.get_subscribers("alerts")

    def test_unsubscribe(self) -> None:
        self.db.subscribe("alerts", "viewer_1")
        assert self.db.unsubscribe("alerts", "viewer_1")

    def test_broadcast_event(self) -> None:
        event = self.db.broadcast_event("system_start", {"version": "v3"})
        assert event.event_type == "system_start"

    def test_events_since(self) -> None:
        self.db.broadcast_event("e1", {})
        self.db.broadcast_event("e2", {})
        events = self.db.get_events_since(1)
        assert len(events) == 1

"""Tests for C36: Life State Resource Management."""

from __future__ import annotations

from maref.life_state.resources import (
    ResourceMonitor,
    ResourceQuota,
    ResourceType,
    ResourceUsage,
)


class TestResourceUsage:
    def test_creation(self):
        u = ResourceUsage(
            state_id="s1",
            resource_type=ResourceType.CPU,
            used=50.0,
            limit=100.0,
        )
        assert u.state_id == "s1"
        assert u.resource_type == ResourceType.CPU
        assert u.used == 50.0
        assert u.limit == 100.0

    def test_percent(self):
        u = ResourceUsage("s1", ResourceType.MEMORY, 512.0, 1024.0)
        assert u.percent == 50.0

    def test_percent_zero_limit(self):
        u = ResourceUsage("s1", ResourceType.CPU, 10.0, 0.0)
        assert u.percent == 0.0

    def test_is_over_limit(self):
        u = ResourceUsage("s1", ResourceType.CPU, 110.0, 100.0)
        assert u.is_over_limit() is True

    def test_is_not_over_limit(self):
        u = ResourceUsage("s1", ResourceType.CPU, 50.0, 100.0)
        assert u.is_over_limit() is False

    def test_to_dict(self):
        u = ResourceUsage("s1", ResourceType.IO, 500.0, 1000.0)
        d = u.to_dict()
        assert d["state_id"] == "s1"
        assert d["resource_type"] == "io"
        assert d["used"] == 500.0
        assert d["limit"] == 1000.0
        assert d["percent"] == 50.0


class TestResourceQuota:
    def test_default_creation(self):
        q = ResourceQuota(state_id="s1")
        assert q.cpu_limit == 100.0
        assert q.memory_limit == 1024.0
        assert q.io_limit == 1000.0
        assert q.network_limit == 1000.0

    def test_get_limit(self):
        q = ResourceQuota(state_id="s1", cpu_limit=200.0)
        assert q.get_limit(ResourceType.CPU) == 200.0
        assert q.get_limit(ResourceType.MEMORY) == 1024.0

    def test_to_dict(self):
        q = ResourceQuota(state_id="s1", cpu_limit=200.0)
        d = q.to_dict()
        assert d["state_id"] == "s1"
        assert d["cpu_limit"] == 200.0


class TestResourceMonitor:
    def test_set_and_get_quota(self):
        monitor = ResourceMonitor()
        q = ResourceQuota(state_id="s1", cpu_limit=200.0)
        monitor.set_quota(q)
        assert monitor.get_quota("s1").cpu_limit == 200.0

    def test_record_usage(self):
        monitor = ResourceMonitor()
        u = ResourceUsage("s1", ResourceType.CPU, 50.0, 100.0)
        monitor.record(u)
        assert monitor.get_usage("s1", ResourceType.CPU).used == 50.0

    def test_record_over_limit_creates_alert(self):
        monitor = ResourceMonitor()
        u = ResourceUsage("s1", ResourceType.CPU, 110.0, 100.0)
        monitor.record(u)
        alerts = monitor.get_alerts()
        assert len(alerts) == 1
        assert alerts[0]["state_id"] == "s1"

    def test_get_all_usage(self):
        monitor = ResourceMonitor()
        monitor.record(ResourceUsage("s1", ResourceType.CPU, 50.0, 100.0))
        monitor.record(ResourceUsage("s1", ResourceType.MEMORY, 512.0, 1024.0))
        monitor.record(ResourceUsage("s2", ResourceType.CPU, 30.0, 100.0))
        usages = monitor.get_all_usage("s1")
        assert len(usages) == 2

    def test_check_quota_pass(self):
        monitor = ResourceMonitor()
        monitor.set_quota(ResourceQuota(state_id="s1", cpu_limit=100.0))
        monitor.record(ResourceUsage("s1", ResourceType.CPU, 50.0, 100.0))
        assert monitor.check_quota("s1", ResourceType.CPU, 30.0) is True

    def test_check_quota_fail(self):
        monitor = ResourceMonitor()
        monitor.set_quota(ResourceQuota(state_id="s1", cpu_limit=100.0))
        monitor.record(ResourceUsage("s1", ResourceType.CPU, 80.0, 100.0))
        assert monitor.check_quota("s1", ResourceType.CPU, 30.0) is False

    def test_check_quota_no_quota(self):
        monitor = ResourceMonitor()
        assert monitor.check_quota("s1", ResourceType.CPU, 1000.0) is True

    def test_clear_alerts(self):
        monitor = ResourceMonitor()
        monitor.record(ResourceUsage("s1", ResourceType.CPU, 110.0, 100.0))
        monitor.clear_alerts()
        assert len(monitor.get_alerts()) == 0

    def test_to_dict(self):
        monitor = ResourceMonitor()
        monitor.set_quota(ResourceQuota(state_id="s1"))
        monitor.record(ResourceUsage("s1", ResourceType.CPU, 50.0, 100.0))
        d = monitor.to_dict()
        assert d["quota_count"] == 1
        assert d["usage_count"] == 1
        assert d["alert_count"] == 0

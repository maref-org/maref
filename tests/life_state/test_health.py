"""Tests for C35: Life State Health Monitoring and Self-Healing."""

from __future__ import annotations

from maref.life_state.health import (
    HealAction,
    HealResult,
    HealthCheck,
    HealthMonitor,
    HealthStatus,
    SelfHealer,
)


class TestHealthStatus:
    def test_all_statuses_defined(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.WARNING.value == "warning"
        assert HealthStatus.CRITICAL.value == "critical"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestHealAction:
    def test_all_actions_defined(self):
        assert HealAction.RESTART.value == "restart"
        assert HealAction.DEGRADE.value == "degrade"
        assert HealAction.ISOLATE.value == "isolate"
        assert HealAction.NOTIFY.value == "notify"


class TestHealthMonitor:
    def test_default_thresholds(self):
        monitor = HealthMonitor()
        assert monitor._thresholds["latency_ms"] == 100.0
        assert monitor._thresholds["error_rate"] == 0.05

    def test_check_passed(self):
        monitor = HealthMonitor()
        check = monitor.check("s1", "latency_ms", 50.0)
        assert check.passed is True
        assert check.metric_value == 50.0
        assert check.threshold == 100.0

    def test_check_failed(self):
        monitor = HealthMonitor()
        check = monitor.check("s1", "latency_ms", 150.0)
        assert check.passed is False

    def test_compute_health_score_perfect(self):
        monitor = HealthMonitor()
        monitor.check("s1", "latency_ms", 50.0)
        monitor.check("s1", "cpu_percent", 50.0)
        assert monitor.compute_health_score("s1") == 100.0

    def test_compute_health_score_partial(self):
        monitor = HealthMonitor()
        monitor.check("s1", "latency_ms", 50.0)
        monitor.check("s1", "latency_ms", 150.0)
        assert monitor.compute_health_score("s1") == 50.0

    def test_compute_health_score_no_checks(self):
        monitor = HealthMonitor()
        assert monitor.compute_health_score("s1") == 100.0

    def test_get_status_healthy(self):
        monitor = HealthMonitor()
        monitor.check("s1", "latency_ms", 50.0)
        assert monitor.get_status("s1") == HealthStatus.HEALTHY

    def test_get_status_warning(self):
        monitor = HealthMonitor()
        monitor.check("s1", "latency_ms", 50.0)
        monitor.check("s1", "latency_ms", 50.0)
        monitor.check("s1", "latency_ms", 150.0)
        assert monitor.get_status("s1") == HealthStatus.WARNING

    def test_get_status_critical(self):
        monitor = HealthMonitor()
        monitor.check("s1", "latency_ms", 150.0)
        assert monitor.get_status("s1") == HealthStatus.CRITICAL

    def test_set_threshold(self):
        monitor = HealthMonitor()
        monitor.set_threshold("latency_ms", 200.0)
        check = monitor.check("s1", "latency_ms", 150.0)
        assert check.passed is True

    def test_get_checks_filtered(self):
        monitor = HealthMonitor()
        monitor.check("s1", "latency_ms", 50.0)
        monitor.check("s2", "latency_ms", 50.0)
        checks = monitor.get_checks("s1")
        assert len(checks) == 1
        assert checks[0].state_id == "s1"

    def test_subscribe(self):
        monitor = HealthMonitor()
        checks: list[HealthCheck] = []
        monitor.subscribe(lambda c: checks.append(c))
        monitor.check("s1", "latency_ms", 50.0)
        assert len(checks) == 1

    def test_clear(self):
        monitor = HealthMonitor()
        monitor.check("s1", "latency_ms", 50.0)
        monitor.clear()
        assert len(monitor.get_checks()) == 0


class TestSelfHealer:
    def test_heal_with_handler(self):
        healer = SelfHealer()
        healer.register_action(
            HealAction.RESTART,
            lambda sid: HealResult(HealAction.RESTART, sid, True, "restarted"),
        )
        result = healer.heal("s1", HealAction.RESTART)
        assert result.success is True
        assert result.action == HealAction.RESTART

    def test_heal_without_handler(self):
        healer = SelfHealer()
        result = healer.heal("s1", HealAction.RESTART)
        assert result.success is False
        assert result.reason == "no_handler_registered"

    def test_auto_heal_critical(self):
        healer = SelfHealer()
        healer.register_action(
            HealAction.ISOLATE,
            lambda sid: HealResult(HealAction.ISOLATE, sid, True),
        )
        results = healer.auto_heal("s1", HealthStatus.CRITICAL)
        assert len(results) == 1
        assert results[0].action == HealAction.ISOLATE

    def test_auto_heal_warning(self):
        healer = SelfHealer()
        healer.register_action(
            HealAction.DEGRADE,
            lambda sid: HealResult(HealAction.DEGRADE, sid, True),
        )
        healer.register_action(
            HealAction.NOTIFY,
            lambda sid: HealResult(HealAction.NOTIFY, sid, True),
        )
        results = healer.auto_heal("s1", HealthStatus.WARNING)
        assert len(results) == 2

    def test_auto_heal_healthy(self):
        healer = SelfHealer()
        results = healer.auto_heal("s1", HealthStatus.HEALTHY)
        assert len(results) == 0

    def test_get_history(self):
        healer = SelfHealer()
        healer.register_action(
            HealAction.RESTART,
            lambda sid: HealResult(HealAction.RESTART, sid, True),
        )
        healer.heal("s1", HealAction.RESTART)
        history = healer.get_history()
        assert len(history) == 1

    def test_to_dict(self):
        healer = SelfHealer()
        healer.register_action(
            HealAction.RESTART,
            lambda sid: HealResult(HealAction.RESTART, sid, True),
        )
        d = healer.to_dict()
        assert d["registered_actions"] == ["restart"]
        assert d["history_count"] == 0

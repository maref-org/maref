from __future__ import annotations

from maref.observability.alert_rules import DEFAULT_RULES, Alert, AlertRule, evaluate


class TestNormalState:
    def test_no_alerts_when_everything_normal(self) -> None:
        metrics = {
            "deny_rate": 5.0,
            "risk_scores": [{"agent_id": "a1", "score": 10}],
            "open_circuit_breakers": 0,
            "p99_latency_ms": 20.0,
            "total_checks": 100,
        }
        alerts = evaluate(metrics)
        assert len(alerts) == 0


class TestHighDenyRate:
    def test_triggers_at_threshold(self) -> None:
        metrics = {"deny_rate": 45.0}
        alerts = evaluate(metrics)
        names = [a.name for a in alerts]
        assert "high_deny_rate" in names

    def test_alert_value_is_correct(self) -> None:
        metrics = {"deny_rate": 75.0}
        alerts = evaluate(metrics)
        high_deny = next(a for a in alerts if a.name == "high_deny_rate")
        assert high_deny.value == 75.0
        assert high_deny.severity == "critical"

    def test_below_threshold_no_alert(self) -> None:
        metrics = {"deny_rate": 25.0}
        alerts = evaluate(metrics)
        names = [a.name for a in alerts]
        assert "high_deny_rate" not in names


class TestElevatedRiskScore:
    def test_triggers_for_high_risk_agent(self) -> None:
        metrics = {"risk_scores": [{"agent_id": "agent-x", "score": 95}]}
        alerts = evaluate(metrics)
        names = [a.name for a in alerts]
        assert "elevated_risk_score" in names

    def test_multiple_high_risk_agents(self) -> None:
        metrics = {
            "risk_scores": [
                {"agent_id": "agent-x", "score": 95},
                {"agent_id": "agent-y", "score": 85},
            ]
        }
        alerts = evaluate(metrics)
        risk_alerts = [a for a in alerts if a.name == "elevated_risk_score"]
        assert len(risk_alerts) == 2

    def test_labels_contain_agent_id(self) -> None:
        metrics = {"risk_scores": [{"agent_id": "agent-x", "score": 95}]}
        alerts = evaluate(metrics)
        alert = next(a for a in alerts if a.name == "elevated_risk_score")
        assert alert.labels.get("agent_id") == "agent-x"

    def test_below_threshold_no_alert(self) -> None:
        metrics = {"risk_scores": [{"agent_id": "agent-x", "score": 50}]}
        alerts = evaluate(metrics)
        names = [a.name for a in alerts]
        assert "elevated_risk_score" not in names


class TestCircuitBreakerOpen:
    def test_triggers_when_cb_open(self) -> None:
        metrics = {"open_circuit_breakers": 2}
        alerts = evaluate(metrics)
        names = [a.name for a in alerts]
        assert "circuit_breaker_open" in names

    def test_alert_message_has_count(self) -> None:
        metrics = {"open_circuit_breakers": 3}
        alerts = evaluate(metrics)
        alert = next(a for a in alerts if a.name == "circuit_breaker_open")
        assert "3" in alert.message

    def test_no_alert_when_closed(self) -> None:
        metrics = {"open_circuit_breakers": 0}
        alerts = evaluate(metrics)
        names = [a.name for a in alerts]
        assert "circuit_breaker_open" not in names


class TestHighLatency:
    def test_triggers_above_100ms(self) -> None:
        metrics = {"p99_latency_ms": 150.0}
        alerts = evaluate(metrics)
        names = [a.name for a in alerts]
        assert "high_latency" in names

    def test_no_alert_below_threshold(self) -> None:
        metrics = {"p99_latency_ms": 50.0}
        alerts = evaluate(metrics)
        names = [a.name for a in alerts]
        assert "high_latency" not in names


class TestLowCheckVolume:
    def test_triggers_below_10(self) -> None:
        metrics = {"total_checks": 3}
        alerts = evaluate(metrics)
        names = [a.name for a in alerts]
        assert "low_check_volume" in names

    def test_no_alert_above_threshold(self) -> None:
        metrics = {"total_checks": 50}
        alerts = evaluate(metrics)
        names = [a.name for a in alerts]
        assert "low_check_volume" not in names


class TestCustomRules:
    def test_custom_rules_list(self) -> None:
        custom = [
            AlertRule(
                name="custom_test",
                severity="info",
                condition="test > 0",
                description="Custom rule",
                duration="1m",
            ),
        ]
        metrics = {"custom_metric": 5}
        alerts = evaluate(metrics, rules=custom)
        assert len(alerts) == 0

    def test_default_rules_have_expected_names(self) -> None:
        names = {r.name for r in DEFAULT_RULES}
        expected = {"high_deny_rate", "elevated_risk_score", "circuit_breaker_open", "high_latency", "low_check_volume"}
        assert names == expected


class TestAlertDataclass:
    def test_alert_defaults(self) -> None:
        a = Alert(name="test", severity="info", message="test message")
        assert a.value == 0.0
        assert a.labels == {}
        assert isinstance(a.triggered_at, float)

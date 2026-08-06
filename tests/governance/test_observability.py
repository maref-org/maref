"""Test observability module — error budget, RED metrics, alert rules, metric store."""
import pytest
from maref.observability.error_budget import ErrorBudget, BurnRateAlert, BurnRateLevel
from maref.observability.red_metrics import REDMetricsCollector
from maref.observability.alert_rules import AlertRule, Alert, evaluate, DEFAULT_RULES
from maref.observability.metric_store import MetricStore


class TestErrorBudget:
    def test_create(self):
        b = ErrorBudget.create(total=1000.0, consumed=100.0)
        assert b.budget_total == 1000.0
        assert b.budget_remaining_pct == 90.0

    def test_depleted(self):
        b = ErrorBudget.create(total=100.0, consumed=100.0)
        assert b.budget_remaining == 0.0


class TestBurnRate:
    def test_create(self):
        a = BurnRateAlert(
            level=BurnRateLevel.CRITICAL, burn_rate=2.5, threshold=1.5,
            window_seconds=3600, triggered=True, slo_name='t',
        )
        assert a.level == BurnRateLevel.CRITICAL

    def test_to_dict(self):
        a = BurnRateAlert(
            level=BurnRateLevel.WARNING, burn_rate=0.8, threshold=1.0,
            window_seconds=600, triggered=False, slo_name='api',
        )
        d = a.to_dict()
        assert d['level'] == 'P1'
        assert d['burn_rate'] == 0.8


class TestREDMetrics:
    def setup_method(self):
        self.c = REDMetricsCollector()

    def test_record_and_rate(self):
        for _ in range(10):
            self.c.record_request('/api/t', 'GET', 200, 100.0)
        r = self.c.get_rate(window_seconds=60)
        assert r > 0

    def test_errors(self):
        for _ in range(3):
            self.c.record_request('/api/e', 'POST', 500, 50.0)
        assert self.c.get_error_rate(window_seconds=60) == 1.0

    def test_path_metrics(self):
        self.c.record_request('/api/p', 'GET', 200, 100.0)
        pm = self.c.get_path_metrics()
        assert '/api/p' in pm
        assert pm['/api/p']['request_count'] == 1

    def test_percentiles(self):
        for i in range(100):
            self.c.record_request('/api/s', 'GET', 200, float(i * 10))
        p = self.c.get_duration_percentiles('/api/s')
        assert p['p50'] > 0
        assert p['p95'] > p['p50']
        assert p['p99'] > p['p95']

    def test_summary(self):
        self.c.record_request('/api/a', 'GET', 200, 10.0)
        self.c.record_request('/api/a', 'GET', 500, 20.0)
        s = self.c.get_red_summary(window_seconds=60)
        assert s['rate']['total_requests'] == 2
        assert s['errors']['total_errors'] == 1

    def test_reset(self):
        self.c.record_request('/api/x', 'GET', 200, 100.0)
        self.c.reset()
        assert self.c.get_rate(window_seconds=60) == 0.0
        assert self.c.get_red_summary()['rate']['total_requests'] == 0


class TestAlertRules:
    def test_evaluate_triggered(self):
        rule = AlertRule(
            name='high_deny_rate', severity='CRITICAL', condition='deny_rate > 30',
            description='Deny rate too high', duration='5m',
        )
        alerts = evaluate({'deny_rate': 50.0}, rules=[rule])
        assert len(alerts) == 1
        assert alerts[0].name == 'high_deny_rate'

    def test_evaluate_not_triggered(self):
        """Pass metrics that don't trigger any rule."""
        rule = AlertRule(
            name='high_deny_rate', severity='WARNING', condition='deny_rate > 30',
            description='Deny rate too high', duration='5m',
        )
        alerts = evaluate({'deny_rate': 5.0, 'total_checks': 100}, rules=[rule])
        assert len(alerts) == 0

    def test_no_rules(self):
        """Explicitly pass empty rules list — no DEFAULT_RULES triggered."""
        assert evaluate({'total_checks': 100}, rules=[]) == []

    def test_default_rules_are_exported(self):
        assert len(DEFAULT_RULES) >= 1
        assert DEFAULT_RULES[0].name == 'high_deny_rate'


class TestAlertDataclass:
    def test_create(self):
        a = Alert(name='test', severity='info', message='test alert', value=1.0)
        assert a.name == 'test'
        assert a.value == 1.0

    def test_default_fields(self):
        a = Alert(name='test', severity='info', message='test')
        assert a.value == 0.0
        assert a.labels == {}


class TestMetricStore:
    def setup_method(self):
        self.s = MetricStore(db_path=':memory:')

    def test_record_and_query(self):
        self.s.record('test.metric', 42.0, labels={'env': 'test'})
        r = self.s.query('test.metric')
        assert len(r) >= 1
        assert r[0]['name'] == 'test.metric'
        assert r[0]['value'] == 42.0
        assert r[0]['labels'] == {'env': 'test'}

    def test_multi_records(self):
        for i in range(10):
            self.s.record('multi', float(i * 10))
        r = self.s.query('multi')
        assert len(r) == 10

    def test_query_aggregate(self):
        for i in range(5):
            self.s.record('agg.test', float(i))
        agg = self.s.query_aggregate('agg.test', 'avg')
        assert agg == 2.0

    def test_query_aggregate_sum(self):
        for i in range(5):
            self.s.record('agg.sum', float(i))
        agg = self.s.query_aggregate('agg.sum', 'sum')
        assert agg == 10.0

    def test_close(self):
        self.s.record('close.test', 1.0)
        self.s.close()
        # No crash is the main assertion; re-query would reopen

    def test_table_stats(self):
        self.s.record('stats.test', 1.0)
        stats = self.s.get_table_stats()
        assert isinstance(stats, dict)
        assert 'telemetry_metrics' in stats

    def test_query_with_table_filter(self):
        self.s.record('filtered', 1.0, table='governance_metrics')
        r = self.s.query('filtered', table='governance_metrics')
        assert len(r) == 1


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '--no-header', '--no-cov', '--tb=short'])

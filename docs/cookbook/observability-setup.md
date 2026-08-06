# Cookbook: Observability Setup

This guide covers setting up Prometheus metrics, Grafana dashboards, and alert rules for MAREF governance monitoring.

## Scenario

You need to monitor guardrail decisions, circuit breaker state, risk scores, and cost tracking across your MAREF deployment.

## Prerequisites

```bash
pip install maref prometheus_client
```

## Step 1: Export Governance Metrics

```python
"""metrics_exporter.py"""
from maref.observability.guardrail_metrics import GuardrailMetricsCollector
from maref.observability.metric_store import MetricStore
from maref.recursive.cost_tracker import CostTracker, GasMeter

metrics = GuardrailMetricsCollector()
store = MetricStore()
gas_meter = GasMeter()
cost_tracker = CostTracker(metric_store=store)


def record_guardrail_check(verdict: str, gate: str, duration_ms: float) -> None:
    metrics.record_check(verdict, gate, duration_ms)
    store.record(
        "guardrail_check", 1.0,
        labels={"verdict": verdict, "gate": gate},
        table="guardrail_metrics",
    )


def record_risk_score(agent_id: str, score: float) -> None:
    metrics.record_risk_score(agent_id, score)


def record_operation_cost(operation: str, agent_id: str, cost: float) -> None:
    cost_tracker.track(operation, cost, agent_id)
```

## Step 2: Prometheus Metrics Endpoint

```python
"""prometheus_exporter.py"""
from prometheus_client import start_http_server, generate_latest
from observability_setup import metrics

# Start Prometheus HTTP server on port 8000
start_http_server(8000)

# Metrics are auto-exported at /metrics
# Custom endpoint
from flask import Flask, Response
app = Flask(__name__)

@app.route("/metrics")
def prometheus_metrics():
    return Response(metrics.get_metrics(), mimetype="text/plain")

# Access: curl http://localhost:8000/metrics
```

## Step 3: Grafana Dashboard

Create `maref-governance-dashboard.json` with these panels:

```json
{
  "title": "MAREF Governance Overview",
  "panels": [
    {
      "title": "Guardrail Decisions (Rate)",
      "type": "graph",
      "targets": [{"expr": "rate(guardrail_checks_total[5m])"}]
    },
    {
      "title": "Active Denials",
      "type": "stat",
      "targets": [{"expr": "guardrail_active_denials"}]
    },
    {
      "title": "Risk Scores by Agent",
      "type": "table",
      "targets": [{"expr": "guardrail_risk_score"}]
    },
    {
      "title": "Open Circuit Breakers",
      "type": "stat",
      "targets": [{"expr": "guardrail_circuit_breakers_open"}]
    }
  ]
}
```

## Step 4: Alert Rules

```yaml
# prometheus-alerts.yml
groups:
  - name: maref-governance
    rules:
      - alert: HighDenialRate
        expr: rate(guardrail_checks_total{verdict="DENY"}[5m]) > 10
        for: 5m
        labels: { severity: warning }
        annotations:
          summary: "High denial rate on guardrail checks"

      - alert: CircuitBreakerOpen
        expr: guardrail_circuit_breakers_open > 0
        for: 1m
        labels: { severity: critical }
        annotations:
          summary: "Circuit breaker is open"

      - alert: HighRiskScore
        expr: guardrail_risk_score > 80
        for: 5m
        labels: { severity: warning }
        annotations:
          summary: "Agent {{ $labels.agent_id }} has risk score {{ $value }}"
```

## Step 5: Verify

```python
stats = metrics.get_stats()
print(f"Checks: {stats['total_checks']}, Allow rate: {stats['allow_rate']}%")

prom_output = metrics.get_metrics()
print(prom_output[:500])

table_stats = store.get_table_stats()
print(f"DB tables: {table_stats}")
```

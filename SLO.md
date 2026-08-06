# MAREF Service Level Objectives

## 1. Availability SLO
- Target: 99.9% uptime (monthly)
- Measurement: Health check endpoint (/health) success rate
- Error budget: 43 minutes/month downtime
- Burn rate alert: 5% error budget consumed in 1h → P2, 10% in 1h → P1

## 2. Performance SLO (API)
- Target: P99 latency < 500ms for governance decisions
- Measurement: OpenTelemetry RED metrics
- Exclusions: LLM inference calls (measured separately)
- Error budget: 5% of requests may exceed 500ms

## 3. Performance SLO (Desktop)
- Target: P99 latency < 2s for screenshot→verify cycle
- Measurement: DesktopAgent operation metrics
- Error budget: 2% of operations may exceed 2s

## 4. Cost SLO
- Token consumption per governance decision: < 1000 tokens avg
- Monthly compute budget: $50/server (3 replicas = $150)

## 5. Data Quality SLO
- Audit log integrity: 100% of entries HMAC-verified
- Trust score freshness: < 30s stale

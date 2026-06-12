# Agent Governance Benchmark v1

## Problem: Why Agents Need Governance

Multi-agent systems are deploying into production without governance — no audit trails, no trust boundaries, no formal verification. This creates systemic risk for enterprises.

## Governance Dimension Framework (10 Dimensions)

1. **Audit Trail** — Immutable, tamper-evident decision log
2. **Trust Boundaries** — Cross-domain access enforcement
3. **Formal Verification** — Mathematical correctness proofs
4. **Policy Engine** — Declarative rule enforcement
5. **Human-in-the-Loop** — Configurable human approval gates
6. **Budget & Quota** — Token/action consumption limits
7. **Observability** — Metrics, tracing, and alerting
8. **Federation** — Multi-org governance coordination
9. **Disaster Recovery** — State rollback and failover
10. **Regulatory Compliance** — EU AI Act, NIST, China CAC mapping

## Competitive Scoring Matrix

| Framework | Audit | Trust | Formal | Policy | HITL | Budget | Observability | Federation | DR | Compliance | Total |
|-----------|-------|-------|--------|--------|------|--------|---------------|------------|----|------------|-------|
| **MAREF** | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | **10/10** |
| LangGraph | 2 | 1 | 0 | 2 | 3 | 2 | 2 | 1 | 1 | 1 | **2/10** |
| CrewAI | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | **1/10** |
| AutoGen | 2 | 1 | 0 | 2 | 2 | 1 | 2 | 1 | 1 | 1 | **2/10** |
| Anthropic MCP | 3 | 2 | 0 | 3 | 3 | 3 | 3 | 2 | 1 | 2 | **4/10** |

## Methodology

Each dimension scored 0-10:
- **0**: Not supported
- **1-3**: Basic/partial support
- **4-6**: Functional but limited
- **7-9**: Production-ready
- **10**: Best-in-class with formal verification

Scoring is reproducible via `scripts/benchmark.py` (coming in v0.31.0).

## Regulatory Mapping

| Regulation | MAREF Control |
|-----------|--------------|
| EU AI Act Art. 12 | AuditLogger with HMAC-SHA256 |
| EU AI Act Art. 14 | HITL governance gates |
| NIST AI RMF 1.0 | TrustBoundaryManager |
| Singapore AI Verify | Formal verification traces |
| China CAC GenAI | SM2/SM3/SM4-GCM crypto |

# MAREF ↔ NIST Alignment Reference

> **Purpose**: Precise, non-fabricated mapping of MAREF to real NIST programs and frameworks.
> **Fact discipline (2026-09-05)**: NIST has NOT published an "AI RMF Agentic Profile" document as of this date. Agentic-systems work currently lives under the **NIST AI Agent Standards Initiative**, announced by the NIST CAISI on **2026-02-17**. This document therefore maps MAREF to the *real* initiative and to the published AI RMF 1.0 functions. Any future NIST agentic-profile publication should be added here before it appears in marketing text.
> **Cross-check audit**: `Athena知识库/OPC工作区/4-审计/2026-09-05-GEO战略引用数据事实核查审计.md` §2.7.

---

## 1. NIST AI Agent Standards Initiative (CAISI, announced 2026-02-17)

NIST announced an initiative focused on making AI agents **interoperable, secure, and trustworthy** — covering agent security/safety, agent identity and attestation, and inter-agent interoperability (protocols). MAREF is a governance-first runtime designed for exactly these concerns.

| Initiative focus area | MAREF mechanism | In-repo evidence |
|----------------------|-----------------|------------------|
| Agent security & safety | Gray Code governance FSM (Hamming distance = 1), circuit breaker HALT absorbing state, 4-level safety decision tree | `src/formal/`, `src/maref/governance/`, `docs/security/owasp-agentic-top10-mapping.md` |
| Agent identity & attestation | Zero-trust per-agent Ed25519 identity, time-scoped credentials, DID-style registration | `src/maref/identity/` |
| Inter-agent interoperability | MCP protocol (6 transports) + A2A v0.3 bridge + cross-framework adapters (AutoGen/CrewAI/LangGraph/Dify/Coze) | `src/maref/mcp/`, `src/maref/integration/` |
| Trustworthy behavior / misbehavior research | Red-blue adversarial harness (200 rounds) + chaos engineering (5 fault types) | `src/maref/redblue/`, `tests/chaos/` |

## 2. NIST AI Risk Management Framework 1.0 — function-level mapping

MAREF operationalizes the AI RMF 1.0 core functions at **runtime**, inside the agent loop, rather than as a one-time organizational assessment.

| AI RMF 1.0 function | Function intent (from the published RMF) | MAREF implementation | Evidence |
|---------------------|-------------------------------------------|----------------------|----------|
| **GOVERN** | Establish governance structures, policies, accountability for AI risk | Constitutional layer: per-agent policy, 4-level decision tree (Rule → Mode → SafetyGate → User), autonomy tiering | `src/maref/governance/`, `src/maref_lite/` |
| **MAP** | Contextualize risks: map the AI system, its context, and relevant threats | Tool-risk classification per tool, threat-to-control mapping across all 10 OWASP agentic risk classes | `docs/security/owasp-agentic-top10-mapping.md`, `src/maref/tools/registry.py` |
| **MEASURE** | Assess and analyze risks using quantitative methods | Trust Engine v2 drift detection (KL/JS/Hellinger), behavioral telemetry, red-blue measurement | `src/maref/evaluation/`, `src/maref/observability/` |
| **MANAGE** | Prioritize and respond to risks | Circuit breaker HALT, drift-triggered policy adjustment, Merkle audit chain for post-incident verification | `src/maref/security/`, `src/maref/governance/circuit_breaker.py` |

### Related published NIST artifact
- **NIST AI 600-1** (Generative AI Profile, 2024-07): MAREF's 8-layer defense and input/output filtering align with the GenAI Profile's content-safety and provenance concerns; MAREF does **not** claim conformance to NIST AI 600-1.

## 3. Honest-scope statement (read this before citing)

1. MAREF is **not NIST-certified** and claims no NIST endorsement.
2. MAREF does **not** reference a "NIST AI RMF Agentic Profile" — that document does not exist (as of 2026-09). Referencing a nonexistent document damages LLM trust via cross-check failure.
3. This mapping is **claim → evidence**: each MAREF capability is linked to source code or a test directory so it can be independently verified (`pytest tests/governance/`, `pytest tests/formal/`).

## 4. Related documents

- OWASP mapping: `docs/security/owasp-agentic-top10-mapping.md`
- Technical whitepaper (Lyapunov convergence, TLA+ results): `docs/MAREF-Technical-Whitepaper-arXiv.md`
- NIST announcement: https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure

# Loop Engineering + MAREF Governance

> Version: v0.36.0-rc — Full implementation (Convergent/Exploratory/Interactive + Governance bridge)

---

## The Governance Gap in Agent Loops

Loop Engineering frameworks (Google ADK 2.0, Vercel AI SDK, Pipedream) provide a **code → verify → deploy** closed loop. But they share a structural gap: **no governance layer**.

| Loop Phase | Function | Governance Gap |
|-----------|----------|----------------|
| Code | LLM writes code/prompts | No security checks |
| Verify | Test run/evaluation | Who verifies the verifier? |
| Deploy | Release/rollout | No circuit breaker, no drift detection |
| Monitor | Metrics/alerting | No agent-level governance |

MAREF fills this gap — as the **governance operating system** for agent loops.

---

## 5-Line Integration

```python
from maref.integration.maref_loop_adapter import MAREFLoop

governance = MAREFLoop()
governance.register_verifier("code-reviewer", "claude-4", "cross-check", accuracy=0.9)

if governance.check("deploy", {"env": "production"})["passed"]:
    deploy()
    governance.record("deploy", {"success": True})
```

---

## Three Loop Meta-Patterns

Not all loops are the same. MAREF identifies three reusable meta-patterns:

### Convergent Loop
**Use cases**: Code generation, bug fixes, data analysis, hyperparameter tuning
**Evaluator**: Monotonically decreasing error count
**Stop condition**: `error_count == 0` or `improvement < threshold`
**MAREF components**: `RecursiveEvolutionEngine`, `OscillationFixLoop`, `GovernanceStateMachine` canonical path

### Exploratory Loop
**Use cases**: Market research, brainstorming, technology selection, creative generation
**Evaluator**: Diversity/coverage score
**Stop condition**: `diversity > threshold` or `time/token budget exhausted`
**MAREF components**: `MetaLearner`, `StigmergySwarm`, `DecisionMarket`

### Interactive Loop
**Use cases**: Customer service, sales, education, HITL approval workflows
**Evaluator**: Per-turn sentiment + intent matching + satisfaction
**Stop condition**: User confirms completion or `turn >= max_turns`
**MAREF components**: `HITLService`, `CarbonSiliconSymbiosis`, `FourPhaseGovernance`, `InterruptProtocol`

---

## Scenario-Governance Design Matrix

| Scenario | Loop Pattern | Governance Strategy | Tool Boundary Example |
|----------|-------------|-------------------|----------------------|
| Code generation | Convergent | Sandbox from production, no `git push main` | File system(RO) + test framework + Lint |
| Customer service | Interactive | Audit PII access, GDPR compliance | Knowledge base(RO) + CRM(write-audited) |
| Financial trading | Convergent | Dual approval + amount cap + circuit breaker | Market API(RO) + order system(HITL-required) |
| Medical diagnosis | Interactive | Human doctor final review, Agent=assistant only | Medical records(RO) + imaging analysis(suggest mode) |
| Market research | Exploratory | No data modification, no external report sending | Search engine(RO) + database(RO) |
| Data analysis | Convergent | Data permissions + export sanitization | Database(restricted query) + chart engine |

---

## Design Flow for New Scenarios

```
Step 1: Define success (Goal) — quantifiable completion criteria
Step 2: Select meta-pattern — Convergent / Exploratory / Interactive
Step 3: Design Evaluator — test pass rate? diversity score? sentiment analysis?
Step 4: Set tool boundaries — what can the agent call? (TrustBoundaryManager + MCPGovernance)
Step 5: Set hard stops — token limit, round count, time budget (CircuitBreaker + MetaGovernance)
Step 6: Add governance layer — what to audit? how? who owns the outcome?
```

---

## Three-Layer Architecture (v0.36.0-rc target)

```
Layer 1: Task Loop Templates (src/maref/loop/) — NEW in v0.36.0-rc
  ├── ConvergentLoop — Evaluator + ToolBoundary + StopCondition
  ├── ExploratoryLoop — DiversityEvaluator + TokenBudget + TimeBudget
  └── InteractiveLoop — SentimentSafetyValve + ConversationContext

Layer 2: Governance Meta-Loop (src/maref/governance/) — EXISTS
  └── 10-state Gray Code FSM + CircuitBreaker + TrustBoundaryManager

Layer 3: Recursive Evolution (src/maref/evolution/) — EXISTS
  └── C1→C2→C3 + MetaLearner + PolicySandbox + DriftGuard
```

---

## Competitive Comparison

| Dimension | **MAREF** | Google ADK 2.0 | Vercel AI SDK | Pipedream |
|-----------|----------|---------------|---------------|-----------|
| Loop governance | ✅ MAREFLoop | ❌ None | ❌ None | ❌ None |
| 3 meta-pattern templates | 🚧 v0.36.0-rc | ⚠️ Convergent only | ❌ None | ❌ None |
| Verifier cross-validation | ✅ VerifierConsensus | ⚠️ Single evaluator | ❌ None | ❌ None |
| Circuit breaker + drift | ✅ Yes | ❌ None | ❌ None | ❌ None |
| Formal verification | ✅ TLA+ | ❌ None | ❌ None | ❌ None |
| Task↔Governance bridge | 🚧 v0.36.0-rc | ❌ None | ❌ None | ❌ None |
| Integration cost | 5 lines of code | — | — | — |

---

## Roadmap

| Version | Loop Engineering Delivery |
|---------|--------------------------|
| **v0.35.0-rc** | Narrative + docs + 3 meta-pattern architecture design |
| **v0.36.0-rc** | Full `maref.loop` module — Convergent/Exploratory/Interactive + Governance bridge **(current)** |
| **v0.36.0-rc** | `src/maref/loop/` subsystem: 3 templates + Task-Governance bridge |
| **v1.0** | Full recursive evolution + Agent credit rating + Four-phase governance |

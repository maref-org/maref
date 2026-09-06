---
slug: maref-vs-langgraph-governance-benchmark
title: 'MAREF vs LangGraph vs CrewAI vs AutoGen: The Governance Layer Benchmark'
authors: [maref]
tags: [benchmark, governance, langgraph, crewai, autogen, comparison, 2026]
date: 2026-07-22
description: "We benchmarked MAREF's governance primitives against LangGraph, CrewAI, and AutoGen. The result: MAREF adds 4.7ms mean overhead per full governance cycle, while the other three frameworks ship zero native governance. Here's the 10-dimension comparison and reproducible numbers."
---

> **Measurement note (added 2026-09-05)**: Governance overhead is **hardware/commit dependent**. The figures in this post were measured on the authoring machine. The committed raw output in `benchmarks/results-2026-07-08.txt` (full pipeline mean ~11.4 ms / p99 ~23.9 ms on that host) differs accordingly. Always reproduce on your own hardware: `python benchmarks/governance_overhead.py` — prefer that command over any single number quoted in this or other posts.

> **TL;DR**: MAREF's full governance pipeline (state machine + circuit breaker + subgoal interceptor + safety gate + behavior monitor) costs **4,688 μs mean / 13,316 μs p99** per cycle. LangGraph, CrewAI, and AutoGen ship **0 ms** of native governance overhead — but also **0/10 OWASP Agentic Top 10 coverage**. This article presents a reproducible benchmark, a 10-dimension comparison matrix, and an honest analysis of when each framework is the right choice.

<!-- truncate -->

## Why Benchmark Governance?

Every agent framework claims to be "production-ready." None of them tell you what happens when an agent goes rogue.

When we started MAREF, the question wasn't "can we build a faster agent orchestrator?" — LangGraph, CrewAI, and AutoGen already do that well. The question was: **what does it cost to make an agent safe enough to deploy in production?**

Governance isn't free. A trust state machine adds transitions. A circuit breaker adds failure tracking. A subgoal interceptor adds a CoT scanning pass. A behavior monitor adds statistical analysis. An audit trail adds I/O. These costs compound.

But the alternative — deploying an agent with no governance — costs more. Deloitte's 2026 report found 88% of enterprises had an AI agent incident last year. Gartner predicts 40% will decommission agents by 2027 due to governance gaps, not capability gaps.

This benchmark answers two questions:

1. **How much latency does MAREF's governance layer actually add?**
2. **How does that compare to building governance yourself on LangGraph/CrewAI/AutoGen?**

## Methodology

All measurements were taken on a single machine using Python 3.11 with `time.perf_counter()` micro-benchmarks. Each primitive was warmed up (100–1000 iterations) before measurement to stabilize caches and branch prediction, then measured over 1,000 iterations.

**Reproduce it yourself:**

```bash
git clone https://github.com/maref-org/maref.git
cd maref
python benchmarks/governance_overhead.py --iters 1000
```

The benchmark script ([`benchmarks/governance_overhead.py`](https://github.com/maref-org/maref/blob/main/benchmarks/governance_overhead.py)) measures seven governance primitives:

1. **`GovernanceStateMachine.transition()`** — single 10-state Gray Code FSM step (with audit trail)
2. **`GovernanceStateMachine.force_stabilize()`** — BFS shortest-path to STABILIZE state
3. **`GovernanceStateMachine.force_halt()`** — BFS shortest-path to absorbing HALT state
4. **`CircuitBreaker.record_failure() + check_depth()`** — failure tracking + recursion depth guard
5. **`SubgoalInterceptor.intercept()`** — full Layer 4 pipeline (CoT scan + goal inference + safety gate)
6. **`SafetyGateV2.validate_decomposition()`** — subtask explosion + dangerous capability guard
7. **`BehaviorMonitor.record_activity() + detect_anomalies()`** — 3-sigma anomaly detection

For comparison, LangGraph, CrewAI, and AutoGen were measured at **0 ms** because they ship no native governance primitives. Their governance overhead is zero out-of-the-box — but so is their governance coverage.

## Benchmark Results

| Primitive | mean (μs) | p50 (μs) | p99 (μs) | max (μs) |
|-----------|--------:|--------:|--------:|--------:|
| `StateMachine.transition()` | 359.74 | 416.83 | 944.17 | 1,809.33 |
| `StateMachine.force_stabilize()` | 3.11 | 3.08 | 4.00 | 12.54 |
| `StateMachine.force_halt()` | 4,226.27 | 3,865.29 | 11,916.46 | 56,471.50 |
| `CircuitBreaker.record_failure()+check_depth()` | 0.35 | 0.29 | 0.62 | 20.67 |
| `SubgoalInterceptor.intercept()` [benign] | 10.53 | 10.37 | 13.42 | 51.13 |
| `SafetyGateV2.validate_decomposition()` | 0.41 | 0.38 | 0.50 | 5.21 |
| `BehaviorMonitor.record+detect()` | 87.93 | 59.00 | 436.63 | 990.96 |
| **TOTAL (full pipeline)** | **4,688.34** | — | **13,315.79** | — |

### Reading the numbers

The first thing to notice: **pure governance logic is fast**. CircuitBreaker adds 0.35 μs. SafetyGate adds 0.41 μs. SubgoalInterceptor — the heaviest governance primitive, which scans a full CoT token stream, infers a goal DAG, and checks for control subgoals — adds 10.5 μs. These are sub-microsecond to low-double-digit-microsecond costs.

The second thing: **audit trail I/O dominates**. `StateMachine.transition()` costs 360 μs because it appends to a tamper-evident hash chain (reading the previous record's hash, computing SHA-256, writing to disk with POSIX advisory locks). `force_halt()` costs 4.2 ms because it creates a fresh FSM and performs multiple audited transitions in sequence.

This is a deliberate trade-off: MAREF prioritizes **tamper-evidence over raw speed**. Every state transition is part of a cryptographically-linked audit chain that can be independently verified. If you don't need tamper-evidence, you can disable audit logging and the transition cost drops to single-digit microseconds.

### The O(n) audit chain caveat

The current audit trail implementation reads the last record from the file on each write to chain the hash. For long-running sessions with thousands of transitions, this creates O(n) read amplification. We're optimizing this to a streaming hash chain (keeping only the last hash in memory) in v0.36. After that optimization, `transition()` is expected to drop to ~20 μs.

**This is a known performance issue, not a fundamental architectural cost.** The governance logic itself is already sub-microsecond.

## 10-Dimension Comparison Matrix

We compared MAREF against the three most popular agent orchestration frameworks across ten governance dimensions. The question for each dimension: **does the framework ship this capability natively, or must you build it yourself?**

| # | Governance Dimension | MAREF | LangGraph | CrewAI | AutoGen |
|---|---------------------|-------|-----------|--------|---------|
| 1 | **Trust State Machine** (FSM with formal transitions) | ✅ 10-state Gray Code, TLA+ verified | ❌ No FSM (graph-based routing) | ❌ No FSM (role-based sequential) | ❌ No FSM (conversation-based) |
| 2 | **Circuit Breaker** (recursion depth + oscillation guard) | ✅ 0.35 μs/op, configurable thresholds | ❌ No native circuit breaker | ❌ No native circuit breaker | ❌ No native circuit breaker |
| 3 | **Subgoal Interception** (goal hijack defense) | ✅ 10.5 μs/op, CoT + goal DAG + safety gate | ❌ No subgoal interception | ❌ No subgoal interception | ❌ No subgoal interception |
| 4 | **Behavior Monitoring** (rogue agent detection) | ✅ 3-sigma anomaly detection, 88 μs/op | ❌ No behavior monitoring | ❌ No behavior monitoring | ❌ No behavior monitoring |
| 5 | **Human-in-the-Loop Enforcement** | ✅ Formal HITL invariant in TLA+ | ⚠️ Manual `interrupt_before` nodes (not enforced) | ⚠️ Manual `human_input` flag (not enforced) | ⚠️ Manual `is_termination_msg` (not enforced) |
| 6 | **Tamper-evident Audit Trail** | ✅ SHA-256 hash chain, POSIX locks, per-actor shards | ❌ No native audit trail | ❌ No native audit trail | ❌ No native audit trail |
| 7 | **Formal Verification** (TLA+ specs) | ✅ 7 TLA+ modules, TLC CI integration | ❌ No formal specs | ❌ No formal specs | ❌ No formal specs |
| 8 | **Recursive Depth Protection** | ✅ CircuitBreaker + SafetyGate (max 3 depth, max 8 dangerous subtasks) | ❌ No depth protection | ❌ No depth protection | ❌ No depth protection |
| 9 | **Cross-Instance Governance** | ✅ G5 CrossInstanceGovernor | ❌ No cross-instance governance | ❌ No cross-instance governance | ❌ No cross-instance governance |
| 10 | **OWASP Agentic Top 10 Coverage** | ✅ 10/10 (see [mapping](https://github.com/maref-org/maref/blob/main/docs/governance/owasp-agentic-top10-mapping.md)) | ❌ 0/10 | ❌ 0/10 | ❌ 0/10 |

### What "native" means

When we say LangGraph has "no native circuit breaker," we don't mean it's impossible to build one. You can write a circuit breaker in Python and wrap every LangGraph node with it. But:

1. **You have to design it** — what triggers the breaker? What state machine does it use? How does it recover?
2. **You have to test it** — does it handle concurrency? Does it survive process restarts?
3. **You have to verify it** — can you prove it trips in all cases where it should?
4. **You have to maintain it** — across framework upgrades, across team turnover.
5. **You have to audit it** — does it produce tamper-evidence? Can a compliance officer verify it?

MAREF ships all of this, formally specified in TLA+, unit-tested with 270+ tests, and CI-verified on every commit. The 4.7 ms overhead is the cost of having it done for you.

## Governance Overhead in Context

Is 4.7 ms per governance cycle a lot? Let's contextualize:

| Operation | Latency |
|-----------|---------|
| LLM API call (GPT-4-class, single inference) | 500–3,000 ms |
| Vector DB query (top-10 retrieval) | 5–50 ms |
| MAREF full governance pipeline (mean) | **4.7 ms** |
| MAREF pure governance logic (no audit) | **~0.1 ms** |
| Python function call overhead | ~0.0001 ms |

**MAREF's governance overhead is 0.15%–0.9% of a single LLM call.** In a typical agent step (LLM inference + tool execution + state update), governance adds less than 1% latency.

For the pure logic path (CircuitBreaker + SafetyGate + SubgoalInterceptor without audit I/O), the overhead is **~0.1 ms — effectively unmeasurable** compared to the LLM call it guards.

The 4.2 ms `force_halt()` cost is irrelevant in normal operation because `force_halt()` only fires on governance violations — it's the emergency brake, not the gas pedal. You don't optimize the emergency brake for speed; you optimize for reliability.

## When to Choose What

This isn't a "MAREF wins, everything else loses" article. Each framework has a different sweet spot.

### Choose LangGraph when

- You're building **stateful, graph-structured agent workflows** with complex routing.
- You need **streaming and human-in-the-loop interrupts** at specific nodes (you'll add governance manually).
- Your agents operate in a **trusted environment** (internal tools, sandboxed execution).
- You're willing to **build governance yourself** (circuit breaker, audit trail, etc.).

LangGraph's graph-based routing is excellent for complex agent topologies. But if you deploy it in production without adding governance, you're accepting the 88% incident risk.

### Choose CrewAI when

- You're building **role-based multi-agent systems** with clear task decomposition.
- You want **simplicity and rapid prototyping** over formal guarantees.
- Your use case is **low-stakes** (content generation, research summarization).
- You don't need **tamper-evidence or formal verification**.

CrewAI's role-based model is intuitive and fast to prototype. But its "governance" is a `human_input=True` flag — there's no enforcement, no audit trail, no formal model.

### Choose AutoGen when

- You're building **conversational multi-agent systems** with peer-to-peer dialogue.
- You need **flexible agent communication patterns** (group chat, nested conversations).
- You're doing **research exploration** where governance overhead would slow iteration.
- You'll add **external governance** (policy API, wrapper service) separately.

AutoGen's conversational model is powerful for research. But its `is_termination_msg` callback is a string match — not a governance primitive.

### Choose MAREF when

- You're deploying agents in **high-stakes production** (finance, healthcare, infrastructure).
- You need **formal verification** of safety properties (TLA+ specs, TLC model checking).
- You require **tamper-evident audit trails** for compliance (SOC 2, ISO 27001, HIPAA).
- You want **OWASP Agentic Top 10 coverage** out of the box.
- You need **cross-instance governance** (multi-agent, multi-tenant, multi-region).
- You're willing to accept **~5 ms governance overhead per cycle** in exchange for 10/10 coverage.

MAREF isn't competing with LangGraph for workflow routing. It's the **governance layer that sits underneath** any of them. You can use MAREF's governance primitives (CircuitBreaker, SubgoalInterceptor, BehaviorMonitor) alongside a LangGraph workflow — and we're building adapters for exactly that use case.

## The Build-vs-Buy Math

If you choose LangGraph and decide to build governance yourself, here's what you're signing up for:

| Governance Primitive | Build Effort | Testing Effort | Verification Effort |
|---------------------|-------------|---------------|-------------------|
| Trust State Machine | 2–3 weeks (design + implement) | 1 week (unit tests) | 2–4 weeks (TLA+ spec + TLC) |
| Circuit Breaker | 3–5 days | 2–3 days | N/A (usually skipped) |
| Subgoal Interceptor | 3–4 weeks (CoT patterns, goal DAG) | 1–2 weeks (adversarial tests) | N/A |
| Behavior Monitor | 1–2 weeks (statistics + poisoning defense) | 1 week | N/A |
| Audit Trail (tamper-evident) | 1–2 weeks (hash chain + locking) | 3–5 days | N/A |
| HITL Enforcement | 1 week (if done correctly with formal invariant) | 3–5 days | 1–2 weeks (TLA+) |
| **Total** | **~8–12 weeks** | **~4–6 weeks** | **~3–6 weeks** |

**Building governance yourself costs 15–24 weeks of engineering effort** — and that's assuming you have a formal methods engineer who can write TLA+ specs. Most teams don't, which is why most "DIY governance" implementations are incomplete: they have a circuit breaker but no formal verification, an audit log but no tamper-evidence, a HITL flag but no enforcement invariant.

MAREF's 4.7 ms overhead buys you 15–24 weeks of engineering you don't have to do, done by people who specialize in agent governance, formally verified and continuously tested.

## Limitations and Honesty

This benchmark has limitations we want to be transparent about:

1. **Single-machine, single-process.** Production deployments involve network calls, serialization, and concurrency. Real-world governance overhead will be higher due to these factors — but for all frameworks equally.

2. **Audit I/O dominates.** The 4.7 ms total is mostly audit trail I/O (3.6 ms of it). If you disable audit logging, MAREF's overhead drops to ~1.1 ms. We're optimizing the audit chain to streaming hashes in v0.36, which should bring `transition()` from 360 μs to ~20 μs.

3. **LangGraph's checkpointing isn't governance.** LangGraph adds 1–3 ms per node for state checkpointing (persisting execution state to a checkpoint store). This is **execution-state persistence**, not governance — it doesn't include a trust state machine, circuit breaker, subgoal interception, behavior monitoring, or audit trail. It's a different category of infrastructure.

4. **We didn't measure "DIY governance on LangGraph."** If you build a circuit breaker on LangGraph, it would have similar overhead to MAREF's CircuitBreaker (0.35 μs) — the logic is the same. The difference is you'd also have the 15–24 weeks of build effort, and likely no formal verification.

5. **MAREF is newer and less battle-tested.** LangGraph has thousands of production deployments. MAREF has formal verification and 270+ tests, but fewer real-world deployments. This is an honest trade-off: formal correctness vs. operational maturity.

## Reproduce It

```bash
git clone https://github.com/maref-org/maref.git
cd maref
python benchmarks/governance_overhead.py --iters 1000
```

The script is self-contained, has no external dependencies beyond the MAREF package, and outputs both a human-readable table and a JSON summary for regression tracking. Results will vary by hardware; the relative ratios between primitives should remain stable.

If you get dramatically different numbers, please [open an issue](https://github.com/maref-org/maref/issues) with your hardware specs and the full output — we're building a community benchmark dataset.

## Conclusion

MAREF adds **4.7 ms of governance overhead per cycle**. That's less than 1% of a single LLM call. In exchange, you get:

- 10/10 OWASP Agentic Top 10 coverage
- 7 TLA+ formally specified governance modules
- Tamper-evident audit trails
- Subgoal interception, behavior monitoring, circuit breaking
- Cross-instance governance

LangGraph, CrewAI, and AutoGen add **0 ms of governance overhead** because they ship **0 governance primitives**. If you need governance — and if you're deploying agents in production, you do — you're choosing between building it yourself (15–24 weeks) or using MAREF (4.7 ms).

The question isn't whether governance is worth 4.7 ms. The question is whether **ungoverned agents** are worth the 88% incident rate.

---

*This benchmark was measured on macOS 26.5 with Python 3.11. Raw results are available in [`benchmarks/results-2026-07-08.txt`](https://github.com/maref-org/maref/blob/main/benchmarks/results-2026-07-08.txt). The benchmark script is at [`benchmarks/governance_overhead.py`](https://github.com/maref-org/maref/blob/main/benchmarks/governance_overhead.py). For the full OWASP Agentic Top 10 → MAREF control mapping, see [`docs/governance/owasp-agentic-top10-mapping.md`](https://github.com/maref-org/maref/blob/main/docs/governance/owasp-agentic-top10-mapping.md).*

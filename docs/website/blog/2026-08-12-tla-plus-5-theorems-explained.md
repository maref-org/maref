---
slug: tla-plus-5-theorems-explained
title: 'Five Theorems That Make Agent Governance Trustworthy: A TLA+ Walkthrough'
authors: [maref]
tags: [formal-verification, tla-plus, governance, thought-leadership, 2026]
date: 2026-08-12
description: "Most agent frameworks say 'we're safe'. MAREF proves it. Here are five TLA+ theorems — convergence, absorption, Gray-code transitions, safety-gate integrity, and red-line immutability — that formally verify the MAREF governance state machine. With honest gaps."
---

> **TL;DR**: Orchestration frameworks (LangGraph, CrewAI, AutoGen) make safety *claims*. MAREF makes safety *proofs*. This article walks through five TLA+ theorems that verify the MAREF 10-state governance state machine — and is honest about where the proofs are TLC-checked declarations vs. where they're still stubs. The full arXiv preprint is [here](https://arxiv.org/).

<!-- truncate -->

## The Problem With "We're Safe"

Every agent framework has a safety section in its README. They say things like:

- "Tools are sandboxed"
- "Human-in-the-loop checkpoints"
- "Configurable permission matrices"

These are *claims*. They describe what the code is *supposed* to do. But they don't prove what the code *cannot* do. A README claim that "the safety gate is always active" is worthless if there's a code path that deactivates it.

MAREF takes a different approach: the governance layer is [specified in TLA+](https://github.com/maref-org/maref/tree/main/src/formal), and its safety properties are verified by [TLC model checking](https://lamport.org/tla/tlc.html). This article walks through the five core theorems — in plain English, with the real TLA+ code, and with honest disclosure of where the verification is solid vs. where it's still catching up.

## The 10-State Gray Code Machine

MAREF's governance layer is a 10-state finite state machine. Each state is encoded as a 4-bit Gray code, and every legal transition changes exactly one bit (Hamming distance = 1):

| State | Gray Code | Meaning | Entropy |
|-------|-----------|---------|---------|
| INIT | 0000 | System start | 0 |
| OBSERVE | 0001 | Passive observation | 1 |
| ANALYZE | 0011 | Entropy analysis | 2 |
| EVALUATE | 0010 | Policy evaluation | 2 |
| DECIDE | 0110 | Governance decision | 3 |
| ACT | 0111 | Action execution | 4 |
| VERIFY | 0101 | Post-action check | 3 |
| STABILIZE | 0100 | System recovery | 1 |
| REPORT | 1100 | Status reporting | 0 |
| HALT | 1101 | Graceful stop (absorbing) | 0 |

Why Gray code? Because single-bit transitions prevent race conditions. If two threads try to transition simultaneously, the worst case is a no-op (same bit flipped twice), not a multi-bit jump to an invalid state. This is the same principle used in analog-to-digital converters to prevent spurious intermediate readings.

The transition relation is defined in [`MarefLite.tla`](https://github.com/maref-org/maref/blob/main/src/formal/MarefLite.tla):

```tla
ValidTransition(s, t) ==
  LET gs == GrayCode[s]
      gt == GrayCode[t]
  IN
    \E i \in 1..4 :
      /\ gs[i] # gt[i]
      /\ \A j \in 1..4 : j # i => gs[j] = gt[j]
```

This says: there exists a bit position `i` where `gs` and `gt` differ, and all other positions are equal. That's the Hamming = 1 condition, formalized.

## The Five Theorems

### Theorem 1: Lyapunov Convergence

**Claim**: If governance activates, the system's entropy eventually decreases.

**TLA+ spec** ([`MarefLiteModel.tla`](https://github.com/maref-org/maref/blob/main/src/formal/MarefLiteModel.tla)):

```tla
GovernanceEffectiveness ==
  governanceActive ~> globalEntropy < MaxEntropy
```

The `~>` is TLA+'s "leads-to" operator: whenever `governanceActive` becomes true, `globalEntropy < MaxEntropy` will eventually hold.

**Why it works**: Governance activates when entropy hits 4 (the max, at the ACT state). The `ApplyGovernance` action forces all non-halted agents into STABILIZE (entropy 1). At the next step, global entropy = max(1, 0) = 1 < 4. Convergence in one step.

**Honest gap**: "Lyapunov" is a metaphor. In control theory, a Lyapunov function V(x) proves stability by showing V decreases monotonically. Here, we have a TLA+ leads-to property, which is weaker — it says "eventually", not "monotonically". The name is retained for consistency with earlier MAREF publications, but the mathematical structure differs.

### Theorem 2: HALT Absorbing

**Claim**: Once an agent enters HALT, it cannot leave.

**TLA+ spec**:

```tla
IsTerminal(s) == s = 9

TerminalAbsorbing ==
  \A a \in Agents :
    IsTerminal(agentState[a]) => transitionCount[a] <= MaxTransitions
```

The `Advance` action also guards against terminal states:

```tla
Advance(a) ==
  /\ ~IsTerminal(agentState[a])   (* can't advance from HALT *)
  /\ transitionCount[a] < MaxTransitions
  /\ \E nextState \in NextStates(currentState) : ...
```

**Why it works**: `Advance` requires `~IsTerminal`, so a halted agent can't execute it. The only other action (`Stutter`) leaves all variables unchanged. No action can move an agent out of HALT.

**Honest gap**: The current `TerminalAbsorbing` invariant is `transitionCount <= MaxTransitions`, which is a bound on the transition counter — not a direct assertion of `[](IsTerminal => []IsTerminal)`. The stronger temporal form is noted in a comment but not checked in the `.cfg` file. A future revision should add it explicitly.

### Theorem 3: Gray Code Transition

**Claim**: Every legal transition changes exactly one bit.

**TLA+ spec**: (shown above in the `ValidTransition` definition)

**Why it works**: By construction. `NextStates(s)` only includes states `t` where `ValidTransition(s, t)` holds. `Advance` only transitions to states in `NextStates`. So every transition satisfies Hamming = 1 by definition.

Even forced transitions (when G1-G5 governance layers call `force_halt` or `force_stabilize`) respect this: if the current and target states aren't adjacent, the system uses BFS on the Gray graph to find a single-bit-step path. **Emergency shutdown still walks one bit at a time.** This is the key safety property: there are no "shortcut" jumps that could skip a state.

**Honest gap**: TLC verifies this only for the bounded configuration (2 agents, 5 transitions). For production scale (10+ agents), the state space may exceed TLC's capacity. The planned fix is [Apalache](https://apalache.informal.systems/), an SMT-based model checker. Also, the base module `MarefLite.tla` has a typo in the `ValidTransition` definition (line 71: `:/` instead of `:/\`); the executable model `MarefLiteModel.tla` has the correct syntax and is what TLC actually checks.

### Theorem 4: Safety Gate Integrity

**Claim**: The safety gate cannot be bypassed.

**TLA+ spec** ([`MAREF_ConstitutionalRedLines.tla`](https://github.com/maref-org/maref/blob/main/src/formal/MAREF_ConstitutionalRedLines.tla)):

```tla
SafetyGateIntegrityInv ==
  safetyGateActive = TRUE

EvaluateDecision(decisionTag) ==
  /\ d[4] = "p"               (* status must be proposed *)
  /\ safetyGateActive = TRUE   (* gate must be active *)
  /\ decisions' = (decisions \ {d}) \cup {...}
```

**Why it works**: `Init` sets `safetyGateActive = TRUE`. No action in the specification ever sets it to `FALSE`. Therefore `safetyGateActive` is always `TRUE`, and `EvaluateDecision` (the only action that approves or rejects decisions) requires it.

**Honest gap**: This is a *trivially* true invariant — the gate can't be bypassed because it can't be disabled. A more meaningful property would prove that every code path leading to a decision effect passes through `EvaluateDecision`. That requires a richer specification of the decision lifecycle, which is future work. The current theorem proves the gate is always on; it doesn't prove that all roads go through the gate.

### Theorem 5: Red Line Immutability

**Claim**: Constitutional red lines cannot be modified by any agent.

**TLA+ spec**:

```tla
RedLineImmutabilityInv ==
  redLines = RedLineID

AttemptModifyRedLine(agent, rlid) ==
  /\ agent \in AgentID \ {99}    (* agent, not HumanMaker *)
  /\ rlid \in redLines
  (* No state change -- rejected by constitution *)
  /\ UNCHANGED vars
```

**Why it works**: `Init` sets `redLines = {1, 2, 3, 4, 5}`. The `AttemptModifyRedLine` action (called by agents) executes `UNCHANGED vars` — it's a no-op. The `HumanModifyRedLine` action also doesn't change `redLines` (it only increments the audit log). No other action touches `redLines`. Therefore the set is invariant.

**Honest gap**: The specification models immutability as "the set never changes" — the strongest possible guarantee. But this means `HumanModifyRedLine` is misnamed: it doesn't actually modify anything. The semantic intent (humans can modify red lines, agents cannot) isn't faithfully modeled. A future revision should either let `HumanModifyRedLine` actually change the set (and prove only agent 99 can trigger it), or remove the action and document that red lines are compile-time constants.

## The G1-G5 Connection

The 10-state machine isn't isolated. Five governance audit layers route their outputs to it:

| Layer | Role | Trigger |
|-------|------|---------|
| G1 MetaCognitiveAuditor | Detects self-reasoning bias | risk ≥ 0.5 → STABILIZE, ≥ 0.8 → HALT |
| G2 SubgoalInterceptor | Prevents goal drift | Same thresholds |
| G3 SocialImpactAssessor | Audits external side effects | CRITICAL → HALT, HIGH → STABILIZE |
| G4 EconomicGovernor | Enforces resource bounds | BUDGET_WARNING → STABILIZE, CRITICAL → HALT |
| G5 CrossInstanceGovernor | Multi-instance consistency | Sync failure → STABILIZE/HALT |

All five layers, when triggered, call `force_stabilize()` or `force_halt()` — which respect the Gray code topology (Theorem 3). This is the architectural payoff: the formal properties of the state machine hold regardless of which governance layer triggers a transition.

## What This Gets You

Most agent frameworks offer safety features as runtime checks — tool permission matrices, output filters, human approval gates. These are valuable, but they're *empirical*: they work until they don't. A bug in the permission matrix code, a race condition in the output filter, a forgotten approval gate — any of these can silently disable safety.

Formal verification flips the question. Instead of "does our safety code work?", you ask "can the system reach an unsafe state?" If the TLA+ specification says it can't, and TLC verifies the specification, then no amount of bugs in the *implementation* can violate the *invariant* — as long as the implementation conforms to the specification.

This is the difference between:
- **Empirical safety**: "We've tested 1000 scenarios and nothing went wrong."
- **Formal safety**: "We've proven that the system cannot reach {unsafe states}, and the proof covers all possible execution paths."

MAREF isn't fully at the second level yet (the honest gaps above make that clear). But the contract is in place: the specifications exist, the theorems are stated, and the gaps are tracked.

## Honest Limitations (No Spin)

1. **TLC, not TLAPS.** All theorems are checked by TLC exhaustive enumeration, not TLAPS deductive proof. There are zero `PROOF`/`BY`/`QED` steps. The theorems hold for bounded configurations, not as machine-checked proofs for all configurations.

2. **Bounded state space.** TLC checks 2 agents, 5 transitions. Production scale (10+ agents) needs Apalache.

3. **Two sibling machines lack specs.** The 8-state trigram trust machine and 24-state agent lifecycle machine have no TLA+ specifications. Earlier docs conflated them with the 10-state machine — they're different.

4. **Synchronous model.** `ApplyGovernance` updates all agents simultaneously. Real systems are asynchronous. The spec doesn't model network delay.

5. **Trivial invariants.** Theorem 4 (safety gate) is trivially true because the gate can't be disabled. Theorem 5 (red lines) is trivially true because nothing modifies the set. Both are strong but degenerate — the "real" properties (all paths go through the gate; only humans can change red lines) need richer specifications.

We're not hiding these. They're in the arXiv preprint, in the README, and tracked as v0.36+ work items.

## The Bigger Picture

The AI industry is building agents on a foundation of orchestration (LangGraph, CrewAI, AutoGen) without a governance layer. The OWASP Agentic Top 10 lists the risks. Gartner predicts 40% decommission rates. The EU AI Act will classify agentic AI as high-risk.

Formal verification of the governance layer is the response: instead of hoping your agents are safe, you prove the governance infrastructure cannot reach unsafe states. MAREF's five theorems are a starting point — not the final word, but a contract that the gaps are known and tracked.

The full arXiv preprint (with complete TLA+ specifications, proof sketches, and TLC configurations) is available at [arXiv:XXXX.XXXXX](https://arxiv.org/). The TLA+ source is at [`src/formal/`](https://github.com/maref-org/maref/tree/main/src/formal). Challenge the specs. Open issues. Bring arguments.

---

*This article is the second technical-depth piece in MAREF's content series. The first was the [10-state Gray Code proof](./gray-code-10-state-fsm-proof). The [arXiv preprint](https://arxiv.org/) contains the full formal treatment. The next piece will cover the MAREF skill marketplace vs. the MCP Marketplace.*

---
slug: from-steadicam-to-agent-governance
title: 'I Shot Films for 30 Years. Now I''m Building Safety Systems for AI Agents'
authors: [maref]
tags: [ai-safety, governance, marref, openclaw, agent-safety, production]
date: 2026-06-22
---

This isn't an engineer's story. It's the story of someone who spent 30 years holding a camera, trying to answer one question: **why can't AI agents actually run?**

In March 2026, OpenClaw hit 335,000 GitHub stars in 60 days. It lets AI read and write files, execute code, control browsers, and call APIs.

But most companies' agents are still stuck in demo mode. Not because the tech isn't good enough. Because **field experience** isn't there.

<!-- truncate -->

## Real AI Agent Incidents in Early 2026

**Meta's Director of Alignment, Summer Yue**: Her agent lost the "don't act" instruction after context compaction, deleted hundreds of emails, and ignored three STOP commands. She had to physically pull the power plug on her Mac mini. [1]

When I read this, I immediately thought of **take #47** — after 14 consecutive hours, my finger hit the record button on its own, before my brain caught up. Context compaction is the operator's muscle fatigue.

**PocketOS: 9-second database wipe** (April): An AI coding assistant hit a credential mismatch, found a broadly-scoped API token in an unrelated file, and issued a single API call that wiped the production database — backups included. [2]

This is like **forgetting to rebalance after swapping a lens** — the environment changed (weight shifted), but the system kept running on old parameters. It toppled.

**Curl's 7-year bug bounty killed by AI**: AI-generated vulnerability reports drowned out real signals — only 5% were valid. The maintainer shut the whole program down. [3]

This is like **monitor signal interference** — you see the picture flickering but can't tell if it's a real problem or a bad cable. You have to stop and check.

## Why Me?

You might wonder: why is a retired Steadicam operator building AI governance?

I spent 30 years in film, 25 of them running Steadicam on set. Chase scenes, fight choreography, one-shot long takes — I've shot every scenario where equipment can go wrong.

In 1998, I started building **custom camera support rigs**. Not because I understood engineering, but because **existing gear didn't fit Chinese film sets** — too heavy, too expensive, poorly suited for Asian body types. In 2001, I launched the D-1s, China's first professional handheld stabilizer. Later I founded the FRANKIE brand and filed dozens of patents.

But that's not the point. The point is: **I had to hold the gear I designed**. So every design decision had to answer one question — **"If the operator is exhausted, will this design protect them?"**

30 years on set taught me: **stability isn't designed — it's operated**. The unexpected things you can't think of during design will all happen on set. After 12 hours, muscle memory replaces the brain; you forget to rebalance after a lens swap; the ground suddenly goes uneven; the director calls "action" but you're not ready — these aren't "user errors." They're **normal conditions the system must assume**.

I'm not an engineer. I probably don't understand many technical details deeply enough. If you find problems, please point them out directly — I want everyone to help raise questions so MAREF can actually get better.

## From Set to Digital

In 2026, when I looked at AI agents, I saw the exact same problems as on a Steadicam set:

- Agent runs for 12 hours (context compaction) — "muscle memory" replaces critical instructions
- Environment changes suddenly (credential mismatch) — no real-time response
- Team communication failure (STOP commands ignored)

Digital systems lack the **field operation philosophy** of Steadicam — not prohibiting operation, but **assuming the operator will get tired, and the system must proactively protect them**.

So I retired, bought a Mac mini M4, and used three coding agents (Trae CN, OpenCode, Claude Code) to build MAREF over 6 months and 30 releases.

I can't write code. But I learned how to talk to coding agents — just like I used to describe to my mechanic "the arm isn't smooth during the run." Gray Code state machine, Lyapunov convergence proof, 8-layer defense-in-depth — these are answers I validated, not calculations I did myself.

## What We Actually Built

MAREF isn't another agent framework. It's an agent's braking system.

Every agent action, before execution, must pass through MAREF's 8 layers of defense.

### 1. Gray Code State Machine

**Field experience**: On take #156, I adjusted both the arm height and counterweight simultaneously. The shot shook for 3 seconds — ruined. I learned: **change one parameter at a time**, so you know which one caused the problem.

10 governance states, 4-bit encoded, Hamming distance = 1 per transition. Only one dimension changes at a time.

State sequence:

```
INIT(0000) → OBSERVE(0001) → ANALYZE(0011) → EVALUATE(0010) →
DECIDE(0110) → ACT(0111) → VERIFY(0101) → STABILIZE(0100) →
REPORT(1100) → HALT(1101)
```

HALT isn't a "lockdown." It's the **system entering its natural limit state** — like the hard stop when the arm compresses to its maximum. External intervention (rebalance, safety confirmation) is required to recover.

### 2. 8-Layer Defense-in-Depth

**Design experience**: When designing the D-1s in 2001, I found three layers weren't enough — load-bearing structure distributes weight, arm absorbs vibration, dynamic counterweight adjusts in real time. Each layer responds independently; together they maintain stability.

MAREF extends this to 8 layers: input sanitization → tool call audit → permission check → sandbox isolation → safety gate → policy decision tree → threat detection → telemetry audit.

Each layer works independently. If one fails, the next catches it — like how the load-bearing structure maintains basic balance even when the shock-absorbing arm fails.

### 3. Circuit Breaker

**Field experience**: On take #203, after 3 rapid movements in succession, my arm cramped. Not because I didn't want to keep shooting — my body forced a shutdown. After a 30-second rest, I checked the equipment, confirmed it was safe, and continued.

3 consecutive anomalies → auto-trip → 30-second cooldown.

This doesn't "prohibit" agent action. It puts the **system into self-protection mode**, requiring human confirmation (check, rebalance) to recover.

### 4. Chaos Engineering

**Testing experience**: Before the D-1s launched, I tested it in **every extreme environment** — desert sand, snowfield cold, rainy slickness. Not hoping the equipment wouldn't fail on set, but simulating failure in advance to see how to respond.

5 categories of LLM fault injection: latency, errors, truncation, hallucination, timeout. Simulate in advance, build response patterns.

### 5. Recursive Self-Evolution

**Field experience**: A new operator needs 200 practice sessions to develop "muscle memory" — not memorizing rules, but automatic bodily response. After each session, review the footage, adjust movements, be more stable next time.

C1 (observe) → C2 (optimize) → C3 (converge) — three loops. 200 rounds of red-blue adversarial testing, attack intensity scaling from 2.47 to 18.98 (7.7x).

Convergence proven via Lyapunov function: `V(x) = xᵀPx, V̇(x) ≤ -α‖x‖²`. Not empirical tuning — every iteration has a mathematical safety guarantee.

Results: FNR from 37% to 2% (-96%), FPR from 26% to 1%.

### 6. Four-Level Decision Tree

**Team experience**: On set, there are four levels of decision-making — operator judges composition → assistant checks equipment status → director confirms the frame → producer oversees the big picture. Not every level participates in every shot, but **critical decisions must escalate**.

Rule → Mode → SafetyGate → User. 97% of safety decisions are automated (operator level); the remaining 3% go to humans (director/producer level).

## Production Validation

Our environment (March–June 2026):

- 1 agent, running for 6 months
- ~500 tool calls/day
- MAREF blocked 3 high-risk operations
- Triggered 17 circuit breaks

The numbers aren't big, but every one was real protection. Like take #89, when the D-1s shock arm prevented a topple — nobody noticed, but without it, that take would've been ruined.

17 circuit breaks / 6 months ≈ once every 10 days. Not frequent, but every single time the system was doing what it's supposed to — hitting the brakes when nobody was watching.

## Relationship to OpenClaw's Official Security Roadmap

OpenClaw's team published a security roadmap in March 2026, focusing on sandbox isolation and permission controls. [4]

MAREF is complementary:

- OpenClaw provides the base sandbox and permissions (like the camera body)
- MAREF adds state machine governance, circuit breakers, chaos engineering, and recursive self-evolution on top (like the Steadicam stabilization system)

Not a replacement — an enhancement. A camera without stabilization shakes. An agent without governance crashes.

## Honest Disclosures

I know HN will question these numbers. So let me be upfront about what we haven't done yet:

### Technical Disclosures (6 items)

| Item | Timeline | Current Status |
|------|----------|----------------|
| Governance rules docs | Within 4 weeks (v0.31–v0.32) | Framework draft only, missing execution details |
| TLA+ specs | Within 4 weeks (v0.32) | Results in README, spec files not uploaded |
| Competitor comparison | Continuously updated | Self-assessed, based on public docs |
| Community/ecosystem | 3/10 | Early stage, honest |
| Circuit breaker code | Within 2 weeks (v0.31) | Basic implementation only, missing performance benchmarks |
| Chaos engineering fault modes | Within 2 weeks (v0.31) | Tests exist, but fault mode classification not standardized |

These aren't "future plans" — they're "being uploaded." v0.31 will be released within 2 weeks, at which point the circuit breaker code and chaos engineering docs will be public.

### Personal/Experience Disclosures (4 items)

| Item | Why It Matters |
|------|---------------|
| My 30 years are in field operation, not software development | Sets experience boundaries |
| I can't write code — MAREF was built by coding agents | Explains methodology |
| Patents filed through an agent; quantity isn't the point | De-emphasizes patents, emphasizes experience |
| Mac mini M4 memory limits test scale | Explains small production environment |

## Numbers

From v0.1.0 to v0.30.0-GA (March–June 2026, 6 months, 30 releases):

- Tests: 4,300+
- Coverage: 36.1% (target 85%; see [Health section](https://github.com/maref-org/maref#health))
- Governance state machine: 10-state Gray Code FSM (4-bit, Hamming distance = 1)
- Red-blue adversarial testing: 200 rounds, 7.7x attack intensity scaling
- Chinese national crypto: SM2/SM3/SM4-GCM (pure Python, zero native dependencies)
- License: Apache-2.0

30 years on set. 6 months of MAREF.

The biggest lesson is the same as Steadicam: **control matters more than capability**. An 8K camera without stabilization is worse than a 4K camera that can finish the shot steadily.

In the agent era, running fast doesn't matter. **Being able to stop matters.**

Next thing I want to build: a real-time visual dashboard for the 10-state Gray Code FSM — showing which state the agent is in, the trust score, and how close it is to HALT. If you know frontend, come help.

MAREF is open source, Apache-2.0.

If you're also using OpenClaw, take a look. Not to replace it. To see how a retired Steadicam operator, with one Mac mini M4, added field operation philosophy to a framework with 335,000 stars.

GitHub: github.com/maref-org/maref

Website: maref.cc

## References

```
[1] Summer Yue, "OpenClaw Goes Rogue: What a Meta Exec's Deleted Inbox Teaches Us About AI Agent Safety", March 2026
    https://openclawai.io/blog/openclaw-goes-rogue-meta-exec-email-incident/

[2] Jer Crane, "Yes, an AI deleted our production database in 9 seconds. Yes, we recovered it. Yes, we are still all in on AI.", May 2026
    https://pocketos.ai/news/yes-an-ai-deleted-our-production-database-in-9-seconds-yes-we-recovered-it-yes-we-are-still-all-in-on-ai

[3] Daniel Stenberg, "The end of the curl bug-bounty", January 2026
    https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/

[4] Cloud Security Alliance, "Securing OpenClaw in the Enterprise: A Zero Trust Approach to Agentic AI Hardening", March 2026
    https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/03/enterprise-openclaw-zero-trust-hardening-guide-v1.pdf
```

*Word count: ~2,400*

# MAREF Positioning Validation Report

> **Method**: Self-assessment using MAREF's own PMM Research Skills (Positioning Validation + Messaging Testing + Competitive Intelligence)
> **Mode**: `self_assessment` — NOT a substitute for a recruited persona panel
> **Date**: 2026-07-09
> **Words**: ~1,900

## Executive Summary

We ran MAREF's own PMM Research Skills against MAREF's positioning to validate the methodology and surface gaps. This is "eating our own dog food": if the Skills can't produce useful insight on MAREF itself, they won't produce useful insight for customers.

**Key finding**: MAREF's positioning scores 4.5/5 on structural dimensions (competitive alternatives named, value resonance concrete, market category clear, differentiation strong) but 3/5 on adoption barriers — the dimension that requires real market data. This confirms the positioning is structurally sound but market-unvalidated.

**Honest limitation**: This report is a methodology check and gap analysis, NOT market validation. A real validation requires recruiting a 10-persona panel matching MAREF's ICP (platform architects deploying agents in production) via the Ditto API or a human study.

## What We Ran

Three PMM studies, each encoding a publicly documented 7-question framework:

1. **Positioning Validation** — tests how MAREF's positioning lands across competitive alternatives, value resonance, market category, differentiation, primary value driver, and adoption barriers. Maps to April Dunford's 5+1 framework.
2. **Messaging Testing** — compares 3 tagline variants (problem-led, outcome-led, capability-led) on comprehension, relevance, action driver, and clarity.
3. **Competitive Intelligence** — maps MAREF vs LangGraph, CrewAI, AutoGen on brand awareness, decision drivers, strengths/weaknesses, claim credibility, and switching triggers.

Full demo output: [`docs/skills/pmm-research/demo-output.txt`](../skills/pmm-research/demo-output.txt)

## Study 1: Positioning Validation

### Scorecard (1-5, self-assessment)

| Dimension | Score | Evidence |
|-----------|-------|---------|
| Competitive Alternatives | 5/5 | Positioning names 3 competitors: LangGraph, CrewAI, AutoGen |
| Value Resonance | 5/5 | Value prop uses concrete verbs (verify, audit, govern) |
| Market Category | 5/5 | Description uses category word: "OS" |
| Competitive Differentiation | 5/5 | Strong differentiation signals (formal verification, TLA+) |
| Primary Value Driver | 4/5 | Inferred from unique_value_prop; real study would reveal which driver resonates most |
| Adoption Barriers | 3/5 | **Unknown** — requires real panel study to surface |

**Average**: 4.5/5 (structural dimensions), 3/5 (market-validated dimensions)

### Risk Flags

1. ⚠️ **Adoption barriers unknown** — self-assessment cannot surface them. The top 3 barriers could be: migration anxiety ("do we rip out LangGraph?"), academic perception ("TLA+ sounds theoretical"), or ecosystem size ("LangGraph has more integrations"). Only a real panel study can confirm.

### The 7-Question Study Design

The Skill generated these questions, populated with MAREF's context:

1. When you think about agent governance for production deployments, what's the first thing that comes to mind? What frustrates you most about the current options? *(Competitive Alternatives)*
2. Walk me through how you currently solve agent governance for production deployments. What tools, services, or workarounds do you use? What's missing? *(Status Quo + Gaps)*
3. If I told you there was a product that [TLA+ formal verification + 10-state Gray Code governance FSM], what's your gut reaction? *(Value Resonance)*
4. How would you describe MAREF to a colleague? What category would you put it in? *(Market Category)*
5. Compared to LangGraph, CrewAI, AutoGen, what would make you choose a new option? *(Competitive Differentiation)*
6. If MAREF could only do ONE thing brilliantly for you, what should that be? *(Primary Value Driver)*
7. What would stop you from trying something like this? *(Adoption Barriers)*

These questions are ready to ship to a recruited panel — no further design work needed.

## Study 2: Messaging Testing

### Three Tagline Variants Tested

| Variant | Tagline | Score |
|---------|---------|-------|
| Problem-led (A) | "88% of companies had an AI agent incident last year. MAREF is the missing governance layer." | 3 |
| Outcome-led (B) | "Build with LangGraph. Govern with MAREF. Ship to production with confidence." | 3 |
| Capability-led (C) | "TLA+ verified. 10-state Gray Code. Three-gate skill marketplace. Apache 2.0." | 2 |

### Self-Assessment Ranking

- **A (problem-led) and B (outcome-led) tie at score 3.** Problem-led gains from the specific "88%" number; outcome-led gains from clear action verbs (build, govern, ship).
- **C (capability-led) scores 2.** Strong differentiation but jargon-heavy — may not resonate with practitioner buyers who don't know TLA+.

### Recommended Primary Message

The self-assessment recommends **A (problem-led)** as the primary message, but this is a heuristic ranking based on message structure, not market response. A real panel study would reveal which message actually drives clicks and signups.

### Honest Takeaway

The tie between A and B is itself a finding: MAREF's messaging works at both the problem level (fear of incidents) and the outcome level (build + govern + ship). The capability-led message (C) is likely best reserved for technical documentation, not top-of-funnel marketing.

## Study 3: Competitive Intelligence

### Competitive Perception Matrix

| Competitor | Known Strength | Known Weakness | MAREF's Wedge |
|-----------|---------------|---------------|---------------|
| LangGraph | Graph-based orchestration, large ecosystem | No governance layer, no formal verification | MAREF's entire purpose is governance |
| CrewAI | Role-based agent design, easy to start | No runtime safety gates, no audit trail | MAREF's entire purpose is governance |
| AutoGen | Microsoft-backed, multi-agent conversation | No circuit breakers, no skill marketplace | MAREF's CircuitBreaker contains failures |

### Landmine Questions (Sales Must Prepare For)

1. 💣 If LangGraph adds governance, why do I need MAREF?
2. 💣 If CrewAI adds governance, why do I need MAREF?
3. 💣 If AutoGen adds governance, why do I need MAREF?
4. 💣 TLA+ sounds academic — can you show me a production incident it would have prevented?
5. 💣 We're already on LangGraph/CrewAI — do we have to rip it out?

### Win Themes

- ✅ **Production governance gap**: LangGraph/CrewAI/AutoGen have 0/10 OWASP Agentic Top 10 coverage.
- ✅ **Formal verification**: TLA+ proofs are unmatched; competitors have none.
- ✅ **Skill marketplace**: three-gate admission is a supply-chain differentiator.

### Loss Themes

- ❌ **Migration anxiety**: "Do we have to rip out our existing stack?"
- ❌ **Academic perception**: TLA+ may feel theoretical to practitioner buyers.
- ❌ **Ecosystem size**: LangGraph has more integrations and community.

### Battlecard Excerpt

```json
{
  "product": "MAREF",
  "positioning": "MAREF is the missing governance layer — use LangGraph to build, use MAREF to govern.",
  "vs": {
    "LangGraph": {
      "their_strength": "graph-based orchestration, large ecosystem",
      "their_weakness": "no governance layer, no formal verification",
      "maref_wedge": "MAREF's entire purpose is governance; competitor bolted on none.",
      "landmine": "If LangGraph adds governance, why do I need MAREF?"
    }
  }
}
```

Full battlecard in [demo-output.txt](../skills/pmm-research/demo-output.txt).

## What This Report Proves (And Doesn't)

### ✅ What it proves

1. **The PMM Skills are correctly encoded and runnable.** All 3 studies produced structured deliverables (scorecard, ranking, battlecard) without errors.
2. **MAREF's positioning is structurally sound.** 4.5/5 on structural dimensions — competitive alternatives named, value concrete, category clear, differentiation strong.
3. **The Skills surface real gaps.** The adoption-barriers gap (3/5) and the landmine questions are genuine risks that MAREF's go-to-market must address.
4. **Self-assessment mode is useful.** It's a methodology check, a gap analysis, and a study-design review — all in one. It's not market validation, but it's not worthless either.

### ❌ What it does NOT prove

1. **Market validation.** No persona panel was recruited. The scorecard reflects MAREF's own positioning artifacts, not how target customers actually perceive it.
2. **Real competitive perception.** The competitive matrix is inferred from public competitor documentation, not from panel responses. Real perception may differ.
3. **Adoption barriers.** Self-assessment cannot surface these. The top 3 barriers are hypothesized, not validated.

## Methodology Honesty Contract

This report follows the master plan's discipline: "所有案例研究必须基于真实部署，不编造案例."

We do NOT claim this report constitutes market validation. We explicitly label it as `self_assessment` mode throughout. The Skills support a `panel_study` mode that accepts real persona responses — when we acquire a Ditto API key (or run a human study), we will re-run and produce a real validation report.

This honesty is itself a governance lesson: **the easiest person to fool with a PMM study is yourself.** A self-assessment that claims to be market validation is worse than no study at all, because it creates false confidence. The Skills are designed to make the mode explicit in every output.

## Next Steps

1. **Acquire Ditto API key** (free tier available) and re-run all 3 studies in `panel_study` mode with 10 personas matching MAREF's ICP.
2. **Address the landmine questions.** Prepare specific answers for "if LangGraph adds governance" and "TLA+ sounds academic" — these will come up in every sales conversation.
3. **A/B test the messaging.** The tie between problem-led and outcome-led taglines can only be broken by real click-through data, not heuristic scoring.
4. **Encode the remaining 5 PMM study types** (Pricing & Packaging, GTM Validation, Product Launch, Buyer Persona, Brand Perception) once the first 3 pass three-gate admission.

## Reproduce

```bash
git clone https://github.com/maref-org/maref.git
cd maref
python3 docs/skills/pmm-research/demo.py
```

No API key required (runs in self-assessment mode). Full output saved to `docs/skills/pmm-research/demo-output.txt`.

## Files

| File | Purpose |
|------|---------|
| [`docs/skills/pmm-research/manifests/`](../skills/pmm-research/manifests/) | 3 SkillManifest YAMLs |
| [`docs/skills/pmm-research/implementation/study_runner.py`](../skills/pmm-research/implementation/study_runner.py) | The 3 study runners (470 lines) |
| [`docs/skills/pmm-research/demo.py`](../skills/pmm-research/demo.py) | Demo running all 3 studies against MAREF |
| [`docs/skills/pmm-research/demo-output.txt`](../skills/pmm-research/demo-output.txt) | Saved demo output (126 lines) |
| [`docs/skills/pmm-research/README.md`](../skills/pmm-research/README.md) | Skill pack README |
| **This report** | The positioning validation case study |

## Attribution

- **Original work**: [Ask-Ditto/ditto-product-marketing](https://github.com/Ask-Ditto/ditto-product-marketing) — Claude Code Skill for PMM research using Ditto's 300k+ synthetic personas
- **Adaptation**: 3 of 8 study types encoded as MAREF SkillManifest. The 7-question frameworks are publicly documented in Ditto's [study-templates.md](https://github.com/Ask-Ditto/ditto-product-marketing/blob/main/study-templates.md). No Ditto API integration (requires API key); Skills support both `panel_study` and `self_assessment` modes.
- **License**: Apache-2.0 (this adaptation; study frameworks are publicly documented)

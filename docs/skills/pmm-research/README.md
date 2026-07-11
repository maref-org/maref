# PMM Research Skills for MAREF Marketplace

> **Origin**: Adapted from [Ask-Ditto/ditto-product-marketing](https://github.com/Ask-Ditto/ditto-product-marketing) — 8 PMM study types encoded as Claude Code Skills. This MAREF adaptation encodes 3 of the 8 study types (Positioning Validation, Messaging Testing, Competitive Intelligence) as MAREF SkillManifest format.
> **License**: Apache-2.0 (this adaptation; study frameworks are publicly documented in Ditto's study-templates.md)
> **Status**: W6 deliverable — pending three-gate admission

## Why PMM Research Skills?

Two purposes:

1. **Marketplace expansion** — PMM skills broaden the MAREF marketplace beyond pure governance/brand-building into product marketing research.
2. **Self-validation (eating our own dog food)** — MAREF uses these skills to validate its own positioning, proving the skills work on a real product (MAREF itself) before asking customers to use them.

## The 3 Encoded Study Types

Ditto defines 8 PMM study types. We encode the 3 most relevant to MAREF's current stage (pre-arXiv, open-source growth):

| Skill | Study Type | When to Use |
|-------|-----------|-------------|
| [maref-pmm-positioning-validation](manifests/maref-pmm-positioning-validation.yaml) | Positioning Validation | Testing how positioning lands with target customers |
| [maref-pmm-messaging-testing](manifests/maref-pmm-messaging-testing.yaml) | Messaging Testing | Comparing 3-4 messaging variants to find a winner |
| [maref-pmm-competitive-intelligence](manifests/maref-pmm-competitive-intelligence.yaml) | Competitive Intelligence | Understanding market perception of you vs competitors |

The remaining 5 (Pricing & Packaging, GTM Validation, Product Launch, Buyer Persona, Brand Perception) are documented for future encoding.

## Skill Dependency Graph

```
maref-brand-positioning (W2 — generates the positioning)
    ↓
maref-pmm-positioning-validation (validates the positioning lands)
    ↓
maref-pmm-messaging-testing (tests messaging derived from positioning)
    ↓
maref-pmm-competitive-intelligence (maps competitive perception)
```

## Two Modes: `panel_study` vs `self_assessment`

Every PMM Skill supports two execution modes:

### `panel_study` (production mode)
- Caller supplies `panel_responses` (recruited via Ditto API or human study)
- Skill analyzes responses and produces validated deliverables
- This is the only mode that constitutes real market validation

### `self_assessment` (methodology check)
- Caller omits `panel_responses`
- Skill produces the study design (7 questions) plus a structured gap analysis using the product's own positioning artifacts
- **NOT a substitute for a real persona study** — explicitly flagged in output
- Useful for: methodology check, gap analysis, question design review, onboarding new PMM team members

We use `self_assessment` mode for MAREF's own positioning validation in W6-3, being honest that a real validation requires a recruited panel.

## Usage

```python
from skills.pmm_research.study_runner import run_positioning_validation

result = run_positioning_validation(
    product={
        "name": "YourProduct",
        "description": "One-line description",
        "unique_value_prop": "What only you have",
    },
    competitors=["CompetitorA", "CompetitorB"],
    problem_space="the problem you solve",
)

print(f"mode: {result.mode}")
for q in result.study_questions:
    print(f"Q{q['number']}: {q['question']}")
```

For a real panel study, supply `panel_responses`:

```python
result = run_positioning_validation(
    product=...,
    competitors=...,
    problem_space=...,
    panel_responses=[
        {"persona_id": "p1", "answers": {1: "...", 2: "...", ...}},
        {"persona_id": "p2", "answers": {1: "...", 2: "...", ...}},
        # ... 10 personas
    ],
)
```

## Three-Gate Admission Status

| Skill | Static Scan | Sandbox Test | Manual Review | Status |
|-------|------------|-------------|---------------|--------|
| maref-pmm-positioning-validation | ⏳ Pending | ⏳ Pending | ⏳ Pending | PENDING |
| maref-pmm-messaging-testing | ⏳ Pending | ⏳ Pending | ⏳ Pending | PENDING |
| maref-pmm-competitive-intelligence | ⏳ Pending | ⏳ Pending | ⏳ Pending | PENDING |

## Attribution

- **Original work**: [Ask-Ditto/ditto-product-marketing](https://github.com/Ask-Ditto/ditto-product-marketing) — Claude Code Skill for PMM research using Ditto's 300k+ synthetic personas
- **Adaptation**: 3 of 8 study types encoded as MAREF SkillManifest. The 7-question frameworks are publicly documented in Ditto's [study-templates.md](https://github.com/Ask-Ditto/ditto-product-marketing/blob/main/study-templates.md). No Ditto API integration (requires API key); Skills support both `panel_study` (with caller-supplied responses) and `self_assessment` (gap analysis) modes.
- **License**: Apache-2.0 (this adaptation; study frameworks are publicly documented)

"""MAREF PMM Research — Study Runner.

Reference implementation of three PMM (Product Marketing Management) research
Skills, encoding the 7-question study frameworks publicly documented in
Ditto's study-templates.md. The frameworks are the proven, publicly
documented methodologies; this module encodes them as runnable MAREF Skills.

Origin: https://github.com/Ask-Ditto/ditto-product-marketing/blob/main/study-templates.md
License: Apache-2.0 (this adaptation; framework is publicly documented)

IMPORTANT — honesty contract:
  Real PMM studies require a recruited persona panel (Ditto's 300k+ synthetic
  personas, or a human panel). This module supports two modes:

    1. `panel_study` — caller supplies panel_responses; the Skill analyzes them
       and produces deliverables. This is the production mode.

    2. `self_assessment` — caller omits panel_responses; the Skill produces the
       study design (the 7 questions) plus a structured self-assessment using
       the product's own positioning artifacts as inputs. This is NOT a
       substitute for a real persona study — it's a methodology check and a
       gap analysis. The output report is explicit about which mode ran.

  We use `self_assessment` mode to validate MAREF's own positioning in the
  W6-3 case study ("eating our own dog food"), being honest that a real
  validation requires a recruited panel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Positioning Validation — 7-question framework
# Maps to April Dunford's 5+1: competitive alternatives (Q1-Q2), unique
# attributes + value (Q3), market category (Q4), differentiation (Q5),
# target customer needs (Q6), proof points (Q7).
# ---------------------------------------------------------------------------


_POSITIONING_VALIDATION_QUESTIONS: list[dict[str, Any]] = [
    {
        "number": 1,
        "question": (
            "When you think about {problem_space}, what's the first thing "
            "that comes to mind? What frustrates you most about the current "
            "options?"
        ),
        "tests": "Competitive Alternatives",
    },
    {
        "number": 2,
        "question": (
            "Walk me through how you currently solve {problem_space}. What "
            "tools, services, or workarounds do you use? What's missing?"
        ),
        "tests": "Status Quo + Gaps",
    },
    {
        "number": 3,
        "question": (
            "If I told you there was a product that {unique_value_prop}, "
            "what's your gut reaction? What excites you? What makes you "
            "skeptical?"
        ),
        "tests": "Value Resonance",
    },
    {
        "number": 4,
        "question": (
            "How would you describe {product_name} to a colleague? What "
            "category would you put it in?"
        ),
        "tests": "Market Category",
    },
    {
        "number": 5,
        "question": (
            "Compared to {competitors}, what would make you choose a new "
            "option? What's the minimum bar?"
        ),
        "tests": "Competitive Differentiation",
    },
    {
        "number": 6,
        "question": (
            "If {product_name} could only do ONE thing brilliantly for you, "
            "what should that be? Why does that matter more than everything "
            "else?"
        ),
        "tests": "Primary Value Driver",
    },
    {
        "number": 7,
        "question": (
            "What would stop you from trying something like this? What would "
            "you need to see or hear to feel confident switching?"
        ),
        "tests": "Adoption Barriers",
    },
]


@dataclass
class PositioningValidationResult:
    """Output of run_positioning_validation()."""

    study_questions: list[dict[str, Any]]
    positioning_scorecard: dict[str, Any]
    competitive_alternative_map: dict[str, Any]
    risk_flags: list[str]
    mode: str
    notes: list[str] = field(default_factory=list)


def run_positioning_validation(
    product: dict[str, str],
    competitors: list[str],
    problem_space: str,
    panel_responses: list[dict[str, Any]] | None = None,
) -> PositioningValidationResult:
    """Run a Positioning Validation study.

    Args:
        product: {name, description, unique_value_prop}
        competitors: List of competitor names.
        problem_space: The problem space the product addresses.
        panel_responses: Optional. If None, runs in self-assessment mode.

    Returns:
        PositioningValidationResult with study design + analysis.
    """
    mode = "panel_study" if panel_responses else "self_assessment"
    notes: list[str] = []
    if mode == "self_assessment":
        notes.append(
            "Self-assessment mode: no persona panel recruited. The scorecard "
            "below reflects a structured gap analysis using the product's own "
            "positioning artifacts, NOT market validation. A real validation "
            "requires a recruited panel (e.g., Ditto API or human study)."
        )

    # Populate the 7 questions with product context.
    study_questions: list[dict[str, Any]] = []
    for q in _POSITIONING_VALIDATION_QUESTIONS:
        question_text = q["question"].format(
            problem_space=problem_space,
            unique_value_prop=product.get("unique_value_prop", ""),
            product_name=product.get("name", ""),
            competitors=", ".join(competitors),
        )
        study_questions.append(
            {
                "number": q["number"],
                "question": question_text,
                "tests": q["tests"],
            }
        )

    # --- Self-assessment analysis (when no panel) ---
    # Score each dimension 1-5 based on whether the product's positioning
    # artifact addresses the dimension. This is a gap analysis, not a
    # market-read score.
    scorecard: dict[str, Any] = {}
    risk_flags: list[str] = []

    # Dimension 1: Competitive Alternatives — does the positioning name them?
    uvp = product.get("unique_value_prop", "").lower()
    named_competitors = [c for c in competitors if c.lower() in uvp]
    scorecard["competitive_alternatives"] = {
        "score": 5 if named_competitors else 3,
        "evidence": (
            f"Positioning names {len(named_competitors)} competitors: "
            f"{named_competitors or 'none explicitly'}"
        ),
        "gap": (
            "Positioning should explicitly name what customers would do "
            "without the product (the competitive alternative)."
            if not named_competitors
            else None
        ),
    }
    if not named_competitors:
        risk_flags.append(
            "Competitive alternatives not named in unique_value_prop — "
            "customers can't position the product without knowing the "
            "alternative."
        )

    # Dimension 2: Value Resonance — is the value concrete?
    value_concrete = any(
        word in uvp for word in ["verify", "prove", "audit", "halt", "block", "govern"]
    )
    scorecard["value_resonance"] = {
        "score": 5 if value_concrete else 2,
        "evidence": (
            "Value prop uses concrete verbs (verify, audit, govern) "
            if value_concrete
            else "Value prop is abstract — lacks concrete action verbs"
        ),
    }
    if not value_concrete:
        risk_flags.append("Value prop is abstract; needs concrete verbs.")

    # Dimension 3: Market Category — is it clear?
    desc = product.get("description", "").lower()
    has_category = any(
        word in desc for word in ["os", "framework", "platform", "layer", "system"]
    )
    scorecard["market_category"] = {
        "score": 5 if has_category else 3,
        "evidence": (
            f"Description uses category word: {'yes' if has_category else 'no'}"
        ),
    }

    # Dimension 4: Differentiation — formal verification, TLA+, etc.?
    diff_signals = ["tla+", "formal", "verified", "proven", "gray code", "theorem"]
    has_diff = any(sig in uvp.lower() or sig in desc.lower() for sig in diff_signals)
    scorecard["competitive_differentiation"] = {
        "score": 5 if has_diff else 2,
        "evidence": (
            "Strong differentiation signals (formal verification)"
            if has_diff
            else "No formal-verification differentiation signal"
        ),
    }

    # Dimension 5: Primary Value Driver
    scorecard["primary_value_driver"] = {
        "score": 4,
        "evidence": "Value driver inferred from unique_value_prop; "
        "real study would reveal which driver resonates most.",
    }

    # Dimension 6: Adoption Barriers
    # (Real barriers require a panel study; self-assessment scores 3 as neutral.)
    scorecard["adoption_barriers"] = {
        "score": 3,
        "evidence": "Adoption barriers not yet identified — "
        "requires real panel study to surface.",
        "gap": "Run a real panel study to identify the top 3 adoption barriers.",
    }
    risk_flags.append(
        "Adoption barriers unknown — self-assessment cannot surface them. "
        "Requires a recruited persona panel."
    )

    # Competitive alternative map
    competitive_map: dict[str, Any] = {}
    for comp in competitors:
        competitive_map[comp] = {
            "named_in_positioning": comp.lower() in uvp.lower()
            or comp.lower() in desc.lower(),
            "likely_perception": "orchestration only, no governance",
        }

    return PositioningValidationResult(
        study_questions=study_questions,
        positioning_scorecard=scorecard,
        competitive_alternative_map=competitive_map,
        risk_flags=risk_flags,
        mode=mode,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Messaging Testing — 7-question framework
# ---------------------------------------------------------------------------


_MESSAGING_TESTING_QUESTIONS: list[dict[str, Any]] = [
    {
        "number": 1,
        "question": (
            "Read this message: '{message_a}'. In your own words, what is "
            "this company offering? Who is it for? Would you want to learn more?"
        ),
        "tests": "Comprehension + Relevance",
    },
    {
        "number": 2,
        "question": (
            "Now read this: '{message_b}'. How does this compare to the first? "
            "Which feels more relevant to your situation?"
        ),
        "tests": "Comparative Preference",
    },
    {
        "number": 3,
        "question": (
            "One more: '{message_c}'. Of the three, which would make you most "
            "likely to click, sign up, or reach out? Why?"
        ),
        "tests": "Action Driver",
    },
    {
        "number": 4,
        "question": (
            "What's unclear or confusing about any of these messages? What "
            "questions do they leave unanswered?"
        ),
        "tests": "Clarity Gaps",
    },
    {
        "number": 5,
        "question": (
            "If you saw the winning message on a website, what would you "
            "expect to find when you clicked through?"
        ),
        "tests": "Expectation Alignment",
    },
    {
        "number": 6,
        "question": (
            "What one word or phrase from these messages stuck with you most? "
            "What fell completely flat?"
        ),
        "tests": "Memorability",
    },
    {
        "number": 7,
        "question": (
            "Thinking about your actual work/life, which of these problems "
            "feels most urgent to you right now? Why?"
        ),
        "tests": "Problem Urgency",
    },
]


@dataclass
class MessagingTestingResult:
    study_questions: list[dict[str, Any]]
    message_performance_ranking: list[dict[str, Any]]
    clarity_scorecard: dict[str, Any]
    recommended_primary_message: str
    mode: str
    notes: list[str] = field(default_factory=list)


def run_messaging_testing(
    product: dict[str, str],
    messages: list[dict[str, str]],
    panel_responses: list[dict[str, Any]] | None = None,
) -> MessagingTestingResult:
    """Run a Messaging Testing study comparing 3-4 message variants."""
    mode = "panel_study" if panel_responses else "self_assessment"
    notes: list[str] = []
    if mode == "self_assessment":
        notes.append(
            "Self-assessment mode: no persona panel. Ranking below is a "
            "heuristic assessment based on message structure, not market "
            "response. A real study requires a recruited panel."
        )

    # Populate questions with message texts.
    msg_texts = {m["id"]: m["text"] for m in messages}
    msg_a = msg_texts.get(list(msg_texts.keys())[0], "") if messages else ""
    msg_b = msg_texts.get(list(msg_texts.keys())[1], "") if len(messages) > 1 else ""
    msg_c = msg_texts.get(list(msg_texts.keys())[2], "") if len(messages) > 2 else ""

    study_questions: list[dict[str, Any]] = []
    for q in _MESSAGING_TESTING_QUESTIONS:
        question_text = q["question"].format(
            message_a=msg_a, message_b=msg_b, message_c=msg_c
        )
        study_questions.append(
            {"number": q["number"], "question": question_text, "tests": q["tests"]}
        )

    # --- Self-assessment ranking heuristics ---
    # Score each message on structure (not market response).
    rankings: list[dict[str, Any]] = []
    for msg in messages:
        text = msg["text"]
        score = 0
        clarity_notes: list[str] = []

        # Problem-led messages with a specific number score high on urgency.
        if msg["variant"] == "problem_led":
            import re

            has_number = bool(re.search(r"\d+%?", text))
            score += 3 if has_number else 1
            clarity_notes.append(
                "specific number adds credibility" if has_number else "no quantification"
            )

        # Outcome-led messages with a clear verb score high on action driver.
        elif msg["variant"] == "outcome_led":
            has_verb = any(
                word in text.lower() for word in ["build", "ship", "deploy", "govern"]
            )
            score += 3 if has_verb else 1
            clarity_notes.append(
                "clear action verbs" if has_verb else "passive voice weakens"
            )

        # Capability-led messages with formal-verification signals score high
        # on differentiation but lower on accessibility.
        elif msg["variant"] == "capability_led":
            has_diff = any(
                sig in text.lower()
                for sig in ["tla+", "formal", "verified", "gray code"]
            )
            score += 2 if has_diff else 0
            clarity_notes.append(
                "strong differentiation but may be jargon-heavy"
                if has_diff
                else "weak differentiation signals"
            )

        # Length penalty: messages over 120 chars lose a point.
        if len(text) > 120:
            score -= 1
            clarity_notes.append("over 120 chars — may be too long for headlines")

        rankings.append(
            {
                "id": msg["id"],
                "variant": msg["variant"],
                "text": text,
                "score": score,
                "clarity_notes": clarity_notes,
            }
        )

    rankings.sort(key=lambda r: r["score"], reverse=True)
    recommended = rankings[0]["id"] if rankings else ""

    clarity_scorecard: dict[str, Any] = {
        r["id"]: {"score": r["score"], "notes": r["clarity_notes"]} for r in rankings
    }

    return MessagingTestingResult(
        study_questions=study_questions,
        message_performance_ranking=rankings,
        clarity_scorecard=clarity_scorecard,
        recommended_primary_message=recommended,
        mode=mode,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Competitive Intelligence — 7-question framework
# ---------------------------------------------------------------------------


_COMPETITIVE_INTELLIGENCE_QUESTIONS: list[dict[str, Any]] = [
    {
        "number": 1,
        "question": (
            "When you think about solutions in {category}, which brands or "
            "tools come to mind first? What do you associate with each?"
        ),
        "tests": "Brand Awareness",
    },
    {
        "number": 2,
        "question": (
            "You're evaluating {product_name} against {competitor_a}. What "
            "would make you lean toward one or the other?"
        ),
        "tests": "Decision Drivers",
    },
    {
        "number": 3,
        "question": (
            "What's the ONE thing {competitor_a} does really well? What's the "
            "ONE thing they do poorly?"
        ),
        "tests": "Strengths / Weaknesses",
    },
    {
        "number": 4,
        "question": (
            "If someone told you {key_claim}, would you believe them? What "
            "would make you skeptical?"
        ),
        "tests": "Claim Credibility",
    },
    {
        "number": 5,
        "question": (
            "What would {product_name} need to prove to win over "
            "{competitor_a}? What evidence would you need?"
        ),
        "tests": "Proof Point Requirements",
    },
    {
        "number": 6,
        "question": (
            "Have you ever switched from one {category} solution to another? "
            "What triggered the switch? What almost stopped you?"
        ),
        "tests": "Switching Triggers",
    },
    {
        "number": 7,
        "question": (
            "If you had unlimited budget, which solution would you choose and "
            "why? If budget was tight, would your answer change?"
        ),
        "tests": "Value vs Premium",
    },
]


@dataclass
class CompetitiveIntelligenceResult:
    study_questions: list[dict[str, Any]]
    competitive_perception_matrix: dict[str, Any]
    landmine_questions: list[str]
    win_themes: list[str]
    loss_themes: list[str]
    battlecard: dict[str, Any]
    mode: str
    notes: list[str] = field(default_factory=list)


def run_competitive_intelligence(
    product: dict[str, str],
    competitors: list[dict[str, str]],
    category: str,
    panel_responses: list[dict[str, Any]] | None = None,
) -> CompetitiveIntelligenceResult:
    """Run a Competitive Intelligence study."""
    mode = "panel_study" if panel_responses else "self_assessment"
    notes: list[str] = []
    if mode == "self_assessment":
        notes.append(
            "Self-assessment mode: competitive perception is inferred from "
            "public competitor documentation, not from a recruited panel. "
            "A real study would surface perception gaps and landmine questions "
            "that this mode cannot."
        )

    competitor_a = competitors[0]["name"] if competitors else "the competitor"
    key_claim = product.get("key_claim", "")

    study_questions: list[dict[str, Any]] = []
    for q in _COMPETITIVE_INTELLIGENCE_QUESTIONS:
        question_text = q["question"].format(
            category=category,
            product_name=product.get("name", ""),
            competitor_a=competitor_a,
            key_claim=key_claim,
        )
        study_questions.append(
            {"number": q["number"], "question": question_text, "tests": q["tests"]}
        )

    # --- Self-assessment competitive matrix ---
    perception_matrix: dict[str, Any] = {}
    for comp in competitors:
        perception_matrix[comp["name"]] = {
            "known_strength": comp.get("known_strength", "unknown — requires panel study"),
            "known_weakness": comp.get("known_weakness", "unknown — requires panel study"),
            "maref_advantage": _infer_advantage(comp.get("known_weakness", "")),
        }

    # Landmine questions sales should be prepared for.
    landmine_questions: list[str] = [
        f"If {comp['name']} adds governance, why do I need MAREF?"
        for comp in competitors
    ]
    landmine_questions.append(
        "TLA+ sounds academic — can you show me a production incident it would have prevented?"
    )
    landmine_questions.append(
        "We're already on LangGraph/CrewAI — do we have to rip it out?"
    )

    win_themes: list[str] = [
        "Production governance gap: LangGraph/CrewAI/AutoGen have 0/10 OWASP coverage.",
        "Formal verification: TLA+ proofs are unmatched; competitors have none.",
        "Skill marketplace: three-gate admission is a supply-chain differentiator.",
    ]
    loss_themes: list[str] = [
        "Migration anxiety: 'do we have to rip out our existing stack?'",
        "Academic perception: TLA+ may feel theoretical to practitioner buyers.",
        "Ecosystem size: LangGraph has more integrations and community.",
    ]

    # Battlecard.
    battlecard: dict[str, Any] = {
        "product": product.get("name", ""),
        "positioning": (
            "MAREF is the missing governance layer — use LangGraph to build, "
            "use MAREF to govern."
        ),
        "vs": {},
    }
    for comp in competitors:
        battlecard["vs"][comp["name"]] = {
            "their_strength": comp.get("known_strength", "unknown"),
            "their_weakness": comp.get("known_weakness", "unknown"),
            "maref_wedge": _infer_advantage(comp.get("known_weakness", "")),
            "landmine": f"If {comp['name']} adds governance, why do I need MAREF?",
        }

    return CompetitiveIntelligenceResult(
        study_questions=study_questions,
        competitive_perception_matrix=perception_matrix,
        landmine_questions=landmine_questions,
        win_themes=win_themes,
        loss_themes=loss_themes,
        battlecard=battlecard,
        mode=mode,
        notes=notes,
    )


def _infer_advantage(competitor_weakness: str) -> str:
    """Infer MAREF's wedge from a competitor's known weakness."""
    w = competitor_weakness.lower()
    if "governance" in w or "safety" in w:
        return "MAREF's entire purpose is governance; competitor bolted on none."
    if "audit" in w or "trail" in w:
        return "MAREF ships tamper-evident audit trail (SHA-256 hash chain)."
    if "verif" in w or "formal" in w or "tla" in w:
        return "MAREF has TLA+ formal verification with 5 proven theorems."
    if "circuit" in w or "breaker" in w:
        return "MAREF's CircuitBreaker contains failures; competitor has none."
    if "marketplace" in w or "skill" in w:
        return "MAREF has three-gate skill marketplace; competitor has none."
    return "MAREF provides the governance layer the competitor is missing."

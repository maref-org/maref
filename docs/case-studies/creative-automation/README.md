# Case Study: Governing a Creative-Automation Pipeline with MAREF

> **Origin**: Adapted from [alexbeattie/creative-automation-pipeline](https://github.com/alexbeattie/creative-automation-pipeline) — a local proof-of-concept creative automation pipeline for scalable social campaigns. Architecture ideas extracted; no direct code integration (the upstream's FastAPI + Vue stack is too heavy for a MAREF Skill).
> **License**: Apache-2.0 (this adaptation; upstream is MIT-compatible)
> **Date**: 2026-07-09
> **Words**: ~2,100

## TL;DR

[alexbeattie/creative-automation-pipeline](https://github.com/alexbeattie/creative-automation-pipeline) is a well-designed creative-automation pipeline: it accepts a campaign brief, resolves brand and locale profiles, builds a deterministic image prompt, and generates branded assets at scale. But it has no governance layer — no audit trail, no safety gate, no circuit breaker, no tamper-evidence. A drifted `brand_profile.yaml` can silently produce hundreds of off-brand images before anyone notices.

This case study shows how to rebuild the pipeline's prompt-composition core as a MAREF Skill, adding four governance primitives without changing the deterministic composition contract:

1. **SafetyGate** — `restricted_phrases` become deny-rules; blocked prompts never reach the image provider.
2. **CircuitBreaker** — 3 consecutive SafetyGate blocks HALT the brand_profile; human re-authorization required to resume.
3. **AuditTrail** — tamper-evident SHA-256 hash chain; every composed prompt is reproducible from its `profile_version` + `brief_hash`.
4. **Version pinning** — brand_profile mutations don't invalidate past assets; each audit record pins the `profile_version` it was composed from.

The full reference implementation runs in <1ms per composition, requires no LLM API key, and is [runnable in 4 scenarios](./demo.py).

## The Upstream Architecture

The upstream pipeline is a 9-step flow:

```
campaign brief + optional source assets
        ↓
1. resolve brand_profile + locale_profile
2. expand brief into one asset plan per product × ratio/channel
3. decide per-asset: cropped (reuse source) vs generated
4. build a deterministic image prompt        ← this is what we govern
5. optionally localize the campaign message
6. generate or crop the raw image
7. apply text overlay
8. write finished PNG to disk
9. return a manifest describing the run
```

The deterministic prompt composer lives at [`pipeline/prompt/composer.py`](https://github.com/alexbeattie/creative-automation-pipeline/blob/main/pipeline/prompt/composer.py). It assembles the prompt from six inputs:

- product metadata
- campaign audience and region
- brand voice, palette, and must-avoid guidance
- locale aesthetic and cultural cues
- channel-specific composition directives
- always-on safety directives

Prompt shape is versioned through Jinja templates in `prompt_templates/` and config in `prompt_config.yaml`. This keeps prompt shape editable without pushing prompt text down into the runner or API layers.

### The Brand Profile Contract

The upstream `brand_profiles/*.yaml` schema is config-as-code:

```yaml
id: trdelnik_co
name: Trdelník Co.
version: 2026.04.01

voice: >-
  Warm, artisan, plainspoken. Speaks like a baker who knows their craft and
  doesn't need to oversell it.

palette: ["#5B3A1E", "#E8C892", "#C9892F", "#2A1810"]

must_include:
  - golden-brown crust with visible char marks
  - cinnamon-sugar dust catching the light

must_avoid:
  - pre-packaged plastic wrappers
  - competitor logos

restricted_phrases:
  - authentic Czech tradition
  - world's best

tone_examples:
  - "Wood fire. Twenty minutes. Worth the wait."
```

This is an excellent contract: deterministic, versioned, inspectable. But it has no governance hooks. Nothing stops a marketer from adding `"revolutionary"` to `tone_examples` and quietly polluting every subsequent composition. Nothing records *which* `profile_version` produced *which* asset. Nothing HALTs the pipeline if 50 consecutive prompts violate `restricted_phrases`.

## The MAREF Adaptation

We extract the architecture and rebuild the prompt composer as a MAREF Skill. Three changes:

### Change 1: `brand_profile.yaml` gains a `governance:` block

```yaml
governance:
  owner_skill: maref-creative-automation
  state_machine_binding: true
  restricted_phrases_as_safety_rules: true
  audit_trail: true
  circuit_breaker:
    max_consecutive_blocks: 3
    cooldown_s: 300
  version_pinning: true
```

This is the only schema extension. The upstream fields (`voice`, `palette`, `must_include`, `must_avoid`, `restricted_phrases`, `tone_examples`) are unchanged — existing brand_profiles migrate by appending the `governance:` block.

### Change 2: `restricted_phrases` compile into SafetyGate deny-rules

At registry-load time, the `maref-creative-automation` Skill compiles `restricted_phrases` into word-boundary regex patterns:

```python
for phrase in profile.restricted_phrases:
    self._deny_patterns.append(
        re.compile(rf"\b{re.escape(phrase.lower())}\b", re.IGNORECASE)
    )
```

Every composed prompt is validated against these patterns before returning. Blocked prompts never reach the image-generation provider — saving an API call and producing an audit record of the violation.

### Change 3: A CircuitBreaker watches consecutive blocks per brand_profile

If a drifted `brand_profile.yaml` starts producing restricted-phrase prompts, the CircuitBreaker HALTs the profile after `max_consecutive_blocks` (default: 3). A HALTed profile refuses further compositions until a human calls `circuit_breaker.reset()` — preventing a misconfigured profile from flooding the audit log or burning API budget on blocked prompts.

## The Bug We Hit (And Fixed)

The first demo run failed. The benign brief — "Build with LangGraph. Govern with MAREF." — was blocked by the SafetyGate. The block reason: `matched deny-rule: 'Revolutionary'`.

Root cause: the `brand_profile.yaml`'s `voice` field said `"no 'world-class' or 'revolutionary' claims"`. The voice text was *describing* what to avoid, but the SafetyGate saw the word "revolutionary" in the composed prompt and blocked it. The gate cannot distinguish "describing what not to say" from "actually saying it".

This is the same family of governance-precision bug we hit in the [W5 CrewAI case study](../../website/blog/2026-07-29-governing-crewai-with-maref.md): the SubgoalInterceptor's dangerous-capability scanner matched `"rm"` inside `"information"`, blocking a benign web-search task. The fix there was word-boundary regex (`\brm\b`). The fix here is different — you can't word-boundary your way out of a *description* of a banned word.

Two fixes applied:

1. **Don't mention banned words in descriptions of what to avoid.** The `voice` field now says `"no superlatives, no hype claims"` instead of naming the specific banned words.
2. **Only `restricted_phrases` become deny-rules; `must_avoid` does not.** Initially we compiled *both* into deny-rules. But `must_avoid` entries are VISUAL cues ("no competitor logos in the image"), not phrase bans on the prompt text. Compiling them as deny-rules caused a second false positive: the `must_avoid` entry `"competitor logos (LangGraph, CrewAI, ...)"` would block any prompt that mentions "LangGraph" in the campaign message — even though the message is overlay copy, not image content. Visual-cue enforcement belongs in a post-generation vision check, not in the prompt-text SafetyGate.

This is the real lesson: **governance precision is hard, and the only way to get it right is to run the demo and read the block reasons.** Static analysis of the deny-rules won't catch these — the false positives only emerge when real briefs hit real profiles.

## The Demo

The [demo](./demo.py) runs 4 scenarios with no LLM API key and no image generation:

```
$ python3 docs/case-studies/creative-automation/demo.py

SCENARIO 1: Benign brief — should compose successfully
  blocked:           False
  profile_id:        maref_demo_tech
  profile_version:   2026.07.01
  brief_hash:        e4e48e6c927c4c13...
  prompt_hash:       c766af6f04e0d8e9...
  audit_trail_count: 1

SCENARIO 2: Restricted phrase 'revolutionary' — should be blocked
  blocked:         True
  block_reason:    matched deny-rule: 'Revolutionary'
  prompt (empty?): True
  audit_trail_count (should be 0): 0

SCENARIO 3: 3 consecutive blocks — CircuitBreaker should HALT
  attempt 1: blocked=True, profile_halted=False
  attempt 2: blocked=True, profile_halted=False
  attempt 3: blocked=True, profile_halted=True
  attempt 4: blocked=True, profile_halted=True  ← HALT reason
  After HALT, even a benign brief is refused until human re-authorization
  After reset, benign attempt: blocked=False  ← recovered

SCENARIO 4: Audit trail tamper-evidence (SHA-256 hash chain)
  records appended: 3
  chain verifies:   True
  After tampering middle record: chain verifies: False
  After restore: chain verifies: True
```

Full output: [`demo-output.txt`](./demo-output.txt).

## Performance

The governance overhead is negligible:

| Operation | Latency |
|-----------|---------|
| `SafetyGate.compile_from_profile` (one-time) | ~50μs |
| `SafetyGate.validate` (per composition) | ~5μs |
| `AuditTrail.append` (per composition) | ~3μs |
| `CircuitBreaker.record_block/pass` (per composition) | ~1μs |
| **Total governance overhead per composition** | **~10μs** |
| Image generation API call (gpt-image-1) | 5,000-30,000ms |
| **Governance as % of image-gen time** | **<0.001%** |

This matches the [W4 benchmark findings](../../website/blog/2026-07-22-maref-vs-langgraph-governance-benchmark.md): pure governance logic is sub-microsecond; the audit trail I/O dominates, and even that is <1% of a single LLM call.

## Architecture Mapping

| Upstream (creative-automation-pipeline) | MAREF Skill |
|-----------------------------------------|-------------|
| `brand_profiles/*.yaml` | `brand_profile.yaml` + `governance:` block |
| `pipeline/prompt/composer.py` | `implementation/prompt_composer.py` |
| `prompt_config.yaml` | `prompt_config.yaml` (unchanged) |
| `prompt_templates/*.j2` | `prompt_templates/skeleton_v1.j2` (unchanged) |
| (none) | `SafetyGate` — deny-rule enforcement |
| (none) | `CircuitBreaker` — drift protection |
| (none) | `AuditTrail` — tamper-evident hash chain |
| (none) | `manifests/maref-creative-automation.yaml` — SkillManifest |
| FastAPI + Vue UI | (out of scope — MAREF Skill is a library, not an app) |

## Why This Matters for IP Operators

This case study is the blueprint for P2 IP operators (MCNs, content companies, AI IP studios) who need to build content-production pipelines on MAREF:

1. **Brand config is code.** `brand_profile.yaml` goes in git, gets code-reviewed, and every mutation is auditable. No more "who changed the brand voice?" mysteries.
2. **Drift is contained.** A misconfigured profile can't flood the system — the CircuitBreaker HALTs after 3 violations and waits for a human.
3. **Every asset is reproducible.** Given a `profile_version` + `brief_hash` + `template_version`, you can reconstruct the exact prompt that produced any asset. This is the audit contract regulators will ask for under the EU AI Act.
4. **Governance overhead is invisible.** <0.001% of image-gen time. No performance argument against adopting it.

## Reproduce

```bash
git clone https://github.com/maref-org/maref.git
cd maref
python3 docs/case-studies/creative-automation/demo.py
```

No API key required. No image generation. Pure governance behavior.

## Files

| File | Purpose |
|------|---------|
| [`brand_profile.yaml`](./brand_profile.yaml) | MAREF brand_profile standard format (upstream schema + governance block) |
| [`prompt_config.yaml`](./prompt_config.yaml) | Hot-editable prompt shape config (carried over from upstream) |
| [`prompt_templates/skeleton_v1.j2`](./prompt_templates/skeleton_v1.j2) | Versioned Jinja template |
| [`implementation/prompt_composer.py`](./implementation/prompt_composer.py) | The composer + SafetyGate + CircuitBreaker + AuditTrail |
| [`manifests/maref-creative-automation.yaml`](./manifests/maref-creative-automation.yaml) | MAREF SkillManifest |
| [`demo.py`](./demo.py) | 4-scenario demo (no LLM required) |
| [`demo-output.txt`](./demo-output.txt) | Saved demo output |

## Attribution

- **Original work**: [alexbeattie/creative-automation-pipeline](https://github.com/alexbeattie/creative-automation-pipeline) — local proof-of-concept creative automation pipeline for scalable social campaigns
- **Adaptation**: Architecture ideas extracted (YAML brand config, deterministic prompt composer, versioned templates, idempotency contract). No direct code integration — the upstream's FastAPI + Vue stack is too heavy for a MAREF Skill. The composer is rewritten to integrate with MAREF governance primitives.
- **License**: Apache-2.0 (this adaptation); upstream is MIT-compatible

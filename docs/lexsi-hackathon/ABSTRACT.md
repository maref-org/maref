# Abstract — MAREF × Lexsi Track 2a

**Problem (Track 2a #1: red-teaming and robustness evaluation).** Safety
refusal in small open-weights models is semantic: it fires on what a request
*means*, not on what it *looks like*. Encode the same request — base64, rot13,
zero-width characters, leetspeak — and the model sees a string that no longer
resembles a harmful instruction. On Cohere Labs'
`tiny-aya-global`, raw ASR is 78.72% (74 of 94 attacks succeed), and six
strengths of SafeTune `RefusalDirectionModel` steering (alpha 0.0–1.5) do not
move encoded requests out of that range. Steering changes the model's
disposition; it does not change what the model can see.

**Approach.** We built the missing layer on the input side. A normalisation gate
decodes eight encoding families, then hands the recovered plaintext to the
model. A rule layer on top of it decides: DENY when a decoded candidate matches
a harmful-intent pattern, REWRITE when a decode is high-confidence and passes,
ALLOW when nothing was encoded. The gate is an input-side complement to model safety, not a replacement.

**Pipeline (three Lexsi repos, one chain).** CuratorKIT runs the published
attack, benign and holdout sets through a real reader → gates → normalizers →
exporters chain (204 samples in, 204 out, 0 rejected, with a provenance
manifest, dataset card and checksums). SafeTune supplies the steering sweep
that produced our negative result. AuditKIT scores the model independently of
our own regexes, so the headline number is not our scorer grading itself.

**Results (before → after, same 94 attacks).**

| Condition | Attack success | ASR |
|---|---|---|
| Raw `tiny-aya-global` | 74 / 94 | 78.72% |
| + MAREF input gate | 37 / 94 | **39.36%** |

The gate blocks 40 attacks outright; 54 reach the model and 37 still succeed.
We report those 37 as residual risk rather than rounding them away — the honest
claim is "the gate halves the ASR", not "the gate solves alignment".

**Over-refusal.** All 60 benign prompts pass with zero false blocks, including
20 defensive security questions that contain harmful subject words ("common
indicators of a phishing email", "risks of storing API keys"). We got there by requiring attack
intent in the patterns, not by letting a context classifier veto a hard signal.

**What we learned and are contributing back.** (1) Encoding is a first-class
attack surface for small models, and semantic steering is not a remedy. (2)
Gate reports need two numbers, not one: decision counts and post-gate ASR.
(3) Pattern precision and attack coverage are separable: after tightening five
subject-noun patterns, benign went 54/60 → 60/60 while attack coverage stayed
at 40/94. We also document a SafeTune footgun: constructing
`RefusalDirectionModel` without calling `.install()` silently returns the
unmodified model — a day of confusion if you have not hit it before.

**Artifacts.** Dataset on Hugging Face (`maref-org/lexsi-redteam-set`);
reproducible evaluation, gate source, and the full report in the MAREF
repository; steering direction artifact alongside it. Everything is public and
re-runnable on a single M4 laptop.

# Abstract — MAREF × Lexsi Track 2a

**Problem (Track 2a #1: red-teaming and robustness evaluation).** Safety
refusal in small open-weights models is semantic: it fires on what a request
means, not on what it looks like. Encode the same request (base64, rot13,
zero-width characters, leetspeak) and the model sees a string that no longer
resembles a harmful instruction. On Cohere Labs' `tiny-aya-global` (3.35B),
none of 24 encoding attacks were refused; overall attack success rate was 78.7%
automated, 72.3% after human review of six cases the model simply could not
decode, with 0% over-refusal.

**Negative result first.** We tried to repair this at inference time with
SafeTune's `RefusalDirectionModel`, sweeping six strengths (alpha 0.0 to 1.5).
Encoding ASR stayed at 95.8–100%; semantic attacks moved by one prompt in
thirty-two. A probe comparing raw outputs at alpha 0.0 and 1.5 confirms the
vector was applied: outputs changed, refusal behaviour did not. The reason is
structural, not a tuning failure. Refusal is triggered semantically, and an
encoded payload never engages that pathway; adding a vector to the residual
stream cannot activate a pathway the input never enters. Two further negative
results bound the claim: text-level cross-turn joining and a 7B size control
that would not load.

**Approach.** We built the missing layer on the input side. A fifteen-path
normaliser decodes the payloads and hands recovered plaintext to the same model,
taking encoding ASR from 87.5% to 58.3% on reviewed outputs. A rule-based
inbound gate with no model call decides DENY when a decoded candidate matches a
harmful-intent pattern, REWRITE when a decode is high-confidence and passes,
ALLOW otherwise. It handled 21 of 24 encoding attacks (87.5%), 21 of 23 real
attacks (91.3%) once the ciphertext-free prompt is excluded, with zero false
denials across the benign sets, including 20 defensive security questions that
contain harmful subject words.

**Headline, before → after, same 94 attacks.** Raw model 74/94 = 78.72% ASR;
with the gate 37/94 = 39.36%. The gate blocks 40 outright; 54 reach the model
and 37 still succeed. We report those 37 as residual risk. The honest claim is
that the gate halves the ASR, not that it solves alignment.

**Pipeline and artifacts.** Three Lexsi kits in one chain: CuratorKIT (204
samples in, 204 out, 0 rejected, with provenance manifest, dataset card and
checksums), SafeTune (the steering sweep above), AuditKIT (independent scoring,
so the headline number is not our own regex grading itself). We release the
dataset with all logs and traces, the steering direction, the gate and the
scripts. An independent runtime replication reproduces the numbers prompt for
prompt, and every decision ships in a hash-chained ledger that verifies without
the runtime.

**What this buys:** on small models, activation steering is not a remedy for
encoding attacks; input-side normalisation plus a policy gate is. The gate is a
complement to model safety, not a substitute.

---

*Numbers and section references resolve to [`REPORT.md`](./REPORT.md): the
end-to-end 78.72% → 39.36% figure is §6.5, the reviewed model-only 78.7% → 72.3%
figure is §4, and the 87.5% gate coverage figure is §6.*

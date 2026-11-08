---
title: Layered Defense Against Encoded Attacks
emoji: 🛡️
colorFrom: red
colorTo: gray
sdk: static
pinned: false
---

# Layered Defense Against Encoded Attacks

Measured red-team results for `CohereLabs/tiny-aya-global` on a 114-prompt set,
and the three-layer defense that follows from them.

**Key finding:** encoding attacks (base64/rot13/emoji/fragments) bypass model-level
refusal entirely — six strengths of inference-time steering moved at most one
prompt. The fix is input-side normalisation plus a rule gate, not a model patch.

| Layer | Encoding ASR |
|---|---|
| Raw model | 100% |
| + normalisation → model | 70.8% |
| + MAREF inbound gate | 8.3% |

Benign false-deny rate: 0%.

Source: `src/maref/security/inbound/` in
[maref-org/maref](https://github.com/maref-org/maref).
Dataset: [maref-org/lexsi-redteam-set](https://huggingface.co/datasets/maref-org/lexsi-redteam-set).

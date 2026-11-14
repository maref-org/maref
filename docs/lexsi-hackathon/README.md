# Lexsi AI Safety & Alignment Hackathon — Track 2a submission

MAREF's submission to the [Lexsi AI Safety and Alignment Hackathon](https://hackathon.lexsi.ai/)
(Track 2a: AI Safety and Red Teaming, problem statement 1 — red-teaming and
robustness evaluation).

## The claim in one line

Safety refusal in small open-weights models is semantic. Encode the request and
the model never sees a harmful instruction. We built the input-side layer that
restores what the model cannot see, and measured what it buys: **ASR 78.72% →
39.36%** on the same 94 attacks, with **zero false blocks** on 60 benign
prompts.

## What is in this directory

| file | content |
|---|---|
| [`ABSTRACT.md`](./ABSTRACT.md) | 495-word abstract |
| [`REPORT.md`](./REPORT.md) | full write-up (method, negative results, numbers, limitations) |

## Pipeline (three Lexsi repos, one chain)

```
CuratorKIT  ->  SafeTune  ->  MAREF gate  ->  AuditKIT
curation        steering      input-side      independent
204 -> 204      negative      normalisation   scoring
0 rejected      result        21/24 enc.      78.72% / 0% OR
```

- **CuratorKIT** — published attack, benign and holdout sets run through a
  real reader → gates → normalizers → exporters chain. 204 in, 204 out,
  0 rejected, with provenance manifest, dataset card and checksums.
- **SafeTune** — `RefusalDirectionModel` steering sweep (alpha 0.0–1.5).
  Negative result: steering does not move encoded-attack ASR.
- **AuditKIT** — independent scoring of the same model outputs
  (`RedTeamRunner`), so the headline number is not our own regex grading itself.
- **MAREF gate** — the input-side normalisation and rule layer this repo
  maintains. Not a Lexsi tool; presented as a deployment-side complement.

## Numbers

| Condition | Attack success | ASR |
|---|---|---|
| Raw `CohereLabs/tiny-aya-global` | 74 / 94 | 78.72% |
| + MAREF gate | 37 / 94 | **39.36%** |

Gate decision split: 40 DENY (model never sees it), 2 REWRITE (restored
plaintext), 52 ALLOW. Of the 54 that reach the model, 37 still succeed — that
is the residual risk, reported rather than rounded away.

Over-refusal: 60/60 benign pass, including 20 defensive security questions that
contain harmful subject words.

## Reproduce

Everything runs locally on one machine (M4 / 24 GB, MPS). No inference credits.

All evaluation code, data and hash-pinned snapshots live in
[`hackathon/lexsi-track2a/`](../../hackathon/lexsi-track2a/) — that directory has
its own README with the full reproduction guide.

```bash
cd hackathon/lexsi-track2a

# 1. gate + datasets + AuditKIT replay (hash-asserted, no model call)
make reproduce

# 2. full pipeline (gate -> model -> score, ~5 min on M4)
PYTHONPATH=../../src python3 prep/gate_pipeline_eval.py

# 3. CuratorKIT curation (3rd Lexsi repo in the chain)
#    clone Lexsi-Labs/CuratorKIT first, then run from this directory
PYTHONPATH=prep curatorkit run prep/curatorkit_pipeline.yaml \
  --output-dir prep/curatorkit_out
```

Artifacts live in `hackathon/lexsi-track2a/prep/runs/`
(`gate_pipeline_v1.json`, `auditkit_baseline_v1.json`, `alpha_sweep_v2.json`)
and `hackathon/lexsi-track2a/prep/curatorkit_out/` (manifest, dataset card,
checksums).

### Reproducibility notes

- Gate decisions are pinned by SHA-256 hashes in `prep/expected/*.json`;
  `make reproduce` asserts all five targets.
- The model is not re-run by `make reproduce` — AuditKIT replays stored
  outputs, so the check is fast and deterministic.
- `gate_pipeline_eval.py` does load the model (≈5 min on M4) because it needs
  live inference; it writes per-prompt paths so every number can be traced.
- Python 3.13, PyTorch 2.15 (MPS), transformers 5.22.

## SafeTune footgun (documented for other teams)

Constructing `RefusalDirectionModel(...)` without calling `.install()` returns
an **unmodified** model and produces a silent no-op. If your alpha sweep looks
flat, check that first.

## Artifacts on Hugging Face

- Dataset: [`maref-org/lexsi-redteam-set`](https://huggingface.co/datasets/maref-org/lexsi-redteam-set)
- Steering direction: [`maref-org/tiny-aya-refusal-direction`](https://huggingface.co/maref-org/tiny-aya-refusal-direction)
- Collections (public, un-gated):
  - dataset + traces → [collection](https://huggingface.co/collections/maref-org/maref-lexsi-track-2a-red-team-dataset-traces-6aede19d9606318fb0da635c)
  - steering direction → [collection](https://huggingface.co/collections/maref-org/maref-lexsi-track-2a-tiny-aya-refusal-direction-6af56da9e74357660567f4d3)
  - negative result → [collection](https://huggingface.co/collections/maref-org/maref-tiny-aya-refusal-direction-negative-result-6aede19c6961494aa4eb618c)

## License / openness

Datasets, logs, traces and reports are public so the community can build on
them, per the hackathon's open-project requirement.

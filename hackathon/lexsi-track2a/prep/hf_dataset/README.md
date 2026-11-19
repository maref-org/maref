---
license: cc-by-4.0
language:
  - en
task_categories:
  - text-generation
tags:
  - ai-safety
  - red-teaming
  - jailbreak
  - prompt-injection
  - encoding-attacks
  - multi-turn
  - agent-governance
  - benchmark
pretty_name: MAREF Lexsi Red Team Set (structured)
size_categories:
  - n<1K
configs:
  - config_name: prompts
    data_files:
      - split: dev
        path: data/prompts-dev.parquet
      - split: control
        path: data/prompts-control.parquet
      - split: holdout_v2
        path: data/prompts-holdout_v2.parquet
  - config_name: multi_turn
    data_files:
      - split: train
        path: data/multi_turn.parquet
---

# MAREF Lexsi Red Team Set (structured)

Encoding attacks, direct jailbreaks and benign controls used in
**"When Safety Is Semantic: Encoding Attacks Bypass Refusal-Direction Steering"**
(MAREF, Lexsi hackathon Track 2a).

This is the **structured** distribution of the same corpus: same prompts, same
labels, now with explicit splits, a fixed schema, and a datasheet. Nothing in the
prompts or the labels was edited — the numbers published in the report remain the
numbers you reproduce from this data.

## ⚠️ Content warning

This dataset contains prompts that **ask a model to do harmful things** (jailbreaks,
data exfiltration, tool abuse). They exist so defenders can measure whether a gate
blocks them. Do not use them as training targets, and do not paste them into
production systems without a gate in front.

Harmful payloads are mostly obfuscated (base64 / ROT13 / morse / reversed / split).
The dataset is published in the form it was used for evaluation, not as a
ready-to-run attack kit. Prefer reporting aggregates over example payloads.

## Splits

| split | n | what it is |
|---|---|---|
| `dev` | 174 | 94 attacks (`expect=refuse`) + 80 benign (`expect=comply`). **This is the set behind every published number.** |
| `control` | 30 | benign prompts that are *encoded* — the false-block control |
| `holdout_v2` | 30 | pre-registered fresh split, disjoint from `dev`, used to verify the fix |

**`holdout_v1` is not a split — it is a boolean column.** Those 30 prompts are a
**100% subset of `dev`** (verified: 30/30 ids and 30/30 prompt hashes match). Exposing
them as their own split would let a loader train on `dev` and "test" on data it has
already seen, silently inflating results. Filter instead:

```python
ds["dev"].filter(lambda r: r["holdout_v1"])
```

## Schema (`prompts` config)

| column | type | notes |
|---|---|---|
| `id` | string | e.g. `a01`, `c02`, `bn07`, `v2a03` |
| `prompt` | string | the exact text sent to the model |
| `expect` | string | `refuse` or `comply` |
| `category` | string | `jailbreak_direct` / `roleplay` / `encoding` / `prompt_injection` / `data_exfil` / `tool_abuse` / `benign` |
| `encoding` | string | explicit subtype when the source recorded it (`base64`, `rot13`, `emoji`, `split`, `reverse`, `morse`, `keyboard`, `acrostic`, …); **empty when the source did not record one** |
| `group` | string | benign grouping (`everyday`, …) |
| `plain` | string | for encoded-benign rows: the underlying plain question |
| `acrostic` | string | for acrostic rows: the hidden word |
| `holdout_v1` | bool | see above |
| `split` | string | `dev` / `control` / `holdout_v2` |
| `source` | string | originating file, for provenance |

`multi_turn` config: `id`, `turns` (list), `n_turns`, `expect`, `category`, `split`, `source`.

## Load

```python
from datasets import load_dataset
ds  = load_dataset("maref-org/lexsi-redteam-set-v2", "prompts")
mt  = load_dataset("maref-org/lexsi-redteam-set-v2", "multi_turn")
```

## Known limitations (read before slicing)

1. **Dev encoding subtypes are missing.** The v1 red-team file recorded only
   `{id, category, prompt, expect}` for its 24 encoding attacks — no subtype.
   We did **not** infer one. The control set and `holdout_v2` do carry explicit
   subtypes, so per-subtype analysis is only clean there.
2. **Small.** 264 rows total. Every rate in the report has a denominator in the
   tens — treat percentages as coarse.
3. **English only** in this version. A Chinese obfuscation subset is planned
   (full-width characters, pinyin initials, variation selectors) as a separate,
   clearly-labelled split — not folded into existing denominators.
4. **Not a leaderboard.** Attacks were curated for one threat model
   (input-side obfuscation against a frozen model). A model scoring well here is
   not thereby safe.
5. **Results depend on the gate**, not on the data. Reproduce with the code in the
   repo; the dataset alone cannot reproduce ASR.

## Provenance

- Curated and evaluated by MAREF (`maref-org`), Lexsi hackathon Track 2a, 2026-11.
- Base model in the report: `CohereLabs/tiny-aya-global` (3.35B, `cc-by-nc-4.0`), **no fine-tuning**.
- Cross-model checks: `Qwen2.5-3B`; a larger Cohere model is being added.
- Every deterministic claim is replayable: `cd hackathon/lexsi-track2a && make reproduce`
  (5 targets, decision-vector hashes).
- Report, pre-registrations, ledgers and per-run outputs: see the repo `docs/lexsi-hackathon/REPORT.md`.

## License

Prompts authored by this project are released under **CC-BY-4.0**. Derived
obfuscations inherit the same licence. Model outputs (stored run files, not part
of this dataset) are subject to the base model's licence.

## Citation

```bibtex
@misc{maref2026encoding,
  title  = {When Safety Is Semantic: Encoding Attacks Bypass Refusal-Direction Steering},
  author = {MAREF team},
  year   = {2026},
  note   = {Lexsi hackathon, Track 2a. Dataset: maref-org/lexsi-redteam-set-v2}
}
```

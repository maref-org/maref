# Datasheet — MAREF Lexsi Red Team Set (structured)

Following *Datasheets for Datasets* (Gebru et al., 2021). Answers describe **this
structured release**; where the underlying corpus is older, that is stated.

---

## 1. Motivation

**For what purpose was the dataset created?**
To measure whether an input-side defence (a decoding normaliser plus a rule gate)
changes the behaviour of a frozen language model against **obfuscated** harmful
requests — and to make that measurement replayable by others.

**Who created it and who funded it?**
The MAREF team, during the Lexsi *Create AI Agents* hackathon (Track 2a), November
2026. No external funding; the only compute used was a local Apple M4 (24 GB).

**Any other comments?**
The dataset exists because a negative result needed evidence: refusal-direction
steering changed model outputs but not behaviour on encoded attacks. Publishing the
prompts is what makes that claim checkable rather than assertable.

---

## 2. Composition

**What do the instances represent?**
Single-turn prompts (and 30 multi-turn conversations) sent verbatim to a chat model,
each labelled with the behaviour expected from a safe model (`refuse` / `comply`).

| split | rows | composition |
|---|---|---|
| `dev` | 174 | 94 attacks: direct jailbreak 18, roleplay 14, encoding 24, prompt injection 12, data exfiltration 14, tool abuse 12 — plus 80 benign prompts |
| `control` | 30 | benign prompts that are nonetheless encoded (base64 8, rot13 5, emoji 5, split 4, reverse 4, morse 2, keyboard 2) |
| `holdout_v2` | 30 | 16 encoding attacks + 14 benign, generated after the first read of `holdout_v1` |
| `multi_turn` (separate config) | 30 | gradual-escalation conversations, 3–6 turns each |

**Is any information missing?**
Yes, one field: the encoding *subtype* of the 24 dev encoding attacks was not
recorded in the v1 source file and was **not** reconstructed by inference.

**Are relationships between instances explicit?**
`holdout_v1` is a flag, because those 30 rows are a verified 100% subset of `dev`.
No other cross-split overlap exists (checked by id and by prompt hash at build time,
`prep/build_hf_dataset.py`).

**Recommended uses / uses to avoid.**
Use for: measuring gate precision/recall, testing decoding chains, teaching threat
models, replicating the report. Avoid: training a model on these as targets;
treating the set as a general safety benchmark; quoting per-subtype dev rates (see
missing field above).

**Sensitive content?**
Yes: prompts intentionally request harmful actions. Payloads are predominantly
obfuscated rather than plain, and the release does not include model outputs that
would demonstrate successful harm.

---

## 3. Collection process

**How was the data acquired?**
Hand-authored attack prompts across six categories, plus author-written benign
controls, informed by published jailbreak taxonomies. Multi-turn sets were written
as scripted escalation ladders. No scraping of private data, no user data.

**Sampling strategy.**
Category-first, then size-balanced to keep denominators readable; the benign set was
expanded from 20 to 80 after the first over-refusal measurement.

**Who collected it and how were they compensated?**
The authors, unpaid.

**Over what timeframe?**
November 2026, within the hackathon window.

**Ethical review.**
Internal only. The decision to publish rests on: prompts are required to make the
claim falsifiable, harmful payloads are obfuscated, and no real user data is present.

---

## 4. Preprocessing / cleaning / labelling

**Was any preprocessing done?**
No text was rewritten for this release. The build step only reshapes rows into a
fixed schema and attaches `split` / `source` provenance
(`prep/build_hf_dataset.py`, deterministic, re-runnable).

**Was the raw data saved?**
Yes — `prep/redteam_set_v1.jsonl`, `benign_set_v2.jsonl`, `benign_encoded.jsonl`,
`holdout_v1.jsonl`, `holdout_v2.jsonl`, `multi_turn_set_v1.jsonl`. Their sha256
digests are recorded in `manifest.json` next to this file.

**Is the labelling done by humans?**
`expect` labels were assigned by the authors at authoring time. One documented
exception: six baseline prompts whose intended instruction was not decodable were
re-classified during human review (`prep/runs/baseline_aya_v1_corrected.json`), and
the report reports both the automated and the reviewed rates.

**Are labels quality-controlled?**
Pre-registration fixes the target metric before each read; a fresh holdout (`v2`)
exists specifically because the first holdout was read once and then fixed. Rows
were not edited after any read.

---

## 5. Uses

**Has the dataset been used already?**
Yes: it produced the published results (end-to-end ASR 78.72% → 39.36% on the 94
`expect=refuse` attacks; gate handles 87.5% of encoding attacks; 0.0% false blocks on
benign sets), the steering negative result, and the cross-turn negative result.

**Are there tasks the dataset should not be used for?**
See §2. In particular: do not report per-subtype dev encoding rates; do not compare
across papers using different benign denominators.

**Any risks?**
Dual-use. Mitigations: obfuscated payloads, no working harm demonstrations, explicit
content warning, and a preference for aggregate reporting.

---

## 6. Distribution

**How is it distributed?**
Hugging Face Hub, parquet, two configs (`prompts`, `multi_turn`). Free of charge.

**Licence.**
CC-BY-4.0 for prompts authored here. Upstream model licences are unaffected because
no model weights are redistributed.

**Any IP or regulatory restrictions?**
None known. The corpus contains no third-party copyrighted text and no personal data.

---

## 7. Maintenance

**Who maintains it and how can they be contacted?**
The MAREF team, via the repository issue tracker.

**Will it be updated?**
Planned: (a) a Chinese obfuscation subset as its own labelled split — full-width
characters, pinyin initials, variation selectors — **never merged into existing
denominators**; (b) encoding subtypes for the dev encoding attacks if the original
authoring notes are recovered. Version bumps will state which rows changed.

**Will older versions be supported?**
Yes. Published numbers are tied to the version they were computed on; the report
cites that version explicitly.

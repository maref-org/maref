---
tags:
- curatorkit
configs:
- config_name: sft_alpaca
  default: true
  description: curatorkit sft_alpaca export, sha256 a4c0806b3cb227811360b10d0a2fe2966e652cd3535e6c7c0e4002738dd8c333
  data_files:
  - split: train
    path: sft_alpaca.jsonl
- config_name: sft_sharegpt
  description: curatorkit sft_sharegpt export, sha256 b8c07de336983c2c754dbe5d6cec40a760bc555cfdeb1352befb2e7213e400ec
  data_files:
  - split: train
    path: sft_sharegpt.jsonl
---

# Dataset Card: maref_redteam_curation

## Summary

- **Run timestamp**: 2026-11-07T09:34:52.152191Z
- **Wall clock time**: 0.0s
- **Pipeline config hash**: `c592e560ea9a5d31`

## Source Documents

  - Unknown

## Pipeline Stages

| Step | Input | Passed | Recovered | Rejected | Forward |
|------|-------|--------|-----------|----------|---------|
| JSONLReader | 204 | 204 | — | 0 | 204 |
| SchemaGate | 204 | 204 | 0 | 0 | 204 |
| ExactDeduplicator | 204 | 204 | — | — | 204 |
| TextCleaner | 204 | 204 | — | — | 204 |
| AlpacaExporter | — | 204 | — | — | 204 |
| ShareGPTExporter | — | 204 | — | — | 204 |

## Gate Pass Rates and Rejection Breakdown

- **JSONLReader**: 204/0 passed (N/A), 0 rejected
- **SchemaGate**: 204/204 passed (100.0%), 0 rejected


**Rejection reasons:**
  - None

## Deduplication

  - exact_duplicates_removed: 0

## Known Limitations

- No MinHash deduplication applied.
- Table extraction requires `extract_tables: true` on the PDF reader and MinerU with GPU support. Disabled by default.
- Token counting uses a whitespace tokenizer by default. For exact LLM context window
  enforcement, enable `use_tiktoken: true` in the SchemaGate config.
- Both within-run (MinHash/Diversity) and cross-run (EmbeddingDeduplicator) deduplication
  are available. Cross-run dedup persists an embedding index across runs; use
  `embedding_reset_index: true` to start fresh.

## Reproduction

```bash
pip install curatorkit
curatorkit run pipeline.yaml --output-dir ./out/
```

## Tool Versions

- **curatorkit**: 0.1.21
- **python**: 3.13.12

## Configs

Load one with `datasets.load_dataset("<this folder or Hub repo>", "<config>")`.

| Config | Splits (rows) | Columns |
|--------|---------------|---------|
| `sft_alpaca` | train (204) | `instruction`: string<br>`input`: string (empty when there is no input)<br>`output`: string |
| `sft_sharegpt` | train (204) | `conversations`: list of {from, value}; from is system, human or gpt |
